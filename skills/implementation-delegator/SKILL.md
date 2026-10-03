---
name: implementation-delegator
description: "Delegate a bounded implementation from a Claude Code parent to a fresh Codex CLI worker with full repository access, incremental progress, and no automatic runtime timeout. Use in Claude Code when the user asks another model to implement code or when a frozen, non-trivial work order is ready for Codex; Codex clients should work directly instead of invoking this skill."
---

# Implementation Delegator

Use Claude as coordinator and Codex as the implementation worker. This skill currently supports only Claude Code → Codex. It is not a review or second-opinion workflow.

## Delegate

Resolve `<skill-dir>` as the directory containing this `SKILL.md`.

1. Finish the design decisions that materially affect implementation. Do not delegate an unresolved architecture question.
2. Inspect the repository enough to freeze a bounded work order: goal, repository, owned files or module, intended behavior, constraints, non-goals, required proof, and the sanctioned stop condition.
3. Put the work order in a temporary file using a safe file-editing mechanism. Never interpolate user text into inline shell quoting.
4. Start one tracked background command in Claude Code; do not append `&`, use an external `timeout`, or hide the worker behind an untracked launcher:

```bash
<skill-dir>/scripts/delegate-implementation --repo <repository> < /tmp/implementation-work-order.md
<skill-dir>/scripts/delegate-implementation --repo <repository> --fast < /tmp/implementation-work-order.md
```

Codex defaults to `gpt-5.6-sol` with reasoning effort `high`; `--fast` only selects the Fast service tier. Honor an explicit user model choice with `--model` after verifying it exists in the active Codex CLI/provider.

5. Follow progress on stderr. The runner announces its protected output directory and an exact `tail` command for `worker-events.jsonl`. It has no runtime deadline: heartbeat continues until Codex exits or the caller interrupts the runner.
6. Read the final Markdown report, then independently inspect `git status`, the full diff, and the claimed test evidence. The worker report is advisory.
7. For a narrow correction, resume the recorded session rather than starting a fresh worker:

```bash
<skill-dir>/scripts/delegate-implementation \
  --repo <repository> \
  --resume <session-id> \
  < /tmp/implementation-correction.md
```

Use at most two correction rounds. If the implementation still does not converge, stop and report the decision or take over directly. Never edit the same files while a worker remains alive.
Resume preserves the session's model unless `--model` is explicitly supplied as a deliberate override. Repeat `--fast` only when the correction should also use the Fast service tier.

## Work Order

```text
Goal:
<one concrete outcome>

Repository and ownership:
- Repository: <path is passed separately through --repo>
- Owned files/module: <bounded surface>
- Preserve: <existing or concurrent work>

Expected behavior:
- <observable acceptance criteria>

Constraints:
- <architecture, compatibility, style, or dependency constraints>
- If a constraint cannot be satisfied honestly, stop and report the exact blocker; do not work around it.

Non-goals:
- <adjacent work that must not begin>

Required proof:
- <focused tests and applicable repository gates>
```

Provide the original user intent and relevant decisions, not a transcript dump. Codex has full repository access and must inspect the actual files itself.

Specify the repository's actual validation commands in Required proof. Follow its installed toolchain: in Vite+ projects, `vp check` covers static checks when `typeAware` and `typeCheck` are enabled; tests, Knip, and builds remain separate gate steps. Do not prescribe Biome or duplicate type checks independently of the repository configuration.

## Boundaries

- One worker per invocation. The runner disables Codex multi-agent delegation to prevent recursive workers.
- Full filesystem, command, and network access in the requested repository. Repository `AGENTS.md` instructions remain active.
- No automatic timeout and no inactivity kill. Interruption terminates the worker process group; artifacts remain under `/tmp/implementation-delegator`.
- The delegated scope ends at implementation and tests. Do not commit, push, open or merge PRs, deploy, update tickets, delete branches/worktrees, or mutate unrelated external state.
- Preserve pre-existing working-tree changes. Never reset, clean, restore, overwrite, or reformat unrelated work.
- Do not launch long-running servers or watchers unless the work order explicitly requires them and defines their lifecycle.
- A truthful `BLOCKED` or `PARTIAL` report is a valid worker result. Never contort code merely to report completion.
- Commit, publication, AutoReview, visual inspection, and final handoff remain responsibilities of the Claude coordinator under the repository directives.
