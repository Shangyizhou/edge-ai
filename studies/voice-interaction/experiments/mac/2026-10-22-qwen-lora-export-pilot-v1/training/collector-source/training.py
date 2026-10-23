"""Explicit MLX LoRA experiment; final test data is never loaded here."""

import argparse
import contextlib
import copy
import importlib.metadata
import json
import time
from pathlib import Path

from .benchmark import asset_manifest, file_hash, read_json, write_json
from .measure import ResourceSampler
from .lineage import freeze_sources


def load_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def validate_splits(train, valid):
    """Source families and exact user prompts cannot cross the two splits."""
    if not train or not valid:
        raise ValueError("train and valid must both contain examples")
    for rows in (train, valid):
        ids = [row["id"] for row in rows]
        if len(set(ids)) != len(ids):
            raise ValueError("sample IDs must be unique within each split")
        if any(not row.get("source_group") for row in rows):
            raise ValueError("each example requires source_group")
    if {r["source_group"] for r in train} & {r["source_group"] for r in valid}:
        raise ValueError("source_group leakage between train and valid")
    prompts = lambda rows: {tuple(m.get("content", "") for m in r["messages"]
                                  if m["role"] == "user") for r in rows}
    if prompts(train) & prompts(valid):
        raise ValueError("exact user prompt leakage between train and valid")


def prepare_samples(rows, tokenizer, max_length):
    """Materialize official nonthinking template and prove every loss prefix."""
    from jsonschema import Draft202012Validator

    encoded, proof = [], []
    for row in rows:
        messages = row["messages"]
        if not messages or messages[-1]["role"] != "assistant":
            raise ValueError("each supervised example must end in assistant")
        tools = row.get("tools", [])
        schemas = {t["function"]["name"]: t["function"]["parameters"]
                   for t in tools}
        for call in messages[-1].get("tool_calls", []):
            function = call["function"]
            if function["name"] not in schemas:
                raise ValueError("unknown tool in training target")
            if not isinstance(function["arguments"], dict):
                raise ValueError("training arguments must be JSON objects")
            Draft202012Validator(schemas[function["name"]]).validate(
                function["arguments"])
        options = dict(tools=tools or None, tokenize=True, return_dict=False,
                       enable_thinking=False)
        tokens = tokenizer.apply_chat_template(messages, **options)
        prefix = tokenizer.apply_chat_template(
            messages[:-1], add_generation_prompt=True, **options)
        if tokens[:len(prefix)] != prefix or len(tokens) <= len(prefix):
            raise ValueError("assistant loss mask does not match inference prefix")
        if len(tokens) > max_length:
            raise ValueError(f"sample {row['id']} exceeds max_seq_length: "
                             f"{len(tokens)} > {max_length}; no truncation")
        encoded.append((tokens, len(prefix)))
        proof.append({"id": row["id"], "source_group": row["source_group"],
                      "tokens": len(tokens), "offset": len(prefix),
                      "prefix_matches_inference": True,
                      "target_tokens": len(tokens) - len(prefix),
                      "supervised_target": tokenizer.decode(tokens[len(prefix):])})
    return encoded, proof


class EncodedDataset:
    """MLX CacheDataset-compatible preflighted token/offset records."""

    def __init__(self, records):
        self.records = records

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        return self.records[index]

    def process(self, record):
        return record


