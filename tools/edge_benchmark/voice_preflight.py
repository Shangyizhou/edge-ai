"""Verify frozen v2 assets before execution; never loads a model."""

import argparse
import hashlib
import json
from pathlib import Path


def verify(directory):
    records = json.loads((directory / "assets-manifest.json").read_text())
    runtime = json.loads((directory / "runtime-manifest.json").read_text())
    paths = {}
    for row in records + runtime["files"]:
        paths[row["path"]] = row["sha256"]
    fixtures = json.loads((directory / "asr-fixtures.json").read_text())[
        "fixtures"
    ]
    for row in fixtures:
        paths[row["path"]] = row["sha256"]
    errors = []
    for name, expected in paths.items():
        p = Path(name)
        if not p.is_file():
            errors.append("missing " + name)
            continue
        h = hashlib.sha256()
        with p.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        if h.hexdigest() != expected:
            errors.append("hash mismatch " + name)
    for module in ("asr", "tts", "llm"):
        suite = json.loads(
            (directory / (module + "-screening.json")).read_text()
        )
        if suite["budget_seconds"] != 600:
            errors.append(module + " budget mismatch")
        for c in suite["cases"]:
            if c["min_memavailable_mib"] != 600:
                errors.append(c["id"] + " guard mismatch")
            required = [
                c[k]
                for k in ("encoder", "decoder", "joiner", "tokens", "binary")
                if k in c
            ]
            if c["kind"] == "llama":
                required.append(c["model"])
            if "vits" in c:
                required.extend(
                    v for v in c["vits"].values() if Path(v).is_file()
                )
                required.extend(c["tts_config"]["rule_fsts"].split(","))
                required.extend(
                    str(f)
                    for f in Path(c["vits"]["dict_dir"]).rglob("*")
                    if f.is_file()
                )
            for filename in required:
                if filename not in paths:
                    errors.append("unfrozen dependency " + filename)
    return {
        "status": "READY_FOR_SCREENING" if not errors else "NOT_READY",
        "errors": errors,
        "checked_files": len(paths),
        "scope": "hash/configuration verification only; no inference or benchmark acceptance",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = verify(args.directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not result["errors"] else 1)


if __name__ == "__main__":
    main()
