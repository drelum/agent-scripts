# AGENTS.MD

Andre owns this. Start: say Olá + 1 motivating line.
Style: telegraph; noun-phrases ok; drop filler/grammar; min tokens.

## Agent Protocol
- Contact: Andre Monteiro (drelum@gmail.com).
- Workspace: `~/Projects`.
- 3rd-party/OSS clone under `~/Projects/oss`.
- Scope/files: repo or `~/Projects/agent-scripts` only.
- "Make a note" => edit `AGENTS.md` (shortcut; not a blocker). Ignore `CLAUDE.md`.
- Bugs: add regression test when it fits.
- Keep files <~500 LOC; split/refactor as needed.
- Commits: Conventional Commits (`feat|fix|refactor|build|ci|chore|docs|style|perf|test`).
- Prefer end-to-end verify; blocked => say what's missing.
- New deps: quick health check (recent releases/commits, adoption).
- Web: search early; quote exact errors; prefer 2024-2025 sources.
- tmux: somente jobs longos (servers, watch, builds pesados). Session = nome da pasta do projeto.
- tmux: nao usar para tsc, biome check, lint, tests.

## Docs
- Follow links until domain makes sense; honor `Read when` hints.
- Keep notes short; update docs on behavior/API changes (no ship w/o docs).
- Add `read_when` hints on cross-cutting docs.
- Models: latest only. OK: Anthropic Opus 4.5 / Sonnet 4.5 (Sonnet 3.5 = old; avoid), OpenAI GPT-5.2, xAI Grok-4.1 Fast, Google Gemini 3 Flash.

## Flow & Runtime
- Use repo's package manager/runtime; no swaps w/o approval.
- Use Codex background for long jobs.

## Browser Automation
Use `agent-browser` for web automation. Run `agent-browser --help` for all commands.

Core workflow:
1. `agent-browser open <url>` - Navigate to page
2. `agent-browser snapshot -i` - Get interactive elements with refs (@e1, @e2)
3. `agent-browser click @e1` / `fill @e2 "text"` - Interact using refs
4. Re-snapshot after page changes

## Build / Test
- Before handoff: full gate (biome check/typecheck/tests).
- Lint == `biome check` only (no `pnpm lint`).
- Keep it observable (logs, panes, tails).

## Git
- Safe by default: `git status/diff/log`. Push only when user asks.
- Commit/push: sempre perguntar + esperar OK explicito do Andre antes de executar (mesmo se ja foi solicitado).
- Branch changes require user consent.
- Destructive ops forbidden unless explicit (`reset --hard`, `clean`, `restore`, `rm`, ...).
- Remotes under `~/Projects`: prefer HTTPS; flip SSH->HTTPS before pull/push.
- Don't delete unexpected stuff; stop + ask.
- No repo-wide search/replace scripts; keep edits small/reviewable.
- Avoid manual `git stash`; if Git auto-stashes during pull/rebase, that's fine (hint, not hard guardrail).
- If user types a command ("pull and push"), that's intent for that command; still ask OK before commit/push.

## Language/Stack Notes
- TypeScript: preferred
- Biome lint

## Critical Thinking
- Fix root cause (not band-aid).
- Unsure: read more code; still stuck => ask w/ short options.
- Conflicts: call out; pick safer path.
- fallback: only implement if explicitly requested; when in doubt, ask before implementing.
- Unrecognized changes: assume other agent; keep going; focus your changes. If issues, stop + ask user.
- Leave breadcrumb notes in thread.

<frontend_aesthetics>
Avoid "AI slop" UI. Be opinionated + distinctive.

Do:
- Typography: pick a real font; avoid Inter/Roboto/Arial/system defaults.
- Theme: commit to a palette; use CSS vars; bold accents > timid gradients.
- Motion: 1-2 high-impact moments (staggered reveal beats random micro-anim).
- Background: add depth (gradients/patterns), not flat default.

Avoid: purple-on-white cliches, generic component grids, predictable layouts.
</frontend_aesthetics>
