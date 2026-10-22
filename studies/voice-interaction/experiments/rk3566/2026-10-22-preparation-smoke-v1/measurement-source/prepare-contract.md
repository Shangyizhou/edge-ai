# Preparation contract v1

## Input: edge-model-prepare/request-v1

`handoff` accepts a selection JSON with `device`, `requirements` and `candidates`. Each candidate has `id` (or an ID derived from its original index), `name`, `decision`, `model`, `artifact`, `runtime`, `backend`, `precision`, optional `evidence` and `test_focus`.

The generated request contains `schema`, `device`, `requirements`, `source_selection_sha256` and `candidates`. Preserve original candidate IDs and technical identities. The SHA256 identifies the actual input bytes; it is not an artifact/model hash. Carry hardware/BSP/driver gaps forward. The adapter copies candidates; it does not turn prose into independently verified versions.

Manual requests can use the same schema. Runtime-specific adapters/configurations remain with the benchmark project; this skill coordinates preparation and reporting rather than implementing every inference engine.

## Check evidence: edge-model-prepare/checks-v1

Top-level fields:

- `schema`: `edge-model-prepare/checks-v1`.
- `request_sha256`: SHA256 of the actual request file; ties observations to one handoff.
- `evidence`: unique IDs with `kind`, `location`, `sha256` and `description`. Location may refer to a project-relative record or an external asset manifest. Keep credentials out. SHA256 is the referenced evidence file's hash, not a label guessed from a filename.
- `candidates`: exactly one entry per requested ID, with `acquisition`, `checks`, `benchmark_configs`, `next_action`.

`acquisition` records `model` (`reuse` or `download`), `runtime` (`reuse`, `binary`, `build`) and `reason`. Building must explain why binaries/reuse were unsuitable or why that exact build was required.

Each check has `status` (`PASS`, `FAIL`, `UNKNOWN`, `NOT_RUN`), `reason`, and `evidence` (list of evidence IDs). PASS and FAIL require at least one evidence reference. Evidence is an observation reference; a JSON PASS alone does not independently verify its truth.

`benchmark_configs` lists evidence IDs with kind `benchmark_config`, each pointing to a frozen executable configuration. Benchmark PASS requires at least one. Smoke PASS requires a reference of kind `smoke`; loading-only evidence cannot satisfy it. Other kinds describe assets, runtime, load and benchmark-tool checks. The next-stage handoff includes ready candidate identities and their configuration evidence.

Four required gates:

| Key | PASS means |
| --- | --- |
| `assets` | Exact model and companion assets exist, provenance/license and hashes checked |
| `runtime` | Actual binary, libraries, architecture, backend and ABI checked |
| `smoke` | Small real inference produced inspectable task-appropriate output |
| `benchmark` | Benchmark configuration, inputs and capture tools resolve against the frozen protocol |

Optional `load` check records constructor/health success separately. Unknown driver compatibility matters only for a requested backend that uses that driver. A CPU-only request need not be held up by an unrelated NPU gap.

## Output: edge-model-prepare/readiness-v1

The reporter derives each candidate status, in dependency order:

1. A failed required gate (or failed load check) → `NOT_READY`.
2. Assets/runtime incomplete → `NOT_READY`.
3. Assets/runtime pass, smoke incomplete, load passes → `LOADED_ONLY`.
4. Assets/runtime pass, smoke incomplete, no load proof → `ENVIRONMENT_READY`.
5. Assets/runtime/smoke pass, benchmark incomplete → `FUNCTIONAL_READY`.
6. All four required gates pass → `READY_FOR_BENCHMARK`.

Overall `READY_FOR_BENCHMARK` requires all requested candidates ready. A mix containing at least one ready candidate is `PARTIALLY_READY`; otherwise overall is `NOT_READY`. Display the per-candidate intermediate states so overall NOT_READY does not hide completed work. Only candidates with `READY_FOR_BENCHMARK` enter `benchmark_handoff.candidates`.

Outputs preserve source identities, checks, evidence and next actions. `evidence_verification` is `references_only`; the renderer checks cross-references and hash syntax, not the referenced filesystem or inference itself. Product acceptance remains `NOT_EVALUATED`. The HTML has no network dependencies and escapes user/model strings; regeneration executes no models.

A schema/integrity error fails report generation. A deployment failure is valid report data: render FAIL and its evidence. Neither a mock nor an illustrative successful sample can promote a real candidate.
