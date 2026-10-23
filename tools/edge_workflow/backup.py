"""Verified dataset snapshots and restore-to-new-directory; never overwrites data."""

import argparse
import io
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

from .registry import releases, resolve, sha


def create(output, catalog=None, include_final=False):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    entries = []
    for manifest, dataset in releases(catalog) if catalog else releases():
        for split, record in dataset["splits"].items():
            if record["purpose"] == "final_reserved" and not include_final:
                continue
            artifacts = [("data", record["artifact"])] + [
                (item["id"], item["replica"])
                for item in record.get("media", [])
                if item.get("replica")
            ]
            for suffix, item in artifacts:
                path = resolve(item["uri"])
                if (
                    path is None
                    or not path.is_file()
                    or sha(path) != item["sha256"]
                ):
                    raise ValueError("missing or mismatched backup input")
                name = "/".join(
                    [
                        dataset["id"],
                        dataset["version"],
                        split,
                        suffix + path.suffix,
                    ]
                )
                entries.append(
                    {
                        "member": name,
                        "sha256": item["sha256"],
                        "bytes": path.stat().st_size,
                        "uri": item["uri"],
                        "path": str(path),
                    }
                )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            for row in entries:
                archive.add(
                    row["path"], arcname=row["member"], recursive=False
                )
            payload = json.dumps(
                [
                    {k: v for k, v in row.items() if k != "path"}
                    for row in entries
                ],
                sort_keys=True,
            ).encode()
            info = tarfile.TarInfo("backup-index.json")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return {
        "sha256": sha(output),
        "files": len(entries),
        "bytes": output.stat().st_size,
        "includes_final": include_final,
    }


def restore(archive_path, output, expected_sha256):
    archive_path = Path(archive_path)
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    if sha(archive_path) != expected_sha256:
        raise ValueError("archive identity mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary)
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            names = [x.name for x in members]
            if len(names) != len(set(names)) or any(
                not x.isfile()
                or Path(x.name).is_absolute()
                or ".." in Path(x.name).parts
                for x in members
            ):
                raise ValueError("unsafe archive members")
            index = json.loads(archive.extractfile("backup-index.json").read())
            expected = {row["member"]: row for row in index}
            if len(index) != len(expected) or set(names) != set(expected) | {
                "backup-index.json"
            }:
                raise ValueError("archive contents differ from index")
            for member in members:
                if member.name == "backup-index.json":
                    continue
                target = stage / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open(
                    "xb"
                ) as destination:
                    shutil.copyfileobj(source, destination)
                row = expected[member.name]
                if (
                    target.stat().st_size != row["bytes"]
                    or sha(target) != row["sha256"]
                ):
                    raise ValueError("restored content mismatch")
        output.mkdir(exist_ok=False)
        for child in stage.iterdir():
            shutil.move(str(child), str(output / child.name))
    return {
        "status": "verified_restore",
        "files": len(index),
        "archive_sha256": expected_sha256,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("create")
    q.add_argument("output", type=Path)
    q.add_argument("--include-final", action="store_true")
    q = sub.add_parser("restore")
    q.add_argument("archive", type=Path)
    q.add_argument("output", type=Path)
    q.add_argument("--sha256", required=True)
    a = p.parse_args()
    print(
        json.dumps(
            create(a.output, include_final=a.include_final)
            if a.command == "create"
            else restore(a.archive, a.output, a.sha256),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
