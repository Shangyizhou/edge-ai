#!/usr/bin/env python3
"""Run an explicit project adapter and validate its evidence handoff."""

import argparse
import json
import subprocess
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_request(value):
    if value.get("schema") != "edge-model-benchmark/request-v1":
        raise ValueError("unsupported benchmark request schema")
    if not value.get("run_id") or not isinstance(value.get("candidate"), dict):
        raise ValueError("run_id and candidate are required")
    if not value.get("suite") and not value.get("suite_ref"):
        raise ValueError("a frozen suite or suite_ref is required")


def check_result(value, request):
    if value.get("schema") != "edge-model-benchmark/result-v1":
        raise ValueError("adapter did not produce benchmark result-v1")
    if value.get("run_id") != request["run_id"]:
        raise ValueError("adapter result belongs to another run")
    if value.get("source", {}).get("kind") != "device_measurement":
        raise ValueError("synthetic fixtures cannot satisfy real benchmark handoff")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("adapter must preserve per-case evidence")
    if not value.get("evidence"):
        raise ValueError("adapter must reference raw evidence")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args()
    if not args.command:
        parser.error("--command requires the project adapter argv")
    request_path = args.request.resolve()
    output = args.output.resolve()
    request = load(request_path)
    check_request(request)
    if output.exists():
        raise FileExistsError("benchmark output must be a new directory")
    completed = subprocess.run(
        args.command + [str(request_path), str(output)], cwd=args.cwd,
        check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    check_result(load(output / "results.json"), request)
    print(output / "results.json")


if __name__ == "__main__":
    main()
