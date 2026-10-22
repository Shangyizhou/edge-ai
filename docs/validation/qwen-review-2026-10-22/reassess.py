"""Read-only intake comparison without Registry or model execution."""

import hashlib
import json
import subprocess
from pathlib import Path

from tools.qwen_lifecycle.protocol import intake

ROOT = Path(__file__).resolve().parents[3]
BASE = "6d7c0decc16c768a6e9c2db22ab0abf2088048da"
old = {"__name__": "old_protocol"}
exec(
    subprocess.check_output(
        ["git", "show", BASE + ":tools/qwen_lifecycle/protocol.py"],
        cwd=ROOT,
        text=True,
    ),
    old,
)
STUDY = ROOT / "studies/voice-interaction/experiments"
paths = sorted(
    (STUDY / "mac/2026-10-22-qwen-selected9-adaptation-v1/validation").glob(
        "*/results.json"
    )
)
paths += sorted(
    (STUDY / "final/2026-10-22-qwen-final132-v1/runs").glob(
        "*/benchmark/results.json"
    )
)
paths += sorted(
    (STUDY / "mac/2026-10-22-qwen-selected-precision-v1/runs").glob(
        "*/benchmark/results.json"
    )
)
keys = [
    "native_parse",
    "json_valid",
    "response_complete",
    "schema_valid",
    "expected_behavior",
    "reply",
]
runs = []
for path in paths:
    result = json.loads(path.read_text())
    if result["run_id"].endswith("launch-interrupted"):
        continue
    suite = json.loads((path.parent / "suite.json").read_text())
    hashes = {}
    for item in [
        path,
        path.parent / "request.json",
        path.parent / "suite.json",
    ]:
        hashes[str(item.relative_to(ROOT))] = hashlib.sha256(
            item.read_bytes()
        ).hexdigest()
    changed, recorded = [], []
    counts = {key: {"old": 0, "current": 0} for key in keys[:-1]}
    for case in result["cases"]:
        generation = case.get("generation")
        if not generation:
            continue
        args = (
            generation["raw"],
            generation["finish_reason"],
            suite["tools"],
            case["expected"],
            generation.get("wire_calls"),
        )
        previous, current = old["intake"](*args), intake(*args)
        delta = [key for key in keys if previous.get(key) != current.get(key)]
        if delta:
            changed.append({"id": case["id"], "fields": delta})
        delta = [
            key
            for key in keys
            if key in case["assessment"]
            and case["assessment"].get(key) != current.get(key)
        ]
        if delta:
            recorded.append({"id": case["id"], "fields": delta})
        for key in counts:
            counts[key]["old"] += previous.get(key) is True
            counts[key]["current"] += current.get(key) is True
    # Prove analysis did not rewrite the source evidence.
    for name, digest in hashes.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    runs.append(
        {
            "path": str(path.relative_to(ROOT)),
            "cases": len(result["cases"]),
            "counts": counts,
            "old_current_differences": changed,
            "recorded_current_differences": recorded,
            "unchanged_sha256": hashes,
        }
    )
print(
    json.dumps(
        {
            "base": BASE,
            "scope": (
                "read-only syntax/JSON/Schema/expected behavior; "
                "no Registry subprocess, handlers, models or persona re-review"
            ),
            "runs": runs,
        },
        ensure_ascii=False,
        indent=2,
    )
)
