# Qwen lifecycle experiment adapter

The reusable Skills define handoffs; this project owns Qwen3/MLX-LM and
llama.cpp execution, native intake, resource sampling and the measured view.
The public seam ends at pure application Registry validation, never execution.

Use the isolated model runtime Python with `psutil`, `jsonschema`, and MLX-LM
for the Metal adapter. The HTTP adapter uses a prepared llama-server and must
set `runner.monitor_pid` to the actual local model server PID so CPU/RAM are
not incorrectly measured on the client alone.

```sh
python -m tools.qwen_lifecycle benchmark REQUEST.json NEW_OUTPUT_DIRECTORY
python -m tools.qwen_lifecycle report RESULTS.json --output report.html
python -m unittest tools.qwen_lifecycle.test_lifecycle -v
```

Low-rank training and artifact transformations use separate explicit commands:

```sh
python -m tools.qwen_lifecycle finetune TRAIN_REQUEST NEW_RUN
python -m tools.qwen_lifecycle export EXPORT_REQUEST NEW_RUN
python -m tools.qwen_lifecycle stage-report TRAIN_RESULTS EXPORT_RESULTS --output stages.html --loss-plot loss.svg
```

Finetune request/result schemas are `edge-model-finetune/request-v1` and
`edge-model-finetune/result-v1`. A request identifies `base_artifact`,
`dataset.train_ref` / `dataset.valid_ref`, and `train_config`. JSONL examples
carry `id`, `source_group`, tools and messages ending in their assistant target.
The preflight validates targets, rejects train/valid source or exact-prompt
leakage and over-length sequences, and proves the nonthinking inference-prefix
loss mask before loading the optimizer. Both NumPy shuffle and MLX are seeded;
microsteps and optimizer-update counts are recorded separately. The final
independent test set is not an input to training.

Export request/result schemas are `edge-model-export/request-v1` and
`edge-model-export/result-v1`. Explicit operations reference prior artifact IDs,
argv and new output IDs/locations. Costs are measured around the transformation
process, separately from manifest hashing. The chain stops on its first failed
operation and the CLI returns failure while retaining logs/results. Weights
remain external to the evidence run. Each output still needs preparation
loading/smoke and separate capability evaluation.

For Qwen3, use ordinary MLX fuse, then the full pinned llama.cpp converter and
quantizer. The direct MLX GGUF exporter rejects Qwen3. Keep converter and MLX
dependencies isolated. `convert_hf` stages immutable merged tensors with
canonical base tokenizer assets after proving vocabulary and native
nonthinking prompt equality; this handles the observed TF5 tokenizer-save /
TF4 converter incompatibility without rewriting either source artifact.

Training and transformation commands freeze collector source before execution.
`stage-report` only reads saved data; its optional SVG loss plot is generated
by `training_curve` using matplotlib in a separate plotting environment. The
training table retains raw callback payloads; the normalized validation
microstep accounts for the upstream zero-based validation counter.

The request schema is `edge-model-benchmark/request-v1`; inspect the frozen
Mac baseline request and suite for a complete working example. It identifies
candidate/model/runtime/backend/precision, generation controls, source-grouped
suite, and the optional exact `registry_validator` argv. The validator reads
`{"calls":[{"call_id":"...","name":"...","arguments":{}}]}` from stdin and
returns `{"passed":true|false,...}` without invoking handlers.

Output is `edge-model-benchmark/result-v1`, a frozen expanded request/suite,
asset hashes, per-case results/events/resource samples, and offline HTML.
A new directory is required. Failures/truncation stay in the denominator;
fixtures are explicitly synthetic and cannot satisfy real-model handoff.

Generation throughput retains native runtime counter boundaries. MLX's prompt
time includes the first sampled token and generation count can include EOS.
Valid-call latency spans template, generation, parsing and pure validation.
Loading is separate. Sampled CPU covers the declared process tree divided by
logical host capacity. Mac RSS and MLX allocated memory are distinct,
potentially overlapping quantities; Linux PSS is separate. No available field
is invented for another platform.

`report` is read-only and imports no MLX runtime. A combined HTML embeds result
JSON; each run's generated HTML also carries a zip of raw JSON evidence. It
follows the existing approved layout without modifying historical reports.

For isolated Linux CPU preparation and benchmarking, run
`python -m tools.qwen_lifecycle.board_run REQUEST NEW_OUTPUT` on the board.
The request adds `server.binary`, `server.port` and explicit `server.argv`
(threads, batch/microbatch, context, KV and CPU backend flags). The launcher
binds loopback, records binary/ldd/source/loading evidence, checks every complete
rendered prompt plus output budget, monitors its own model server, and stops
only that owned process. Existing servers and production environments are not
modified. Python 3.8 works with isolated compatible psutil/jsonschema/Pydantic.

HTTP prompt caching is opt-in via `generation.cache_prompt` (default false).
`prompt_tokens` uses full native usage when emitted; `evaluated_prefill_tokens`
retains `timings.prompt_n`, with raw usage/timings saved separately. Cached
prefill rate uses evaluated tokens, never the full prompt length. Keep cache
conditions in separate run groups. Linux raw samples include thermal-zone
readings when available and system-wide swap-in/out counters; their deltas
cannot be attributed solely to the model process.
