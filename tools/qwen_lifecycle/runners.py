"""Minimal MLX/llama.cpp transports; neither adapter executes business tools."""

import importlib.metadata
import json
import time
import urllib.request


class MlxRunner:
    """Load one model, reset the per-case MLX peak, disable prompt caching."""

    def __init__(self, request):
        import mlx.core as mx
        from mlx_lm import load

        self.mx = mx
        candidate = request["candidate"]
        kwargs = {}
        if candidate.get("adapter_path"):
            kwargs["adapter_path"] = candidate["adapter_path"]
        self.model, self.tokenizer = load(candidate["model_path"], **kwargs)
        self.identity = {
            "name": "mlx-lm",
            "version": importlib.metadata.version("mlx-lm"),
            "mlx_version": importlib.metadata.version("mlx"),
            "backend": "Metal",
        }

    def generate(self, messages, tools, config, on_event):
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        tokens = self.tokenizer.apply_chat_template(
            messages,
            tools=tools or None,
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
            return_dict=False,
        )
        if len(tokens) + config.get("max_tokens", 256) > config.get(
            "context_tokens", 4096
        ):
            raise ValueError(
                "context_budget: complete prompt plus output "
                "exceeds configured context; no truncation"
            )
        self.mx.reset_peak_memory()
        started = time.perf_counter()
        chunks = []
        first = None
        last = None
        for response in stream_generate(
            self.model,
            self.tokenizer,
            tokens,
            max_tokens=config.get("max_tokens", 256),
            sampler=make_sampler(temp=config.get("temperature", 0)),
            prefill_step_size=config.get("prefill_step_size", 512),
        ):
            elapsed = time.perf_counter() - started
            if response.text and first is None:
                first = elapsed
            chunks.append(response.text)
            last = response
            on_event(
                {
                    "elapsed_seconds": elapsed,
                    "text": response.text,
                    "token": response.token,
                    "generation_tokens": response.generation_tokens,
                    "finish_reason": response.finish_reason,
                }
            )
        if last is None:
            raise RuntimeError("model produced no generation response")
        return {
            "raw": "".join(chunks),
            "finish_reason": last.finish_reason,
            "ttft_seconds": first,
            "wall_seconds": time.perf_counter() - started,
            "prompt_tokens": last.prompt_tokens,
            "output_tokens": last.generation_tokens,
            "prefill_tokens_per_second": last.prompt_tps,
            "decode_tokens_per_second": last.generation_tps,
            "prefill_seconds": last.prompt_tokens / last.prompt_tps,
            "decode_seconds": last.generation_tokens / last.generation_tps,
            "mlx_peak_allocated_bytes": int(last.peak_memory * 1e9),
            "timing_source": "MLX GenerationResponse; prompt time "
            "includes first model token; generation count includes EOS",
            "wire_calls": None,
        }


class LlamaHttpRunner:
    """Use llama-server native OpenAI tool parser and preserve stream events."""

    def __init__(self, request):
        self.settings = request["runner"]
        self.identity = {
            "name": "llama.cpp",
            "version": request["candidate"].get("runtime_version"),
            "backend": request["candidate"].get("backend"),
            "network": self.settings.get("network", "direct"),
        }
        network = self.settings.get("network", "direct")
        if network not in ("direct", "environment"):
            raise ValueError("HTTP network must be direct or environment")
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
            if network == "direct"
            else urllib.request.ProxyHandler()
        )

    def generate(self, messages, tools, config, on_event):
        payload = {
            "messages": messages,
            "stream": True,
            "temperature": config.get("temperature", 0),
            "max_tokens": config.get("max_tokens", 256),
            "cache_prompt": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if tools:
            payload.update(
                tools=tools, tool_choice="auto", parallel_tool_calls=True
            )
        endpoint = self.settings["endpoint"].rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/v1/chat/completions"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        started = time.perf_counter()
        first = None
        text = []
        calls = {}
        finish = None
        timings = {}
        with self.opener.open(
            request, timeout=config.get("timeout_seconds", 600)
        ) as response:
            for line in response:
                if not line.startswith(b"data: "):
                    continue
                data = line[6:].strip()
                if data == b"[DONE]":
                    break
                event = json.loads(data)
                elapsed = time.perf_counter() - started
                on_event({"elapsed_seconds": elapsed, "wire": event})
                timings.update(event.get("timings", {}))
                for choice in event.get("choices", []):
                    delta = choice.get("delta", {})
                    if (
                        delta.get("content") or delta.get("tool_calls")
                    ) and first is None:
                        first = elapsed
                    text.append(delta.get("content") or "")
                    for piece in delta.get("tool_calls", []):
                        index = piece["index"]
                        call = calls.setdefault(
                            index,
                            {
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        for field in ("name", "arguments"):
                            call["function"][field] += piece.get(
                                "function", {}
                            ).get(field, "")
                        if piece.get("type"):
                            call["type"] = piece["type"]
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]
        return {
            "raw": "".join(text),
            "finish_reason": finish,
            "wire_calls": [calls[k] for k in sorted(calls)] if calls else None,
            "wall_seconds": time.perf_counter() - started,
            "ttft_seconds": first,
            "prompt_tokens": timings.get("prompt_n"),
            "output_tokens": timings.get("predicted_n"),
            "prefill_seconds": _seconds(timings.get("prompt_ms")),
            "decode_seconds": _seconds(timings.get("predicted_ms")),
            "prefill_tokens_per_second": timings.get("prompt_per_second"),
            "decode_tokens_per_second": timings.get("predicted_per_second"),
            "mlx_peak_allocated_bytes": None,
            "timing_source": "llama-server final timings; unknown if "
            "runtime does not emit timings",
        }


def _seconds(value):
    return None if value is None else value / 1000
