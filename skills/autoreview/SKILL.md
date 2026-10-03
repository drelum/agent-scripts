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

Before invoking from Codex, preserve the calling client's tier: use explicit session/status metadata when available; otherwise read the persisted `service_tier` selected by `/fast` in the active Codex config. Pass `--fast` when that value is `fast`, or when the user explicitly requests Fast. Omit it when Fast is disabled or cannot be established. From Claude, omit it unless the user explicitly requests a Codex Fast review. The flag preserves `gpt-6.1-sol` and reasoning `high`; it changes only the Codex service tier.

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

2. Let the helper build a bounded review bundle. In a no-HEAD or multi-ticket checkout, repeat `--path <relative-file-or-directory>` to include only the frozen scope. The helper does not block paths or text because they contain credentials, private keys, tokens, environment variables, or other secrets. Untracked or initial symlinks (e.g. `CLAUDE.md -> AGENTS.md`) enter only as a target record, never with the linked content. It still rejects binary untracked files and oversized input.
3. Read the Markdown report. The helper validates structured engine output internally, then renders the human-facing result. Confirm each finding by inspecting source, tests, and dependency contracts.
   - The helper detects Vercel Eve before the review: a `package.json` governing a changed file (the file's directory up to the repository root) declaring `eve` or `@aitrus/eve-kit`, or an `import`/`export` of those packages in the bundle. Without Eve, it skips the documentation snapshot, the Eve Kit snapshot, Eve instructions, and web access; the dry-run shows `EVE: não detectado`.
   - When Eve is detected, a full review conditionally refreshes the official documentation snapshot under `~/.cache/agent-scripts/eve-docs`, then gives the reviewer its immutable local path. When Eve is detected, prefer version-matched `node_modules/eve/docs/`, open the snapshot `INDEX.md`, read only relevant pages, and report their exact official source URLs; never load `llms-full.txt` wholesale.
   - For an Eve project, the helper snapshots the current local working tree at `~/Projects/eve-kit`; ignore package versions, publication metadata, remotes, tags, releases, and installed copies. Treat proven reimplementation of a concrete, compatible local public export or README direction as actionable drift, citing its local path or section.
4. Accept only concrete defects introduced or exposed by the reviewed change. Reject style-only, speculative, pre-existing, or overengineered findings.
5. Fix accepted findings within the frozen task scope and rerun relevant tests. Use the focused follow-up instead of repeating the full review:

```bash
<skill-dir>/scripts/autoreview --mode local --path src/feature --engine codex \
  --follow-up /tmp/autoreview-<uid>/<run>/report.md
```

   - A report with one finding selects it automatically. For multiple findings, repeat `--accepted-finding <number>` for the findings actually accepted.
   - The follow-up reuses the full review's EVE metadata, official documentation snapshot, and Eve Kit snapshot, compares only the correction delta, and avoids general project or documentation rediscovery.
   - Local mode keeps the reviewed `HEAD`; branch/commit mode permits only same-branch fast-forward corrections with the frozen base and paths. Rebase, branch/base/path change, or Eve Kit change requires a new full review. A follow-up cannot start another follow-up cycle.
6. Treat a valid report as a completed run. Use `Status: CLEAN|FINDINGS`, not the process exit code, to interpret the diagnosis; then apply the scope governor.

## Runtime Observability

- Internal timeout: 30 minutes by default; override with `--timeout-seconds`. Do not wrap the helper in an external timeout.
- Heartbeat: emitted to stderr every 30 seconds by default; override with `--heartbeat-seconds`.
- Incremental raw logs: private user-specific run directory under `/tmp/autoreview-<uid>`; the helper prints the exact `tail -n 200 -f` command when it starts.
- EVE documentation: `scripts/eve-docs-snapshot` refreshes by ETag, writes atomically under a user-private cache, prints the current snapshot path, and falls back to the last snapshot with an explicit warning when the network fails.
- Filtered streaming: lifecycle events always appear on stderr. Add `--stream-engine-output` for extra safe activity summaries. Raw commands, engine-emitted paths, model text, and tool payloads never stream to the terminal.
- Final Markdown report: stdout and `report.md` in the private run directory. A valid `CLEAN` or `FINDINGS` report exits 0; operational failures such as timeout, invalid report, or unavailable engine exit 2. Partial events remain diagnostic evidence, never a valid review result.

## Scope Governor

- Before the first review, freeze the original request, intended behavior, owner boundary, changed files, and non-test LOC.
- Classify every accepted finding as an in-scope blocker, a follow-up, or a stop-and-escalate decision.
- Allow one full review and one focused follow-up. If they do not converge, stop and reclassify before any further edit.
- Do not let review fixes grow changed files or non-test LOC beyond 2x the baseline without explicit user approval.
- After the focused follow-up, continue only when every remaining finding is an in-scope blocker. Otherwise report follow-ups or the decision needed.
- Override the stop only for concrete data loss, crashes, broken install/upgrade, release blockers, or security exposure.
- The helper is one-shot. Never loop indefinitely to force a clean result.

## Isolation Contract

- Codex: ephemeral execution in the native read-only sandbox, with repository and EVE snapshot readable, empty tool-shell environment, project instructions disabled, user config and exec rules ignored; web search is enabled only for an Eve review without a local EVE snapshot.
- Codex default reviewer: `gpt-6.1-sol` with reasoning effort `high`; an explicit `--model` overrides the model.
- Codex Fast: optional `--fast` enables the CLI Fast feature and selects `service_tier="fast"`. Repass the calling client's known or persisted Fast selection because the helper intentionally ignores user config.
- Claude: print mode, safe mode, user setting source only, checkout- and EVE-snapshot-scoped reads without secret-path denials; `WebFetch` is restricted to `eve.dev` only for an Eve review without a snapshot; shell, writes, open web search, and MCP remain disabled.
- The review bundle and repository reads may contain secrets. Ambient process credentials remain excluded from the reviewer environment.
- Do not run reviewer panels or another engine unless the user asks.
- Do not commit, push, post, merge, or modify external state during review.

## Relationship to Runtime Validation

Assess validation against the repository's scripts and configuration. In Vite+ projects, `vp check` covers formatting, lint, and types when `typeAware` and `typeCheck` are enabled; do not require Biome or a duplicate `tsc` check. Keep additional type checks for other project scopes, declaration generation, or build requirements. A clean review does not replace the repository's full gate, including applicable tests, Knip, and builds.

- `autoreview`: source-aware review of code and diff.
- `visual-inspection`: separate-worker browser QA and visual evidence, after implementation, tests/builds, and Auto Review.

Use `visual-inspection` when the change requires browser proof, following workspace sequencing and isolation rules. `behavior-validator` is temporarily disabled; do not invoke it. For CLI, API, or artifact changes without browser behavior, use the relevant non-browser tests and diagnostics instead of forcing a visual inspection.

## Final Report

The helper output uses these sections:

- `Status: CLEAN|FINDINGS`;
- `# Execução`;
- `# EVE`;
- `# Resumo`;
- `# Achados`;
- `# Conclusão`.

Structured JSON remains an internal engine contract only. The calling agent reports findings accepted or rejected, tests or evidence rerun after fixes, and the final clean result or remaining blocker.
