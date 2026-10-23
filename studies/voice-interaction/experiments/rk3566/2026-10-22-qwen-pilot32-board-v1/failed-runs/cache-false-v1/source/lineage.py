"""Freeze collector bytes before a mutable-worktree experiment."""

import shutil
from pathlib import Path

from .benchmark import file_hash


def freeze_sources(output, names):
    target = Path(output) / "collector-source"
    target.mkdir()
    records = []
    for name in names:
        source = Path(__file__).with_name(name)
        shutil.copy2(source, target / name)
        records.append(
            {
                "path": "collector-source/" + name,
                "sha256": file_hash(target / name),
            }
        )
    return records
