"""Independent split audit; report identities/counts, never final example text."""

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(index):
    data = json.loads(Path(index).read_text())
    groups = {}
    prompts = {}
    issues = []
    counts = {}
    sources = []
    for split, value in data["files"].items():
        path = Path(value)
        payload = path.read_bytes()
        sources.append({"split": split, "sha256": sha(path)})
        rows = (
            [
                json.loads(line)
                for line in payload.decode().splitlines()
                if line.strip()
            ]
            if path.suffix == ".jsonl"
            else json.loads(payload)["samples"]
        )
        counts[split] = len(rows)
        for row in rows:
            group = row["source_group"]
            if group in groups and groups[group] != split:
                issues.append("cross-split source family")
            groups[group] = split
            user = row.get("user") or next(
                m["content"] for m in row["messages"] if m["role"] == "user"
            )
            key = re.sub(r"[\W_]+", "", user, flags=re.UNICODE)
            if key in prompts and prompts[key] != split:
                issues.append("normalized exact user text crosses splits")
            prompts[key] = split
    return {
        "schema": "edge-ai-data-audit/v1",
        "status": "passed" if not issues else "failed",
        "counts": counts,
        "groups": len(groups),
        "sources": sources,
        "issues": sorted(set(issues)),
        "scope": "Declared source-group and normalized exact text audit; semantic independence and unknown base pretraining contamination not proved",
        "access": "Separate audit reads all split files; final contents are not returned or exported to training",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("index", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    d = audit(a.index)
    with a.output.open("x") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    if d["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
