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
<skill-dir>/scripts/autoreview --engine codex --fast
<skill-dir>/scripts/autoreview --engine claude
```

Before invoking from Codex, preserve the calling client's tier: use explicit session/status metadata when available; otherwise read the persisted `service_tier` selected by `/fast` in the active Codex config. Pass `--fast` when that value is `fast`, or when the user explicitly requests Fast. Omit it when Fast is disabled or cannot be established. From Claude, omit it unless the user explicitly requests a Codex Fast review. The flag preserves `gpt-5.6-sol` and reasoning `high`; it changes only the Codex service tier.

Default `--mode auto` behavior:

- dirty checkout: review local changes;
- repository without a first commit: review the initial working tree directly;
- non-main branch: review against `origin/main` or `main`;
- clean main: stop and request an explicit target.

Explicit targets:

```bash
<skill-dir>/scripts/autoreview --mode local --engine codex
<skill-dir>/scripts/autoreview --mode branch --base origin/main --engine claude
<skill-dir>/scripts/autoreview --mode commit --commit HEAD --engine codex
<skill-dir>/scripts/autoreview --mode local --path src/feature --path tests/feature.test.ts --engine codex
```

2. Let the helper build a bounded review bundle. In a no-HEAD or multi-ticket checkout, repeat `--path <relative-file-or-directory>` to include only the frozen scope. The helper validates the complete provider prompt before launch and fails closed on sensitive paths, private keys, API keys, tokens, binary untracked files, or oversized input. Environment-file paths are allowed and screened by content like other files. Password assignments are not content-screened.
3. Read the Markdown report. The helper validates structured engine output internally, then renders the human-facing result. Confirm each finding by inspecting source, tests, and dependency contracts.
4. Accept only concrete defects introduced or exposed by the reviewed change. Reject style-only, speculative, pre-existing, or overengineered findings.
5. Fix accepted findings within the frozen task scope, rerun relevant tests, then rerun the same review engine.
6. Treat a valid report as a completed run. Use `Status: CLEAN|FINDINGS`, not the process exit code, to interpret the diagnosis; then apply the scope governor.

## Runtime Observability

- Internal timeout: 30 minutes by default; override with `--timeout-seconds`. Do not wrap the helper in an external timeout.
- Heartbeat: emitted to stderr every 30 seconds by default; override with `--heartbeat-seconds`.
- Incremental raw logs: private user-specific run directory under `/tmp/autoreview-<uid>`; the helper prints the exact `tail -n 200 -f` command when it starts.
- Filtered streaming: lifecycle events always appear on stderr. Add `--stream-engine-output` for extra safe activity summaries. Raw commands, engine-emitted paths, model text, and tool payloads never stream to the terminal.
- Final Markdown report: stdout and `report.md` in the private run directory. A valid `CLEAN` or `FINDINGS` report exits 0; operational failures such as timeout, invalid report, or unavailable engine exit 2. Partial events remain diagnostic evidence, never a valid review result.

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
- Codex Fast: optional `--fast` enables the CLI Fast feature and selects `service_tier="fast"`. Repass the calling client's known or persisted Fast selection because the helper intentionally ignores user config.
- Claude: print mode, safe mode, user setting source only, MCP and all file/shell/web tools disabled.
- Never pass credentials, environment dumps, private keys, or secret-bearing files to a reviewer.
- Do not run reviewer panels or another engine unless the user asks.
- Do not commit, push, post, merge, or modify external state during review.

## Relationship to Behavior Validation

- `autoreview`: source-aware review of code and diff.
- `behavior-validator`: source-blind proof through web, CLI, API, or artifact surfaces.

Use both when a non-trivial user-visible change needs implementation review and runtime proof.

## Final Report

The helper output uses these sections:

- `Status: CLEAN|FINDINGS`;
- `# Execução`;
- `# Resumo`;
- `# Achados`;
- `# Conclusão`.

Structured JSON remains an internal engine contract only. The calling agent reports findings accepted or rejected, tests or evidence rerun after fixes, and the final clean result or remaining blocker.
