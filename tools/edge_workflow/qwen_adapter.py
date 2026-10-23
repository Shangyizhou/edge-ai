"""New-artifact smoke before measured owned-server Qwen regression."""

import argparse
import copy
import hashlib
import json
import platform
import shutil
from pathlib import Path

from tools.qwen_lifecycle.benchmark import write_json
from tools.qwen_lifecycle.server_lifecycle import execute as server_execute


def execute(request_path, output):
    d = json.loads(Path(request_path).read_text())
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    probe = (
        ("otool", ["otool", "-L"])
        if platform.system() == "Darwin"
        else ("ldd", ["ldd"])
    )
    smoke = copy.deepcopy(d)
    smoke["run_id"] = d["run_id"] + "-preparation"
    suite = json.loads(Path(d["suite_ref"]).read_text())
    suite["samples"] = suite["samples"][:1]
    smoke.pop("suite_ref")
    smoke["suite"] = suite
    first = server_execute(smoke, output / "smoke", probe)
    ready = (
        first.get("status") != "failed"
        and len(first.get("cases", [])) == 1
        and first["cases"][0]["status"] == "completed"
    )
    write_json(
        output / "preparation.json",
        {
            "status": "FUNCTIONAL_READY" if ready else "NOT_READY",
            "candidate": d["candidate"],
            "smoke_result_sha256": hashlib.sha256(
                (output / "smoke/results.json").read_bytes()
            ).hexdigest(),
            "scope": "new artifact actual generation before formal suite; does not imply output quality acceptance",
        },
    )
    if not ready:
        raise RuntimeError(
            "new-artifact smoke failed; formal benchmark not launched"
        )
    result = server_execute(d, output / "measurement", probe)
    result["evidence"] = [
        dict(e, path="measurement/" + e["path"])
        for e in result.get("evidence", [])
    ]
    if result.get("benchmark_result"):
        result["benchmark_result"]["path"] = (
            "measurement/" + result["benchmark_result"]["path"]
        )
    result["source"]["raw_evidence"] = (
        "measurement/benchmark/cases and events; smoke separate"
    )
    write_json(output / "results.json", result)
    shutil.copyfile(output / "measurement/report.html", output / "report.html")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("request", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    execute(a.request, a.output)


if __name__ == "__main__":
    main()
