---
name: visual-inspection
description: "Run browser QA in a separate full-access Codex worker pinned to gpt-5.6-sol with medium reasoning, using agent-browser in an isolated session and returning structured evidence. Use for visual inspection, responsive checks, browser acceptance testing, screenshots, UI regressions, or any request that should keep browser work outside the main agent while sharing complete task context and repository access."
---

# Visual Inspection

Delegate visual and browser QA to one separate Codex worker. Give it the repository and a complete task handoff from the main agent. Use `agent-browser`; never Playwright, Puppeteer, or a built-in browser tool.

## Workflow

Resolve `<skill-dir>` as the directory containing this `SKILL.md`.

1. Finish implementation and non-browser tests first.
2. Start the application separately. Pass the ready public or local URL.
3. Build a complete handoff: current request, relevant decisions, implementation summary, runtime URL, flows, viewports, acceptance criteria, known uncertainties, and required evidence.

For an authenticated target, the caller may supply a short-lived token through a protected channel, such as an inherited environment variable, together with app-specific instructions for consuming it. Put the channel name and usage instructions in the handoff, never the token value; do not echo, persist, or expose the token in reports or artifacts.

4. Invoke the runner:

```bash
<skill-dir>/scripts/visual-inspection --repo <repository> --url <ready-url> < /tmp/visual-inspection-context.txt
```

Before invoking from Codex, preserve the calling client's tier: use explicit session/status metadata when available; otherwise read the persisted `service_tier` selected by `/fast` in the active Codex config. Add `--fast` when that value is `fast`, or when the user explicitly requests Fast. Omit it when Fast is disabled or cannot be established. From Claude, omit it unless the user explicitly requests a Codex Fast inspection.

Use a safe file-editing mechanism for the temporary handoff. Do not interpolate user text into shell quoting.
The total timeout is at most 5 minutes. Use `--timeout-seconds <seconds>` only to lower it; do not wrap the runner in an external timeout.

Keep the run concise:

- Give an exact route and known entity when a criterion depends on data.
- Default to viewport `1024x768`; use another viewport only when the request explicitly names it. Record the actual viewport in preflight evidence.
- Exercise only the requested flows, with one attempt and one reasonable retry. If data or access is still unavailable, report `BLOCKED`; do not hunt across contexts, and allow at most one focused repository lookup.
- Use compact snapshots, finish each criterion before the next, and reserve the final 10% of the timeout to close the session and write the report.

5. Follow progress and 30-second heartbeats on stderr. The runner announces the evidence directory and an exact `tail` command at startup; `worker-events.jsonl` is written incrementally. Final stdout is a Markdown report, also saved as `report.md`.
6. Read the Markdown report. A blocked preflight means the requested flow was not exercised. Treat a worker `PASS` as provisional: open every cited screenshot with the main agent's image-viewing tool and confirm the claimed content and viewport. If image viewing is unavailable, do not accept a visual pass.
7. Report failures and blocked criteria. Fixes remain a separate main-agent action; rerun only when observable behavior changes.

## Worker Contract

- Model: `gpt-5.6-sol`; reasoning effort: `medium`. Fixed by the runner. Optional `--fast` changes only the Codex service tier by enabling Fast and selecting `service_tier="fast"`.
- One ephemeral Codex process, one unique `agent-browser` session, one evidence directory per run.
- Codex runs inside the supplied repository with approvals and sandbox disabled. It inherits the caller environment and may inspect the complete repository, Git history, configuration, tests, logs, and documentation.
- Complete relevant task context comes from the main agent through stdin. The runner cannot export hidden reasoning or the raw conversation automatically; synthesize a faithful handoff.
- Browser interaction uses only `agent-browser`. Do not substitute Playwright, Puppeteer, browser MCPs, or built-in browsing.
- Preflight is generic: confirm that the target opens and the application is usable. Authenticate only when the requested flow requires it. Domain-specific setup belongs in the flow and acceptance criteria.
- A `PASS` may include only `LOW` findings; `MEDIUM`, `HIGH`, or `BLOCKING` findings require `FAIL`.
- Use the concise `agent-browser` protocol embedded by the runner. Re-snapshot after DOM-changing actions; never reuse stale refs.
- Do not mask failed required actions. Retry once from a fresh snapshot, then report the affected criterion as `blocked` or `fail`.
- The worker is an inspector, not an implementer. It may read and run diagnostics, but must not edit repository files, install dependencies, commit, push, or change external state beyond reversible interactions required by the handoff.
- Store screenshots and browser artifacts in the returned evidence directory. Close the session before returning.
- The runner streams safe step progress and heartbeats to stderr while preserving stdout for the final Markdown report. Raw Codex events and stderr are persisted incrementally in the evidence directory.
- The runner owns its timeout and process lifecycle. On timeout, it terminates the worker process group, closes the isolated browser session, preserves partial artifacts, and returns `blocked`.
- If the worker fails or returns an inconsistent report, the runner still writes a final `BLOCKED` Markdown report and lists recoverable files under `Artefatos preservados`. Never reinterpret those unlinked artifacts as a pass.
- On WSL, use viewport screenshots; never use `agent-browser screenshot --full`, which can produce black captures. Scroll and capture multiple viewports for full-page coverage.
- The main agent independently inspects the pixels of every cited screenshot. A worker statement or successful screenshot command alone is not visual proof.
- No technical sandbox or post-run worktree fingerprint is applied.
- No silent fallback to the main agent. If Codex or `agent-browser` is unavailable, return the blocker.

## Handoff Shape

```text
Current user request:
<what the user asked and what must be proven>

Relevant conversation context:
- <decisions, constraints, corrections, and non-goals>

Implementation and repository context:
- <what changed, relevant areas, current state, and known risks>

Runtime target:
- Repository: <path>
- URL: <ready URL>

Flows:
- <navigation or interaction to exercise>

Viewports:
- <desktop/mobile dimensions or named device>

Acceptance criteria:
- <observable result>

Evidence:
- <screenshots, console errors, accessibility snapshot, or other proof>

Known uncertainties:
- <anything the worker should verify rather than assume>
```

Only the goal, flows, and observable acceptance criteria are required. Add the other sections only when they materially help; the runner already supplies repository, URL, model, viewport policy, isolation, and evidence rules.

## Report Shape

```markdown
Status: PASS|FAIL|BLOCKED

# Resumo

# Preflight
Status: PASS|BLOCKED

# Critérios
## <criterion> — PASS|FAIL|BLOCKED

# Achados
## LOW|MEDIUM|HIGH|BLOCKING — <title>

# Limitações

# Evidências
- /absolute/path/to/artifact.png
```

The worker writes Markdown directly. The runner validates only status, required sections, status consistency, and cited evidence paths; it does not require or expose a JSON report.
