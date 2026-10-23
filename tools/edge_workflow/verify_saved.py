"""Verify final input/result guards against saved real runs without execution."""

import argparse
import hashlib
import json
from pathlib import Path


def verify(root, suite_fallback=None):
    root = Path(root)
    plan = json.loads((root / "plan.json").read_text())
    request = json.loads((root / "adapter-request.json").read_text())
    result = json.loads((root / "results.json").read_text())
    rawpath = root / "raw/results.json"
    raw = json.loads(rawpath.read_text())
    suite = Path(plan["suite_ref"])
    if not suite.exists():
        suite = Path(suite_fallback)
    assert (
        hashlib.sha256(suite.read_bytes()).hexdigest() == plan["suite_sha256"]
    )
    rows = json.loads(suite.read_text())["samples"]
    assert raw["run_id"] == request["run_id"]
    assert result["status"] == "completed"
    assert len(raw["cases"]) == len(rows) == raw["summary"]["samples"]
    assert {c["id"] for c in raw["cases"]} == {c["id"] for c in rows}
    if plan["profile"] == "native-tool-persona-v1":
        assert all(
            c["user"] == f["user"] and c["expected"] == f["expected"]
            for c, f in zip(raw["cases"], rows)
        )
    assert (
        hashlib.sha256(rawpath.read_bytes()).hexdigest()
        == result["raw_result"]["sha256"]
    )
    return {
        "run_id": result["run_id"],
        "profile": plan["profile"],
        "samples": len(rows),
        "status": "verified against current identity/denominator guards",
        "raw_sha256": hashlib.sha256(rawpath.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--suite-fallback", type=Path)
    args = parser.parse_args()
    with args.output.open("x") as stream:
        json.dump(verify(args.root, args.suite_fallback), stream, indent=2)


if __name__ == "__main__":
    main()
