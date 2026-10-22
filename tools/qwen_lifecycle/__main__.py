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
    for name in ("finetune", "export"):
        command = sub.add_parser(name)
        command.add_argument("request", type=Path)
        command.add_argument("output", type=Path)
    stages = sub.add_parser("stage-report")
    stages.add_argument("results", type=Path, nargs="+")
    stages.add_argument("--output", type=Path, required=True)
    stages.add_argument("--loss-plot", type=Path)
    stages.add_argument("--inference-report")
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
            render([result], bundle.getvalue()), encoding="utf-8"
        )
        print(args.output / "report.html")
        if result.get("status") == "failed":
            raise SystemExit(1)
    elif args.command in ("finetune", "export"):
        from .stages import export, render_stages
        from .training import train

        execute = train if args.command == "finetune" else export
        result = execute(read_json(args.request), args.output)
        (args.output / "report.html").write_text(
            render_stages([result]), encoding="utf-8"
        )
        print(args.output / "report.html")
        if result.get("status") == "failed":
            raise SystemExit(1)
    elif args.command == "stage-report":
        from .stages import render_stages

        plot = args.loss_plot.read_bytes() if args.loss_plot else None
        args.output.write_text(
            render_stages(
                [read_json(p) for p in args.results],
                plot,
                args.inference_report,
            ),
            encoding="utf-8",
        )
        print(args.output)
    else:
        args.output.write_text(
            render([read_json(p) for p in args.results]), encoding="utf-8"
        )
        print(args.output)


if __name__ == "__main__":
    main()
