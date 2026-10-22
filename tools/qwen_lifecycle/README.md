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
