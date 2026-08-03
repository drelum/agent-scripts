---
name: codex-session-restorer
description: "Find recent interactive Codex sessions and reopen each one in a named Windows Terminal tab from WSL. Use when the user asks to restore, reopen, organize, or recover recent Codex sessions or terminal tabs after a restart, including requests such as 'verifique as últimas 12 horas'."
---

# Codex Session Restorer

Inspect recent sessions, choose concise tab titles, then let the bundled script open them. Do not rename Codex sessions or edit their histories.

## Workflow

Resolve `<skill-dir>` as the directory containing this `SKILL.md`.

1. List candidates for the requested window. Default to 12 hours only when the user gives no window:

```bash
python3 <skill-dir>/scripts/restore-codex-sessions list --hours 12
```

The list excludes archived sessions, subagents, non-CLI sessions, and the current calling session. Use `--include-current` only when the user explicitly wants a duplicate tab for it.

2. Review `existing_title`, `first_user_message`, `preview`, and `recent_user_messages`. Read the indicated `rollout_path` only when the topic remains ambiguous; keep that lookup bounded to the candidate session.

3. Select only sessions representing user work. Skip bootstrap/test sessions, external workers, duplicates, and sessions whose directory no longer exists. If the selection is ambiguous, show the proposed list before opening tabs.

4. Create each title:
   - Ticket known: `<TICKET> — <tema curto>`.
   - No ticket: `<tema curto>`.
   - Same ticket in multiple sessions: distinguish the focus, such as `AITRUS-432 — Backend de preferências` and `AITRUS-432 — Interface de distribuidores`.
   - Prefer the sustained current objective over the first prompt or latest incidental question.
   - Keep the title near 50 characters. Preserve the ticket in uppercase. Avoid generic titles such as `Ajustes`, `Implementação`, or `Análise`.

5. Open tabs from least recent to most recent. This leaves the newest session as the final, focused tab:

```bash
python3 <skill-dir>/scripts/restore-codex-sessions open \
  --session-id '<uuid>' \
  --project-dir '/home/user/Projects/project' \
  --title 'AITRUS-432 — Preferências por distribuidor'
```

Repeat the command for every selected session. Use the exact `session_id` and `cwd` returned by `list`.

6. Report opened tabs in displayed order, title, project directory, and any skipped session with its reason.

## Safety

- Run `open ... --dry-run` when validating commands or when the user has not authorized opening tabs.
- Never construct titles from secrets, credentials, or raw tool output.
- Do not archive, rename, delete, or otherwise mutate Codex session records.
- Do not use `eval`. The helper passes arguments directly to `wt.exe` and quotes the inner Bash command.
