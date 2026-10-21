# Domain documentation

## Read before exploring or designing

Read root [GLOSSARY.md](../../GLOSSARY.md) before exploring domain terminology or designing a module. Read the relevant decisions under [docs/adr/](../adr/). Use the glossary's established terms in issues, research summaries, code and tests.

This repository uses a **single-context** layout. Voice interaction and object detection are research topics within the shared model evaluation vocabulary; separate topic directories do not require separate domain contexts.

```text
GLOSSARY.md
docs/adr/
studies/<topic>/
```

If a referenced glossary or ADR does not yet exist, continue with the task. Apply `domain-modeling` when terms or decisions have actually been resolved. Create additional glossary entries or ADRs as needed, rather than filling speculative placeholders.

## What belongs where

- `GLOSSARY.md`: concise domain definitions, without implementation decisions or task status.
- `docs/adr/NNNN-short-title.md`: resolved architectural decisions with context, trade-offs and consequences. Record an ADR when the decision is costly to reverse, surprising without context and the result of a real trade-off.
- GitHub Issues: specifications, acceptance criteria and work tracking, as defined in [issue-tracker.md](issue-tracker.md).
- `studies/<topic>/`: research conclusions, stages, deployment procedures and detailed measurement evidence.

If proposed work conflicts with an accepted ADR, identify the decision and explain why it should be revisited before changing it. Keep the glossary's wording aligned with resolved domain concepts; do not copy current performance numbers into definitions.
