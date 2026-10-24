# Local experiment tracking and fixed-version notes

This toolkit indexes historical edge experiments in MLflow and generates a compact version card. It never trains a model, re-runs inference, executes robot tools, uploads HF data, or deploys a model. The current public change contains code and a sanitized version summary; private catalog records, samples, binding IDs, databases and model files are not included.

## Responsibilities

- Existing `studies/voice-interaction/datasets/` manifests remain the dataset inventory; experiment catalog dataset entries reference content digests rather than duplicating sample data.
- Frozen experiment directories preserve configurations, outputs, measurements, source snapshots and original HTML.
- The local catalog groups dataset, training, model and evaluation metadata using stable project IDs. MLflow IDs live in a separate local binding table.
- MLflow retains parameters, curves, checkpoints and per-case evidence. Release tags distinguish selection, validation and historical deployment.
- Decision Markdown explains hypotheses and results; version notes are generated from those notes and frozen catalog metrics. HTML is an optional presentation, not a report to hand-maintain for every run.
- HF stays the artifact/dataset store at pinned commits. Remote review-package generation is not publication. The selected newer Q4 must not be confused with older files already in HF.

## Local configuration

Python3.9+ is required for the standard-library tools. MLflow3.1.4 is the tested optional tracking runtime; install it in an isolated environment. `requirements.lock` captures the original local runtime, not training dependencies. Frontend patching below only supports exactly3.1.4.

| Variable | Default |
|---|---|
| `EDGE_AI_STATE_DIR` | `~/.local/share/edge-ai/mlflow` |
| `EDGE_AI_CATALOG_DIR` | `studies/voice-interaction/catalog` (private, ignored) |
| `EDGE_AI_RELEASES_DIR` | `studies/voice-interaction/releases` |

Restore private inputs separately from reviewed archive manifests before importing actual historical evidence. Legacy import scripts are explicit project-specific migration adapters, not recursive scanners or a general training collector. They refuse missing or changed evidence. Neither the CLI nor tests download private inputs automatically.

```sh
python3 tools/experiment_tracking/import_history.py --dry-run
# After restoring the explicit frozen historical inputs and existing import records:
python3 tools/experiment_tracking/migrate_catalog.py
python3 tools/experiment_tracking/build_dashboard.py
```

`catalog.py` checks source/index hashes, unique identities, confined paths, dangling references and cycles. Presentation rebuilds can work without old migration caches. The runtime binding is `<state>/bindings/catalog-mlflow.json`; do not commit it. Source execution timestamps and import timestamps are distinct. Seen-training replay and repeatedly observed development scores are distinct from independent-test results.

## Native MLflow and release notes

```sh
# These commands require the restored private catalog and local MLflow installation:
python tools/experiment_tracking/configure_native.py
python tools/experiment_tracking/release.py --sync-mlflow
python tools/experiment_tracking/start_local.py
```

Both services bind loopback only. Native MLflow is port5001; the optional local comparison UI is port5002. Parameter summaries reference the latest measured development checkpoint, never silently select the best score. The process tree remains available. `current-selected` expresses a user choice, not quality acceptance or deployment authorization.

The release schema links source training, data digests, selected/reference/source-adapter models, frozen evaluations, HF commits and code evidence. Execution code identity comes from measurement snapshots, not the current checkout HEAD. Unknown precision stays unknown. `release.py` writes the local model card, optional HTML and a remote-review bundle without publishing it. The public [version summary](../../studies/voice-interaction/releases/xiaomo-qwen3-0.6b-r1/MODEL_CARD.md) records the existing result and limitations; its private generator inputs are restored separately.

## Optional native frontend patch

`patch_native_frontend.py` adds experiment1's curated training/model defaults and model-column persistence to the local MLflow3.1.4 frontend. It backs up the original entrypoint/assets and generates content-addressed filenames; no server authorization or networking setting changes. Existing bundled source maps no longer describe the few patched expressions. Do not apply it to another version without adaptation. Restore with:

```sh
python tools/experiment_tracking/patch_native_frontend.py --restore
```

The patch is optional; ordinary MLflow tracking does not require it. `inventory_cleanup.py` only annotates explicit local cache/log candidates and never deletes files. Raw experiments, weights, datasets and service logs are not disposable because a catalog exists.

## Verification and publication

```sh
python3 -m unittest discover -s tools/experiment_tracking -v
python3 -m unittest discover -s tools/research_site -p 'test_*.py' -v
```

Portable tests use synthetic metadata. Historical integration checks skip when private evidence is absent; with the owner's restored evidence they validate250 cases, checkpoint lineage and fixed release hashes. The existing SHA256 publication allowlist is unchanged; no catalog, localhost page or unreviewed HTML is added to Pages by this PR. Publishing HF cards, pushing subsequent changes or publishing a site remains separate from indexing results.
