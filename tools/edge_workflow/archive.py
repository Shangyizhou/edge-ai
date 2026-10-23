"""Restore a pinned, hash-verified experiment archive outside the checkout."""

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = Path(
    os.environ.get(
        "EDGE_AI_ASSET_ROOT", str(Path.home() / ".local/share/edge-ai")
    )
)
CACHE = ASSET_ROOT / "archive-cache/20261023-v1"
RECEIPT = ROOT / "studies/voice-interaction/datasets/remote-archive.json"


def extract_verified(archive, output, digest):
    archive, output = Path(archive), Path(output)
    if output.exists():
        raise FileExistsError("Use a new restore directory")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError("Archive SHA256 mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp)
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            names = [m.name for m in members]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate archive members")
            for member in members:
                name = Path(member.name)
                if (
                    not member.isfile()
                    or name.is_absolute()
                    or ".." in name.parts
                ):
                    raise ValueError("Unsafe archive member")
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst)
        # Same filesystem: commit the fully restored directory atomically.
        stage.rename(output)
    return len(members)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=CACHE)
    a = p.parse_args()
    from huggingface_hub import hf_hub_download

    receipt = json.loads(RECEIPT.read_text())
    item = receipt["experiments"]
    archive = hf_hub_download(
        receipt["repository"],
        item["file"],
        repo_type="dataset",
        revision=receipt["revision"],
    )
    count = extract_verified(archive, a.output, item["sha256"])
    print("Restored", count, "files to", a.output)


if __name__ == "__main__":
    main()
