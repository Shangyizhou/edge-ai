# Triage labels

Use the default canonical vocabulary for GitHub Issues in `Shangyizhou/edge-ai`.

| Canonical role | GitHub label | Meaning |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | Maintainer needs to evaluate the issue |
| `needs-info` | `needs-info` | Waiting for information needed to proceed |
| `ready-for-agent` | `ready-for-agent` | Fully specified and ready for agent implementation |
| `ready-for-human` | `ready-for-human` | Requires human implementation |
| `wontfix` | `wontfix` | Will not be actioned |

Use these exact strings when a skill names a triage role. A triaged issue has one current triage role; remove the superseded role when changing it. Labels describe triage, while GitHub open/closed state describes delivery. Existing category labels such as `bug` and `enhancement` remain independent.

Check existing labels before creating a missing canonical label; preserve unrelated labels and their metadata. This file defines the chosen vocabulary, not proof that all five labels already exist remotely.
