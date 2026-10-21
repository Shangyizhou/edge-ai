# Repository instructions

## Research records

Before work on a research topic, read its `studies/<topic>/README.md` and its roadmap when present. Keep the topic overview readable as goals, stages, current conclusions and links to evidence.

Record new measurements as new experiments. Preserve historical configurations, raw outputs, manifests, hashes and measurement-source snapshots; update current summaries with links to the relevant evidence. Keep model weights, recordings, SDKs, credentials and build output outside Git.

Distinguish model execution, benchmark results, production integration and complete interaction acceptance. State the input, timing boundary and validation scope behind performance claims. Production sources in other repositories remain maintained there; experiment snapshots here are evidence.

## Agent skills

### Issue tracker

Track work and specifications in GitHub Issues for `Shangyizhou/edge-ai`. Before reading, creating, updating or closing tickets, read [issue tracker conventions](docs/agents/issue-tracker.md).

### Triage labels

Use the five default canonical triage labels. Before classifying issues, read [label vocabulary](docs/agents/triage-labels.md).

### Domain docs

Use a single-context layout: root `GLOSSARY.md` and `docs/adr/`. Before exploring domain terminology or changing module design, read [domain documentation rules](docs/agents/domain.md).
