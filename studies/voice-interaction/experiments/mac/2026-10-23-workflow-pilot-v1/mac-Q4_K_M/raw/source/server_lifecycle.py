"""Shared owned-server lifecycle for platform entrypoints."""

import argparse
import json
import platform
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from .benchmark import asset_manifest, file_hash, read_json, run, write_json
from .measure import ResourceSampler
from .report import render


def launcher_handoff(result, benchmark_result_path):
    """Rebase launcher evidence; preserve the raw result."""
    handoff = dict(result)
    handoff["source"] = dict(
        result["source"],
        raw_evidence="benchmark/cases/ and benchmark/events/",
    )
    handoff["evidence"] = [
        dict(item, path="benchmark/" + item["path"])
        for item in result["evidence"]
    ]
    handoff["benchmark_result"] = {
        "path": "benchmark/results.json",
        "sha256": file_hash(benchmark_result_path),
    }
    return handoff


def execute(request, output, dependency_probe):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "launcher-request.json", request)
    source = output / "source"
    source.mkdir()
    for path in Path(__file__).parent.glob("*.py"):
        (source / path.name).write_bytes(path.read_bytes())
    settings = request["server"]
    port = settings.get("port", 18082)
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("server port must be an unprivileged TCP port")
    forbidden = ("--host", "--port", "-m", "--model", "-hf", "--hf-repo")
    if any(arg.split("=")[0] in forbidden for arg in settings["argv"]):
        raise ValueError(
            "server argv cannot override loopback, port or model identity"
        )
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))
    endpoint = "http://127.0.0.1:" + str(port)
    write_json(
        output / "assets-manifest.json", asset_manifest(request["candidate"])
    )
    argv = [
        settings["binary"],
        "-m",
        request["candidate"]["model_path"],
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ] + settings["argv"]
    write_json(output / "server-command.json", argv)
    identity = {
        "binary_sha256": file_hash(settings["binary"]),
        "platform": platform.platform(),
        "uname": list(platform.uname()),
        "version": subprocess.run(
            [settings["binary"], "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        ).stdout,
        dependency_probe[0]: subprocess.run(
            dependency_probe[1] + [settings["binary"]],
            capture_output=True,
            text=True,
        ).stdout,
    }
    libraries = []
    for word in identity[dependency_probe[0]].split():
        path = Path(word)
        if word.startswith("/") and path.is_file():
            libraries.append(
                {
                    "path": str(path),
                    "sha256": file_hash(path),
                    "bytes": path.stat().st_size,
                }
            )
    identity["shared_libraries"] = libraries
    write_json(output / "runtime.json", identity)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def post(route, data):
        req = urllib.request.Request(
            endpoint + route,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
        with opener.open(req, timeout=30) as response:
            return json.load(response)

    with (output / "server.log").open("w") as log:
        process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
        sampler = ResourceSampler(process.pid, 0.2).start()
        started = time.perf_counter()
        try:
            while True:
                if process.poll() is not None:
                    raise RuntimeError(
                        "owned server exited: " + str(process.returncode)
                    )
                try:
                    with opener.open(
                        endpoint + "/health", timeout=2
                    ) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                if time.perf_counter() - started > 180:
                    raise RuntimeError("server readiness timeout")
                time.sleep(0.2)
            write_json(
                output / "server-load.json",
                {
                    "health_ready_seconds": time.perf_counter() - started,
                    "resources": sampler.stop(),
                    "samples": sampler.samples,
                    "scope": "process launch to health; "
                    "model inference tested separately",
                },
            )
            suite = request.get("suite") or read_json(request["suite_ref"])
            budgets = []
            for sample in suite["samples"]:
                value = post(
                    "/apply-template",
                    {
                        "messages": [
                            {
                                "role": "system",
                                "content": suite.get("system", ""),
                            },
                            {"role": "user", "content": sample["user"]},
                        ],
                        "tools": suite.get("tools"),
                        "add_generation_prompt": True,
                        "chat_template_kwargs": {"enable_thinking": False},
                    },
                )
                tokens = post(
                    "/tokenize",
                    {"content": value["prompt"], "add_special": False},
                )["tokens"]
                budgets.append(
                    {
                        "id": sample["id"],
                        "prompt": value["prompt"],
                        "prompt_tokens": len(tokens),
                        "maximum_output_tokens": request["generation"][
                            "max_tokens"
                        ],
                    }
                )
                if (
                    len(tokens) + request["generation"]["max_tokens"]
                    > request["generation"]["context_tokens"]
                ):
                    raise ValueError("complete context budget exceeded")
            write_json(output / "context-budget.json", budgets)
            request["runner"] = dict(
                request["runner"], endpoint=endpoint, monitor_pid=process.pid
            )
            result = run(request, output / "benchmark")
            (output / "benchmark/report.html").write_text(
                render([result]), encoding="utf-8"
            )
            handoff = launcher_handoff(
                result, output / "benchmark/results.json"
            )
            write_json(output / "results.json", handoff)
            (output / "report.html").write_text(
                render([handoff]), encoding="utf-8"
            )
            return handoff
        except Exception as error:
            write_json(
                output / "launcher-failure.json",
                {"type": type(error).__name__, "message": str(error)},
            )
            raise
        finally:
            if sampler.thread.is_alive():
                write_json(
                    output / "failed-load.json",
                    {"resources": sampler.stop(), "samples": sampler.samples},
                )
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            write_json(
                output / "owned-process-exit.json",
                {"pid": process.pid, "exit_code": process.returncode},
            )


def main(executor, description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    fresh_output = not args.output.exists()
    try:
        executor(read_json(args.request), args.output)
    except Exception as error:
        if (
            fresh_output
            and args.output.is_dir()
            and not (args.output / "launcher-failure.json").exists()
        ):
            write_json(
                args.output / "launcher-failure.json",
                {"type": type(error).__name__, "message": str(error)},
            )
        raise
