"""Explicit commands: benchmark executes models; report only reads evidence."""

import argparse
import io
import zipfile
from pathlib import Path

from .benchmark import read_json, run
from .report import render


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("request", type=Path)
    benchmark.add_argument("output", type=Path)
    report = sub.add_parser("report")
    report.add_argument("results", type=Path, nargs="+")
    report.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "benchmark":
        request = read_json(args.request)
        result = run(request, args.output)
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(args.output.rglob("*.json")):
                archive.write(file, str(file.relative_to(args.output)))
        (args.output / "report.html").write_text(
            render([result], bundle.getvalue()), encoding="utf-8")
        print(args.output / "report.html")
    else:
        args.output.write_text(render([read_json(p) for p in args.results]),
                               encoding="utf-8")
        print(args.output)


if __name__ == "__main__":
    main()
