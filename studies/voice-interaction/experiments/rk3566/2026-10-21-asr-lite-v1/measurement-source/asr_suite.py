"""从共享素材和部署声明生成轻量ASR筛选或三轮复测矩阵。"""

import argparse
import copy
import json
from pathlib import Path

from evaluation import validate_case_config
from evaluation_metrics import ASR_PROTOCOL, NORMALIZATION


def build(config: dict, tier: str) -> dict:
    """两后端复用输入和处理，部署参数各自显式记录。"""
    if tier not in {"screening", "qualification"}:
        raise ValueError("unknown tier")
    fixture_ids = config[tier + "_fixture_ids"]
    if not fixture_ids:
        raise ValueError("empty fixture selection")
    cases = []
    for round_number in range(1, 2 if tier == "screening" else 4):
        for realtime in (False, True):
            # 每轮交替顺序，缓解固定运行顺序影响，仍不声称冷盘测量。
            candidates = config["candidates"][::1 if round_number % 2 else -1]
            for deployment in candidates:
                identity = deployment["identity"]
                case = copy.deepcopy(config["adapter"])
                case.update(copy.deepcopy(deployment["adapter"]))
                case.update(
                    id=f"{identity['id']}-{'rt' if realtime else 'fast'}-r{round_number}",
                    kind="streaming_asr", fixtures=config["fixtures"],
                    fixture_ids=fixture_ids, realtime=realtime,
                    chunk_ms=100, tail_seconds=3.2, idle_seconds=3,
                    endpoint_silence=1.2,
                    evaluation=dict(
                        task="asr", protocol_id=ASR_PROTOCOL, tier=tier,
                        round=round_number, device_id=config["device_id"],
                        candidate=identity, comparison_type=config["comparison_type"],
                        comparison_group=config["comparison_group"],
                        preprocessing="mono16k-pcm16-v1",
                        output_normalization=NORMALIZATION,
                    ),
                )
                if config.get("controls"):
                    case["evaluation"]["controls"] = config["controls"]
                validate_case_config(case)
                cases.append(case)
    return dict(
        python=config["python"], budget_seconds=config[tier + "_budget_seconds"],
        extra_assets=config.get("extra_assets", []), cases=cases,
    )


def main() -> None:
    """只生成和校验矩阵，不执行模型。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--tier", choices=("screening", "qualification"), required=True)
    args = parser.parse_args()
    suite = build(json.loads(args.config.read_text()), args.tier)
    with args.output.open("x") as stream:
        json.dump(suite, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(args.output)


if __name__ == "__main__":
    main()
