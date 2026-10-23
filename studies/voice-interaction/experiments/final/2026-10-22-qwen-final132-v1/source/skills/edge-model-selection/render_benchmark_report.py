#!/usr/bin/env python3
"""Adapt versioned benchmark results to the project's measured HTML view."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--project", type=Path, required=True,
                        help="edge-ai checkout with the Qwen lifecycle renderer")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for path in args.results:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema") != "edge-model-benchmark/result-v1":
            raise ValueError("expected edge-model-benchmark/result-v1")
    command = [sys.executable, "-m", "tools.qwen_lifecycle", "report"]
    command.extend(str(path.resolve()) for path in args.results)
    command.extend(["--output", str(args.output.resolve())])
    subprocess.run(command, cwd=args.project.resolve(), check=True)


if __name__ == "__main__":
    main()
