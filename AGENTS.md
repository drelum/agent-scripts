# AGENTS.MD

Andre owns this. Start: say Olá + 1 motivating line.
Style: telegraph; noun-phrases ok; drop filler/grammar; min tokens.

## Agent Protocol
- Contact: Andre Monteiro (drelum@gmail.com).
- Workspace: `~/Projects`.
- 3rd-party/OSS clone under `~/Projects/oss`.
- Scope/files: repo or `~/Projects/agent-scripts` only.
- Screenshot: quando eu pedir para consultar o screenshot, buscar o arquivo mais recente em `/mnt/c/Users/drelu/Downloads` cujo nome comece com `Screenshot_`; no WSL, tratar `C:\Users\drelu\Downloads` como `/mnt/c/Users/drelu/Downloads`; se não encontrar, avisar claramente.
- "Make a note" => edit `AGENTS.md` (shortcut; not a blocker). Ignore `CLAUDE.md`.
- Bugs: add regression test when it fits.
- Keep files <~500 LOC; split/refactor as needed.
- Commits: Conventional Commits (`feat|fix|refactor|build|ci|chore|docs|style|perf|test`).
- Prefer end-to-end verify; blocked => say what's missing.
- New deps: quick health check (recent releases/commits, adoption).
- Web: search early; quote exact errors; prefer 2024-2025 sources.
- Edição manual: sempre usar `apply_patch` via shell (`exec_command`), com patch em heredoc ou arquivo temporário; não usar a tool `apply_patch` direta neste ambiente.
- tmux: somente jobs longos (servers, watch, builds pesados). Session = nome da pasta do projeto.
- tmux: nao usar para tsc, biome check, lint, tests.

## Docs
- Follow links until domain makes sense; honor `Read when` hints.
- Keep notes short; update docs on behavior/API changes (no ship w/o docs).
- Add `read_when` hints on cross-cutting docs.
- Models: latest only. OK: Anthropic Opus 4.6 / Sonnet 4.5 (Sonnet 3.5 = old; avoid), OpenAI GPT-5.4, Google Gemini 3 Flash.

## Flow & Runtime
- Use repo's package manager/runtime; no swaps w/o approval.
- Dev server: prefer `portless`; if missing, install global `npm install -g portless`; do not add dependency to project; do not say "subir o portless"; correct: subir o servidor do projeto usando `portless`, com URL no nome do projeto; sempre passar o nome do projeto explicitamente no comando; não confiar no nome inferido; long-running server => `tmux` + `portless`; inside session prefer `portless <nome-do-projeto> <comando>` (ex.: projeto `api.myapp` -> `portless api.myapp pnpm dev` -> `http://api.myapp.localhost:1355`); `portless` injects `PORT`, `HOST=127.0.0.1`, `PORTLESS_URL`; after start, always report `tmux attach -t <sessao>` + final URL.
- Use Codex background for long jobs.
- Servers via `tmux` (sessão sobrevive a crash): criar sessão (sem server) -> `send-keys` (start) -> informar `tmux attach -t <sessao>`. Ex:
```bash
s="$(basename "$PWD")"; tmux has -t "$s" 2>/dev/null || tmux new -d -s "$s" -c "$PWD"
tmux send -t "$s" "cd '$PWD' && portless <nome-do-projeto> pnpm dev" C-m; tmux attach -t "$s"
```

## Build / Test
- Before handoff: full gate (biome check/typecheck/tests/knip).
- Lint == `biome check` only (no `pnpm lint`).
- Testes visuais: Playwright only; sessão própria/isolada por execução; nunca dividir sessão com outro processo.
- Dependency/unused check: use `knip` to find unused dependencies, exports and files.
- Suggested `check` script:
  `biome check && pnpm exec tsc -p tsconfig.json --noEmit && pnpm test && pnpm dlx knip --no-progress`
- Keep it observable (logs, panes, tails).
- Observabilidade (sempre): se eu iniciar algo em `tmux`, logo em seguida informar o comando completo de attach (`tmux attach -t <sessao>`). Se eu redirecionar output para arquivo, logo em seguida informar o comando completo de tail com caminho absoluto (sem precisar `cd`): `tail -n 200 -f /caminho/completo/para/arquivo.log`.

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
- Idioma: pt-BR em comentários e interface (UI); código/variáveis podem ser em inglês; atenção máxima à acentuação correta.
- TypeScript: preferred
- Valores de controle de fluxo (comparações, flags, status, providers, domains, mode switches): evitar strings soltas; preferir enum, union tipada ou mapa tipado centralizado.
- Biome lint
- Knip for unused code/dependencies

## Critical Thinking
- Fix root cause (not band-aid).
- Evitar overengineering: preferir arquitetura elegante, componentizável e resistente a drift, projetada para necessidades reais atuais; não introduzir campos, granularidade, configurações ou abstrações extras para cenários hipotéticos se isso reduzir clareza ou aumentar ambiguidade.
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
