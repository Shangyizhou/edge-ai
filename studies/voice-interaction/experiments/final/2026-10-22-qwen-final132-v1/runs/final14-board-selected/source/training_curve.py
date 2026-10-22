"""Plot saved callbacks with matplotlib; no model loading."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    result = json.loads(args.result.read_text())
    fig, axis = plt.subplots(figsize=(7, 3.5), constrained_layout=True)
    for kind, key in (("train", "train_loss"), ("validation", "val_loss")):
        records = [x for x in result["metrics"] if x["kind"] == kind]
        axis.plot(
            [x.get("microstep", x["upstream"]["iteration"]) for x in records],
            [x["upstream"][key] for x in records],
            marker="o",
            label=kind,
        )
    axis.set(
        xlabel="Microstep (8 microsteps per optimizer update)",
        ylabel="Supervised token loss",
        title="Qwen3-0.6B LoRA pilot",
    )
    axis.grid(alpha=0.2)
    axis.legend()
    fig.savefig(args.output)
    plt.close(fig)


if __name__ == "__main__":
    main()
