---
name: behavior-validator
description: "Validate observable user behavior against a source-blind contract for web apps, Electron apps, CLIs, APIs, and generated artifacts. Use after changes that affect user-visible behavior, when verifying bug fixes or regressions end to end, or when the user asks for behavioral validation, acceptance testing, QA, or runtime proof."
---

# Behavior Validator

Validate observable behavior without inspecting source. Judge the running product, CLI, API, or generated artifact against a behavior contract.

## Contract

- Resolve `<skill-dir>` as the directory containing this `SKILL.md`.
- Read the behavior contract first. If none exists, write a short one from the user request using `<skill-dir>/references/contract-template.md`.
- Stay source-blind. Do not inspect source files, diffs, tests, Git history, implementation notes, build internals, or review bundles.
- Browser targets are the explicit exception: `visual-inspection` receives the main agent's complete relevant context and full repository access. Its pass/fail evidence must still come from observable browser behavior.
- Interact only through user-visible or operator-visible surfaces: browser, CLI, API, generated files, public logs, screenshots, or accessibility trees.
- Treat implementation-looking evidence as contamination. If source access is required, stop and report `blocked_source_required`.
- Classify every relevant contract clause as `pass`, `fail`, `blocked`, or `out_of_scope`.

## Isolation

- Use a fresh, isolated session or workspace for each validation.
- Keep only the contract, approved fixtures, and redacted evidence available to the validator.
- Supply credentials through approved secret tooling, exact environment-variable names, or an approved browser authentication profile. Never expose values in commands, reports, screenshots, or logs.
- If the application must start from its source checkout, start it separately; do not read source while validating.

## Browser Targets on WSL

- For web and Electron targets, invoke the `visual-inspection` skill with the ready URL and this behavior contract. Do not run browser commands in the main validator.
- `visual-inspection` delegates to a full-access Codex worker fixed to `gpt-5.6-sol` with reasoning `medium`; the main agent supplies a complete handoff and the repository path. Browser interaction uses only `agent-browser`. Do not fall back to Playwright, Puppeteer, or an in-app browser.
- Use one worker and one isolated named browser session for each validation; never share it with another process or validation.
- Prefer accessibility snapshots and stable element references for interaction. Capture screenshots or video only when the contract requires visual evidence.
- Reuse authentication only through an approved `agent-browser` vault or profile. Redact cookies, tokens, credentials, and private data.
- Treat visible UI and user-observable state as primary evidence. Do not inspect application bundles or source through browser tooling.

## Workflow

1. Parse the contract into user tasks, expected behavior, anti-cheat probes, setup, and evidence requirements.
2. Prepare runtime access: URL, CLI command, API endpoint, fixture data, credentials, or generated artifact path.
3. Exercise each task as a real user or operator. For browser targets, delegate the complete browser portion to `visual-inspection` and consume its Markdown report.
4. Run anti-cheat probes: vary input, refresh or reopen, test persistence, exercise empty and invalid states, and confirm actions perform real work.
5. Capture compact, redacted evidence: screenshots, terminal excerpts, response summaries, file summaries, or accessibility observations.
6. Emit a structured report. Use `<skill-dir>/references/report-schema.md` when machine-readable output is useful.
7. After a fix, rerun affected clauses and nearby regression probes.

## Finding Rules

- Fail when observable behavior violates the contract, a task cannot be completed, expected state is fake or static, or evidence is insufficient for a claimed pass.
- Block when required runtime access, credentials, fixtures, network, or tools are missing.
- Mark out of scope only when the contract explicitly excludes the behavior or a user-owned product decision is required.
- Reject aesthetic, code-quality, or implementation-style concerns; those belong to code-aware review.

## Final Report

Include:

- target exercised;
- contract used;
- pass, fail, blocked, and out-of-scope summary;
- behavioral findings with reproduction steps and evidence;
- anti-cheat probes;
- remaining blockers.
