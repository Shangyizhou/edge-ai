# Task/data workflow project adapters

Reusable capabilities live in personal-skills and are installed under
`~/.codex/skills/edge-ai-*`. This project owns task recipes, actual model
calls and experiment evidence. No new Skill is added.

- `pilot_data`: a machine-specific Qwen synthetic pilot recipe, requiring
  fresh `--assets` and `--evidence` directories. It binds the frozen nine
  actual tool schemas; it is not a general dataset generator or a natural
  user distribution. Do not regenerate into existing experiment paths.
- `audit_data`: independent declared-group/exact-text audit. It reads
  splits separately and returns counts/hashes/issues, not final questions.
  Semantic independence and base-pretraining contamination remain unproved.
- `guarded`: one owned subprocess tree under a time/memory guard. It never
  stops unrelated model servers.
- `qwen_adapter`: actual owned-server smoke before formal Qwen inference.
  Source, outputs, finish state and resource records remain inspectable.
- `asr_adapter`: actual sherpa ASR calls using the existing worker and
  sampler. It uses `compute_seconds`/`compute_rtf` events and does not pass
  these through the legacy `seconds`-based report renderer.
- `collect_asr`: saved-event inference-window aggregation, excluding
  loading, first request, warmup and idle. It does not rerun recognition.

Public reusable entry points:

```sh
python ~/.codex/skills/edge-ai-train/scripts/prepare_data.py REQUEST NEW_DIR
python ~/.codex/skills/edge-ai-benchmark/scripts/prepare_evaluation.py REQUEST NEW_DIR
python ~/.codex/skills/edge-ai-prepare/scripts/render_workflow_readiness.py REQUEST CHECKS NEW_DIR
python ~/.codex/skills/edge-ai-prepare/scripts/check_experiment.py REQUEST NEW_RESULT.json
python ~/.codex/skills/edge-ai-benchmark/scripts/run_experiment.py REQUEST NEW_DIR --dry-run
python ~/.codex/skills/edge-ai-benchmark/scripts/run_experiment.py REQUEST NEW_DIR
python ~/.codex/skills/edge-ai-benchmark/scripts/render_experiment_report.py REQUEST NEW_DIR
```

Tool-target data validation needs jsonschema; use the isolated model runtime
or another explicit environment containing it. Reports and evaluation
preparation use stdlib only. Data freezing means an immutable reviewed input
snapshot and structural checks; the training adapter must still pass actual
tokenizer/template length and assistant-mask preflight before optimization.

The experiment runner calls an explicit adapter argv, never a shell. Frozen
suite identity and task-specific raw evidence bind the handoff; source flags
alone cannot authenticate measurements. It does not infer model compatibility
or implement arbitrary new task scoring.

Training/validation/development/final are uses, not trust guaranteed by a
filename or folder. Train gets learning sources and reserved group IDs, not
final examples. A shared filesystem or one agent context is not a blind-test
security boundary. Former final cases used for development stay regression
cases. Scores do not prove device actions, ROS co-running or product readiness.

Verification evidence is in the 2026-10-23 workflow experiment directories.
Read failures and scope before reusing any result. Do not overwrite historical
raw results or auto-promote this 32-microstep technical model.

## 长期管理

`registry.py` 验证数据清单并派生实验索引；`backup.py` 创建外部数据备份及恢复到新目录；`report.py` 从冻结证据生成正式展示副本。参见 [数据目录约定](../../studies/voice-interaction/datasets/README.md) 与 [Pages 发布边界](../research_site/README.md)。这些命令不会训练或执行模型。
