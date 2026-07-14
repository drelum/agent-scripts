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
3. Build a complete handoff: current request, relevant conversation decisions, implementation summary, repository state, runtime URL, expected flows, viewports, acceptance criteria, known uncertainties, and required evidence.
4. Invoke the runner:

```bash
<skill-dir>/scripts/visual-inspection --repo <repository> --url <ready-url> < /tmp/visual-inspection-context.txt
```

Use a safe file-editing mechanism for the temporary handoff. Do not interpolate user text into shell quoting.
The default timeout is 15 minutes. Override it for a known long flow with `--timeout-seconds <seconds>`; do not wrap the runner in an external timeout.

5. Follow progress and 30-second heartbeats on stderr. The runner announces the evidence directory and an exact `tail` command at startup; `worker-events.jsonl` is written incrementally. The final stdout remains one machine-readable JSON object.
6. Read the JSON report. Use `started_at`, `finished_at`, and `duration_seconds` to calibrate future timeouts. Treat a worker `pass` as provisional. Open every cited screenshot with the main agent's image-viewing tool and confirm the claimed content, viewport, and absence of blank, black, clipped, or stale captures. If image viewing is unavailable, do not accept a visual pass.
7. Report failures and blocked criteria. Fixes remain a separate main-agent action; rerun only when observable behavior changes.

## Worker Contract

- Model: `gpt-5.6-sol`; reasoning effort: `medium`. Fixed by the runner.
- One ephemeral Codex process, one unique `agent-browser` session, one evidence directory per run.
- Codex runs inside the supplied repository with approvals and sandbox disabled. It inherits the caller environment and may inspect the complete repository, Git history, configuration, tests, logs, and documentation.
- Complete relevant task context comes from the main agent through stdin. The runner cannot export hidden reasoning or the raw conversation automatically; synthesize a faithful handoff.
- Browser interaction uses only `agent-browser`. Do not substitute Playwright, Puppeteer, browser MCPs, or built-in browsing.
- The worker is an inspector, not an implementer. It may read and run diagnostics, but must not edit repository files, install dependencies, commit, push, or change external state beyond reversible interactions required by the handoff.
- Store screenshots and browser artifacts in the returned evidence directory. Close the session before returning.
- The runner streams safe step progress and heartbeats to stderr while preserving stdout for the final JSON. Raw Codex events and stderr are persisted incrementally in the evidence directory.
- The runner owns its timeout and process lifecycle. On timeout, it terminates the worker process group, closes the isolated browser session, preserves partial artifacts, and returns `blocked`.
- If the worker fails or returns an inconsistent report, the runner still writes a final `blocked` report and lists recoverable files under `preserved_artifact_paths`. Never reinterpret those unlinked artifacts as a pass.
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
