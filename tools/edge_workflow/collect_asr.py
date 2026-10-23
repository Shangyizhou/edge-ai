"""Read-only per-precision ASR inference-window aggregation, no models."""

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "edge_benchmark"))
from evaluation_metrics import quality, resource_window


def collect(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    result = []
    for path in sorted(root.glob("*/result.json")):
        d = json.loads(path.read_text())
        resource_path = path.parent / "resources.jsonl"
        samples = [
            json.loads(l) for l in resource_path.read_text().splitlines()
        ]
        events = d["events"]
        windows = []
        start = None
        for e in events:
            if e.get("event") == "phase" and e.get("name") == "inference":
                if e["state"] == "start":
                    start = e["monotonic_seconds"]
                elif start is not None:
                    windows.append(
                        resource_window(
                            samples,
                            start,
                            e["monotonic_seconds"],
                            manifest["cpu_count"],
                            manifest["host_memory"]["MemTotal"],
                        )
                    )
                    start = None
        obs = [
            e
            for e in events
            if e.get("event") == "sample" and e.get("stage") == "inference"
        ]
        q = quality(
            [
                {
                    "case_id": e["fixture"],
                    "reference": e.get("reference"),
                    "transcript": e["final_text"],
                    "output_status": "complete",
                }
                for e in obs
            ]
        )
        valid = [
            w
            for w in windows
            if w["cpu_capacity_percent"]["value"] is not None
        ]
        duration = sum(w["duration_seconds"] for w in valid)
        result.append(
            {
                "candidate": d["id"],
                "samples": len(obs),
                "compute_rtf_median": statistics.median(
                    e["compute_rtf"] for e in obs
                ),
                "cpu_capacity_percent": sum(
                    w["duration_seconds"] * w["cpu_capacity_percent"]["value"]
                    for w in valid
                )
                / duration
                if duration
                else None,
                "peak_pss_mib": max(
                    (
                        w["peak_pss_mib"]["value"]
                        for w in windows
                        if w["peak_pss_mib"]["value"] is not None
                    ),
                    default=None,
                ),
                "inference_windows": len(windows),
                "quality": q,
                "sources": [
                    {
                        "path": str(p),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in [path, resource_path]
                ],
            }
        )
    return {
        "kind": "read-only derived summary of real execution",
        "scope": "3 inference windows per precision; loading/first/warmup/idle excluded; 4-core capacity",
        "cases": result,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    with a.output.open("x") as f:
        json.dump(collect(a.root), f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
