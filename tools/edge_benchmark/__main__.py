"""独立于 Skill 的离线计划、真实执行与补同步命令。"""

import argparse
import os
from pathlib import Path

from .execution import run_plan
from .experiment import freeze


def main() -> None:
    """只有 run 执行模型；sync 永远只读取已有结果。"""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        command = sub.add_parser(name)
        command.add_argument("input", type=Path)
        command.add_argument("--output", type=Path, required=True)
    sync = sub.add_parser("sync")
    sync.add_argument("directory", type=Path)
    parser.add_argument(
        "--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI")
    )
    args = parser.parse_args()
    if args.command == "plan":
        plan = freeze(args.input, args.output)
        print(
            f"{plan['maximum_requests']} requests maximum; "
            f"budget {plan['request']['budget']['total_seconds']}s"
        )
        print(args.output / "plan.json")
        return
    # MLflow 不安装时 plan 仍可用；同步只在控制端读取结果。
    from tools.experiment_tracking.record_execution import synchronize

    if args.command == "run":
        result = run_plan(args.input, args.output)
        directory = args.output
    else:
        result = None
        directory = args.directory
    if args.tracking_uri:
        synchronize(directory, args.tracking_uri)
    else:
        print("Saved locally; set MLFLOW_TRACKING_URI and use sync later.")
        if args.command == "sync":
            raise SystemExit(2)
    if result and result["status"] != "completed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
