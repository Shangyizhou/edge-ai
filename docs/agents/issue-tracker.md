# Issue tracker: GitHub

Issues and specifications for this repository live in [Shangyizhou/edge-ai Issues](https://github.com/Shangyizhou/edge-ai/issues). Use the `gh` CLI from this checkout, or pass `--repo Shangyizhou/edge-ai` explicitly.

## Sources of truth

- GitHub Issues: work scope, acceptance criteria, dependencies, assignment, discussion and completion status.
- `studies/<topic>/`: research goals, stage summaries, current findings, deployment instructions and experiment evidence. Link these from issues instead of copying complete reports into ticket bodies.
- `.scratch/`: retained historical migration records and optional working notes; it is not the active issue tracker. New work is recorded in GitHub.

Search existing issues and relevant topic documents before creating a ticket. A roadmap stage can contain several issues; a completed issue only establishes its own acceptance scope.

## Operations

```sh
# Read the body, comments and labels.
gh issue view NUMBER --repo Shangyizhou/edge-ai --comments
gh issue view NUMBER --repo Shangyizhou/edge-ai --json number,title,body,state,labels,assignees,comments

# List relevant issues; add --label or --search to narrow the query.
gh issue list --repo Shangyizhou/edge-ai --state open --limit 100 \
  --json number,title,body,labels,assignees

# Publish an exact multiline body prepared in an external temporary file.
gh issue create --repo Shangyizhou/edge-ai --title 'TITLE' \
  --body-file /path/to/issue-body.md --label needs-triage

# Amend, discuss, classify and claim.
gh issue edit NUMBER --repo Shangyizhou/edge-ai --body-file /path/to/issue-body.md
gh issue comment NUMBER --repo Shangyizhou/edge-ai --body-file /path/to/comment.md
gh issue edit NUMBER --repo Shangyizhou/edge-ai --add-label ready-for-agent --remove-label needs-triage
gh issue edit NUMBER --repo Shangyizhou/edge-ai --add-assignee @me

# Resolve after checking acceptance and publishing the result/evidence comment.
gh issue close NUMBER --repo Shangyizhou/edge-ai --reason completed
```

Ticket bodies should identify the concrete problem, scope, acceptance criteria, dependencies and relevant topic documents. Resolution comments link validation, limitations and delivery commits. Keep unresolved necessary criteria open, and synchronize the topic's stage summary when its status changes.

When a skill says “publish to the issue tracker”, create a GitHub issue. When it says “fetch the ticket”, read the issue with comments and labels. Use the mapping in [triage-labels.md](triage-labels.md) for classification.

## Pull requests as a triage surface

**PRs as a request surface: no.** External pull requests are not automatically treated as new feature requests. This flag can be changed explicitly later.

GitHub issues and pull requests share a number space. Resolve whether a referenced number is an issue or PR before applying the corresponding operation; read a referenced PR's diff when reviewing it.

## Wayfinding

When using wayfinding, keep one parent issue as the map and link its child tickets. Prefer native sub-issues and issue dependencies when supported; otherwise use a parent task list plus `Part of #N` and `Blocked by: #N` lines in child bodies. Claim only an unassigned issue with no open blocking dependency. Record the answer and evidence before closing it, then update the parent map.

## Access failures

Git SSH access and GitHub API access use different credentials. If `gh` fails authentication or authorization, report the error and the unfinished remote operations. Continue authorized local documentation work while retaining GitHub as the tracker; an API failure does not select a local issue workflow. Recheck remote state after access is restored before creating labels or issues.
