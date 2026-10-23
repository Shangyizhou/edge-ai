"""Versioned dataset references and a derived run index; no model execution."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit


def inside(path, root):
    try:
        Path(path).relative_to(root)
        return True
    except ValueError:
        return False


def samples_digest(rows):
    fields = [
        {k: row[k] for k in ("id", "user", "expected") if k in row}
        for row in rows
    ]
    return hashlib.sha256(
        json.dumps(
            fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "studies/voice-interaction"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve(uri, root=ROOT, asset_root=None):
    """Resolve declared local references; remote locations are never fetched."""
    parsed = urlsplit(uri)
    if parsed.query or parsed.fragment or "@" in parsed.netloc:
        raise ValueError("ambiguous storage reference")
    if parsed.scheme == "repo":
        base = Path(root).resolve()
    elif parsed.scheme == "edge-ai":
        base = Path(
            asset_root
            or os.environ.get(
                "EDGE_AI_ASSET_ROOT", Path.home() / ".local/share/edge-ai"
            )
        ).resolve()
    else:
        return None
    relative = unquote(parsed.netloc + parsed.path).lstrip("/")
    if ".." in Path(relative).parts:
        raise ValueError("reference escapes storage root")
    target = (base / relative).resolve()
    if not inside(target, base):
        raise ValueError("symlink escapes storage root")
    return target


def releases(catalog=STUDY / "datasets/catalog.json"):
    catalog = Path(catalog)
    index = json.loads(catalog.read_text())
    if index.get("schema") != "edge-ai-dataset-catalog/v1":
        raise ValueError("unsupported dataset catalog")
    seen = set()
    for row in index["datasets"]:
        key = (row["id"], row["version"])
        if key in seen:
            raise ValueError("duplicate dataset release")
        seen.add(key)
        path = (catalog.parent / row["manifest"]).resolve()
        if not inside(path, catalog.parent.resolve()):
            raise ValueError("manifest outside catalog")
        data = json.loads(path.read_text())
        if (data["id"], data["version"]) != key:
            raise ValueError("dataset release identity mismatch")
        yield path, data


def verify(
    catalog=STUDY / "datasets/catalog.json",
    include_final=False,
    asset_root=None,
):
    rows = []
    for manifest, dataset in releases(catalog):
        for split, entry in dataset["splits"].items():
            artifact = entry["artifact"]
            state = (
                "not_checked_final"
                if entry["purpose"] == "final_reserved" and not include_final
                else None
            )
            path = resolve(artifact["uri"], asset_root=asset_root)
            if state is None:
                state = (
                    "remote_not_fetched"
                    if path is None
                    else "missing"
                    if not path.is_file()
                    else "verified"
                    if sha(path) == artifact["sha256"]
                    else "mismatch"
                )
            rows.append(
                {
                    "dataset": dataset["id"],
                    "version": dataset["version"],
                    "split": split,
                    "status": state,
                    "sha256": artifact["sha256"],
                }
            )
    return rows


def build_index(output, catalog=STUDY / "datasets/catalog.json"):
    dataset_map = {}
    for manifest, data in releases(catalog):
        for split, record in data["splits"].items():
            dataset_map.setdefault(record["artifact"]["sha256"], []).append(
                {
                    "dataset": data["id"],
                    "version": data["version"],
                    "split": split,
                    "purpose": record["purpose"],
                }
            )
    sample_map = {}
    for manifest, data in releases(catalog):
        for split, record in data["splits"].items():
            if record.get("samples_sha256"):
                sample_map.setdefault(record["samples_sha256"], []).append(
                    {
                        "dataset": data["id"],
                        "version": data["version"],
                        "split": split,
                        "purpose": record["purpose"],
                    }
                )
    rows = []
    ignored = {
        "source",
        "implementation-source",
        "business-source",
        "external-inputs",
        "execution-source",
    }
    schemas = {
        "edge-ai-experiment/result-v1",
        "edge-model-benchmark/result-v1",
        "edge-model-finetune/result-v1",
        "edge-model-export/result-v1",
    }
    for path in sorted(
        (STUDY / "experiments").rglob("results.json"),
        key=lambda p: (len(p.parts), str(p)),
    ):
        if ignored.intersection(path.relative_to(STUDY).parts):
            continue
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get("schema") not in schemas:
            continue
        # An owned launcher/wrapper result already represents nested raw results.
        parent = next(
            (
                row
                for row in rows
                if inside(path, ROOT / row["run_directory"])
                and path.parent != ROOT / row["run_directory"]
            ),
            None,
        )
        if parent:
            continue
        request = next(
            (
                path.parent / n
                for n in [
                    "adapter-request.json",
                    "request.json",
                    "launcher-request.json",
                ]
                if (path.parent / n).exists()
            ),
            None,
        )
        sources = [data.get("suite_sha256")]
        sources.extend(
            data.get("dataset", {}).get(k)
            for k in ["train_sha256", "valid_sha256"]
        )
        if data.get("schema") == "edge-ai-experiment/result-v1":
            raw = path.parent / "raw/results.json"
            if raw.exists():
                sources.append(json.loads(raw.read_text()).get("suite_sha256"))
            plan = path.parent / "plan.json"
            if plan.exists():
                sources.append(
                    json.loads(plan.read_text()).get("suite_sha256")
                )
        bindings = [
            b
            for digest in sources
            if digest
            for b in dataset_map.get(digest, [])
        ]
        resolution = (
            "content_hash_match"
            if bindings
            else "unregistered_or_not_applicable"
        )
        actual = data
        if (
            data.get("schema") == "edge-ai-experiment/result-v1"
            and (path.parent / "raw/results.json").exists()
        ):
            actual = json.loads((path.parent / "raw/results.json").read_text())
        if (
            not bindings
            and actual.get("cases")
            and all("user" in c and "expected" in c for c in actual["cases"])
        ):
            bindings = sample_map.get(samples_digest(actual["cases"]), [])
            if bindings:
                resolution = "canonical_samples_match; prompt/tools/controls remain request-bound"
        candidate = data.get("candidate", data.get("base_artifact", {}))
        if request and not candidate:
            candidate = json.loads(request.read_text()).get("candidate", {})
        request_data = json.loads(request.read_text()) if request else {}
        controls = request_data.get(
            "train_config", request_data.get("generation", {})
        )
        snapshot = next(
            (
                p
                for p in [
                    path.parent / "source",
                    path.parent / "raw/source",
                    path.parent / "raw/measurement/source",
                ]
                if p.is_dir()
            ),
            None,
        )
        code = (
            {
                "status": "snapshot_available",
                "path": str(snapshot.relative_to(ROOT)),
            }
            if snapshot
            else {"status": "not_recorded_in_run"}
        )
        rows.append(
            {
                "controls": controls,
                "code": code,
                "id": data["run_id"],
                "run_directory": str(path.parent.relative_to(ROOT)),
                "result": str(path.relative_to(ROOT)),
                "result_sha256": sha(path),
                "request": str(request.relative_to(ROOT)) if request else None,
                "request_sha256": sha(request) if request else None,
                "schema": data["schema"],
                "status": data.get("status", "not_declared"),
                "source": data.get("source", {}).get("kind", "not_declared"),
                "datasets": bindings,
                "dataset_resolution": resolution,
                "model": {
                    k: candidate[k]
                    for k in [
                        "model",
                        "revision",
                        "precision",
                        "backend",
                        "lineage",
                    ]
                    if k in candidate
                },
                "summary": data.get("summary", {}),
                "note": "Run completion is not model acceptance; unresolved historical bindings stay explicit.",
            }
        )
    output = Path(output)
    output.write_text(
        json.dumps(
            {
                "schema": "edge-ai-experiment-index/v1",
                "origin": "derived from immutable saved results; no new inference",
                "runs": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("verify")
    p.add_argument("--include-final", action="store_true")
    p = sub.add_parser("index")
    p.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        rows = verify(include_final=args.include_final)
        print(json.dumps(rows, indent=2))
        if any(r["status"] in ("missing", "mismatch") for r in rows):
            raise SystemExit(2)
    else:
        print("Indexed", len(build_index(args.output)), "saved runs")


if __name__ == "__main__":
    main()
