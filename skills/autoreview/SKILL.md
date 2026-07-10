---
name: autoreview
description: "Run an isolated, structured code review with Codex or Claude before handoff. Use when the user asks for autoreview, an independent review, a second-model review, or when non-trivial code changes need a source-aware closeout review."
---

# Auto Review

Run an independent source-aware review. Treat findings as advisory; verify every finding against the real code path before changing anything.

## Workflow

Resolve `<skill-dir>` as the directory containing this `SKILL.md`, regardless of the current repository.

1. Select the review target:

```bash
<skill-dir>/scripts/autoreview --engine codex
<skill-dir>/scripts/autoreview --engine claude
```

Default `--mode auto` behavior:

- dirty checkout: review local changes;
- non-main branch: review against `origin/main` or `main`;
- clean main: stop and request an explicit target.

Explicit targets:

```bash
<skill-dir>/scripts/autoreview --mode local --engine codex
<skill-dir>/scripts/autoreview --mode branch --base origin/main --engine claude
<skill-dir>/scripts/autoreview --mode commit --commit HEAD --engine codex
```

2. Let the helper build a bounded review bundle. It must fail closed on sensitive paths, secret-like values, binary untracked files, or oversized input.
3. Read the structured findings. Confirm each one by inspecting source, tests, and dependency contracts.
4. Accept only concrete defects introduced or exposed by the reviewed change. Reject style-only, speculative, pre-existing, or overengineered findings.
5. Fix accepted findings within the frozen task scope, rerun relevant tests, then rerun the same review engine.
6. Stop when the helper exits clean or the scope governor requires a pause.

## Scope Governor

- Before the first review, freeze the original request, intended behavior, owner boundary, changed files, and non-test LOC.
- Classify every accepted finding as an in-scope blocker, a follow-up, or a stop-and-escalate decision.
- Allow at most two review-triggered patch cycles. If they do not converge, stop and reclassify before any further edit.
- Do not let review fixes grow changed files or non-test LOC beyond 2x the baseline without explicit user approval.
- After the two-cycle pause, continue only when every remaining finding is an in-scope blocker. Otherwise report follow-ups or the decision needed.
- Override the stop only for concrete data loss, crashes, broken install/upgrade, release blockers, or security exposure.
- The helper is one-shot. Never loop indefinitely to force a clean result.

## Isolation Contract

- Codex: ephemeral execution, repository-scoped read-only permission profile, empty tool-shell environment, project instructions disabled, user config and exec rules ignored.
- Codex default reviewer: `gpt-5.6-sol` with reasoning effort `high`; an explicit `--model` overrides the model.
- Claude: print mode, safe mode, user setting source only, MCP and all file/shell/web tools disabled.
- Never pass credentials, environment dumps, private keys, or secret-bearing files to a reviewer.
- Do not run reviewer panels or another engine unless the user asks.
- Do not commit, push, post, merge, or modify external state during review.

## Relationship to Behavior Validation

- `autoreview`: source-aware review of code and diff.
- `behavior-validator`: source-blind proof through web, CLI, API, or artifact surfaces.

Use both when a non-trivial user-visible change needs implementation review and runtime proof.

## Final Report

Include:

- engine and target;
- findings accepted or rejected, with brief reasons;
- tests or evidence rerun after accepted fixes;
- final clean result or remaining blocker.