def train(request, output):
    if request.get("schema") != "edge-model-finetune/request-v1":
        raise ValueError("unsupported finetune request schema")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "request.json", request)
    train_rows = load_jsonl(request["dataset"]["train_ref"])
    valid_rows = load_jsonl(request["dataset"]["valid_ref"])
    validate_splits(train_rows, valid_rows)
    for name, rows in (("train", train_rows), ("valid", valid_rows)):
        (output / (name + ".jsonl")).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    import mlx.core as mx
    import numpy as np
    from mlx_lm import load
    from mlx_lm.lora import CONFIG_DEFAULTS, train_model
    from mlx_lm.tuner.callbacks import TrainingCallback

    config = copy.deepcopy(CONFIG_DEFAULTS)
    config.update(request.get("train_config", {}))
    if config["fine_tune_type"] not in ("lora", "dora"):
        raise ValueError("this experiment adapter supports low-rank tuning only")
    if config["iters"] % config["grad_accumulation_steps"]:
        raise ValueError("iters must include complete gradient accumulation groups")
    config.update(model=request["base_artifact"]["model_path"], train=True,
                  test=False, mask_prompt=True,
                  adapter_path=str(output / "adapter"))
    write_json(output / "train-config.json", config)
    result = {"schema": "edge-model-finetune/result-v1",
              "run_id": request["run_id"], "status": "running",
              "source": {"kind": "device_measurement"},
              "base_artifact": request["base_artifact"],
              "request_sha256": file_hash(output / "request.json"),
              "dataset": {"train_samples": len(train_rows),
                          "valid_samples": len(valid_rows), "test_loaded": False,
                          "train_sha256": file_hash(output / "train.jsonl"),
                          "valid_sha256": file_hash(output / "valid.jsonl")},
              "runtime": {key: importlib.metadata.version(key)
                          for key in ("mlx", "mlx-lm", "transformers")},
              "config": config, "metrics": [],
              "measurement_sources": freeze_sources(output, [
                  "training.py", "measure.py", "benchmark.py", "lineage.py"]),
              "measurement": "whole run resources include model load, preflight, "
              "training and validation; native training tokens/s counts supervised "
              "tokens and excludes validation; MLX GB are decimal, not RSS"}
    started = time.perf_counter()
    sampler = ResourceSampler(interval=request.get(
        "sampling_interval_seconds", 0.2)).start()
    metric_file = output / "metrics.jsonl"

    class Recorder(TrainingCallback):
        def record(self, kind, info):
            clean = {k: v.item() if hasattr(v, "item") else v
                     for k, v in info.items()}
            event = {"kind": kind, "elapsed_seconds": time.perf_counter() - started,
                     "upstream": clean,
                     "microstep": clean.get("iteration", 0) + (
                         1 if kind == "validation" and clean.get("iteration", 0)
                         else 0)}
            result["metrics"].append(event)
            with metric_file.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            write_json(output / "results.json", result)

        def on_train_loss_report(self, info):
            self.record("train", info)

        def on_val_loss_report(self, info):
            self.record("validation", info)

    try:
        with (output / "training.log").open("w", encoding="utf-8") as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                model, tokenizer = load(config["model"])
                result["load_seconds"] = time.perf_counter() - started
                train_data, train_proof = prepare_samples(
                    train_rows, tokenizer, config["max_seq_length"])
                valid_data, valid_proof = prepare_samples(
                    valid_rows, tokenizer, config["max_seq_length"])
                write_json(output / "preflight.json",
                           {"train": train_proof, "valid": valid_proof,
                            "enable_thinking": False, "silent_truncation": False})
                result["preflight"] = {"maximum_tokens": max(
                    p["tokens"] for p in train_proof + valid_proof),
                    "mask_prefix_matches": True}
                mx.reset_peak_memory()
                np.random.seed(config["seed"])
                train_started = time.perf_counter()
                train_model(argparse.Namespace(**config), model,
                            EncodedDataset(train_data), EncodedDataset(valid_data),
                            training_callback=Recorder())
                from mlx.utils import tree_flatten
                result["trainable_parameters"] = sum(
                    value.size for _, value in tree_flatten(model.trainable_parameters()))
                result["training_wall_seconds"] = time.perf_counter() - train_started
                result["mlx_peak_allocated_bytes"] = mx.get_peak_memory()
        result["status"] = "completed"
        result["microsteps"] = config["iters"]
        result["optimizer_updates"] = config["iters"] // config["grad_accumulation_steps"]
        result["adapter"] = asset_manifest({"model_path": config["adapter_path"]})
    except (ValueError, RuntimeError, OSError) as error:
        result["status"] = "failed"
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        result["resources"] = sampler.stop()
        result["wall_seconds"] = time.perf_counter() - started
        write_json(output / "resource-samples.json", sampler.samples)
        result["evidence"] = [{"path": p.name, "sha256": file_hash(p)}
                              for p in sorted(output.iterdir()) if p.is_file()
                              and p.name != "results.json"]
        write_json(output / "results.json", result)
    return result
