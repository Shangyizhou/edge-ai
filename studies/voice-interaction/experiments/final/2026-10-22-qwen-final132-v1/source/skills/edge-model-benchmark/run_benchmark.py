#!/usr/bin/env python3
"""Run an explicit project adapter and validate its evidence handoff."""

import argparse
import json
import subprocess
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require_object(value, label):
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a nonempty object")
    return value


def check_hash(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("SHA256 must be 64 lowercase hexadecimal characters")


def check_evidence(value):
    if not isinstance(value, list) or not value:
        raise ValueError("hashed raw evidence references are required")
    for item in value:
        require_object(item, "evidence reference")
        if not isinstance(item.get("path"), str) or not item["path"]:
            raise ValueError("evidence path is required")
        check_hash(item.get("sha256"))


def check_manifest(value):
    require_object(value, "artifact manifest")
    if not isinstance(value.get("root"), str) or not value["root"]:
        raise ValueError("artifact root identity is required")
    files = value.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("artifact files are required")
    names = set()
    for item in files:
        require_object(item, "artifact file")
        name, size = item.get("name"), item.get("bytes")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("unique artifact file names are required")
        names.add(name)
        if type(size) is not int or size < 0:
            raise ValueError("artifact byte count is required")
        check_hash(item.get("sha256"))
    if type(value.get("total_bytes")) is not int or value["total_bytes"] != sum(f["bytes"] for f in files):
        raise ValueError("manifest total_bytes must match file sizes")


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
    for field in ("candidate", "environment", "summary"):
        require_object(value.get(field), field)
    check_hash(value.get("request_sha256"))
    check_hash(value.get("suite_sha256"))
    check_manifest(value.get("artifacts"))
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("adapter must preserve per-case evidence")
    ids = set()
    for case in cases:
        require_object(case, "case")
        if not isinstance(case.get("id"), str) or not case["id"] or case["id"] in ids:
            raise ValueError("unique case IDs are required")
        ids.add(case["id"])
        if not isinstance(case.get("user"), str):
            raise ValueError("case user input is required")
        require_object(case.get("expected"), "expected behavior")
        if case.get("status") == "failed":
            if not case.get("error"):
                raise ValueError("failed case requires an error")
            continue
        if case.get("status") != "completed":
            raise ValueError("case must be completed or explicitly failed")
        generation = require_object(case.get("generation"), "generation")
        if not isinstance(generation.get("raw"), str) or not generation.get("finish_reason") or "wire_calls" not in generation:
            raise ValueError("original generation, finish state and wire calls are required")
        assessment = require_object(case.get("assessment"), "assessment")
        for field in ("native_parse", "json_valid", "schema_valid", "registry_valid", "expected_behavior", "persona_valid"):
            if field not in assessment or assessment[field] is not None and type(assessment[field]) is not bool:
                raise ValueError(f"explicit boolean/null {field} outcome is required")
        reply = require_object(assessment.get("reply"), "parsed reply")
        if not isinstance(reply.get("tool_calls"), list) or not assessment.get("reviewer"):
            raise ValueError("parsed calls and reviewer are required")
    check_evidence(value.get("evidence"))


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
