# AGENTS.MD

Andre owns this. Start: say Olá + 1 motivating line.
Style: telegraph; noun-phrases ok; drop filler/grammar; min tokens.

## Agent Protocol
- Contact: Andre Monteiro (drelum@gmail.com).
- Workspace: `~/Projects`.
- 3rd-party/OSS clone under `~/Projects/oss`.
- Scope/files: repo or `~/Projects/agent-scripts` only.
- Datas/horários: sempre reportar em formato brasileiro e localidade São Paulo, Brasil; converter de GMT/UTC quando necessário.
- Screenshot: quando eu pedir para consultar o screenshot, buscar o arquivo mais recente em `/mnt/c/Users/drelu/Downloads` cujo nome comece com `Screenshot_`; no WSL, tratar `C:\Users\drelu\Downloads` como `/mnt/c/Users/drelu/Downloads`; se não encontrar, avisar claramente.
- "Make a note" => edit `AGENTS.md` (shortcut; not a blocker). Ignore `CLAUDE.md`.
- Bugs: add regression test when it fits.
- Commits: Conventional Commits (`feat|fix|refactor|build|ci|chore|docs|style|perf|test`).
- Prefer end-to-end verify; blocked => say what's missing.
- New deps: quick health check (recent releases/commits, adoption).
- Web: search early; quote exact errors; prefer current primary sources; compare publication date with event/version date.
- tmux: somente jobs longos (servers, watch, builds pesados). Session = nome da pasta do projeto.
- tmux: nao usar para tsc, biome check, lint, tests.

## Docs
- Follow links until domain makes sense; honor `Read when` hints.
- Keep notes short; update docs on behavior/API changes (no ship w/o docs).
- Add `read_when` hints on cross-cutting docs.
- Models: latest/current only; verify availability in the active CLI/provider before selecting or pinning; avoid static allowlists that drift.
- Modelos LLM: para investigar capacidades e preços atuais, consultar sem API key `curl -sS https://openrouter.ai/api/v1/models`; docs: https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties.md.

## Google Workspace / GWS
- CLI local: `gws`.
- Wrappers canônicos em `~/Projects/agent-scripts/bin`.
- Aitrus: de `~/Projects`, usar `./agent-scripts/bin/gws-aitrus`; usuário esperado `andre@aitrus.com.br`.
- Pessoal: de `~/Projects`, usar `./agent-scripts/bin/gws-pessoal`; usuário esperado `drelum@gmail.com`.
- Fora de `~/Projects`, usar `~/Projects/agent-scripts/bin/gws-aitrus` ou `~/Projects/agent-scripts/bin/gws-pessoal`.
- Quando a conta importar, usar o wrapper explícito antes de ler Drive/Gmail/Docs/Sheets/Slides.
- Login Aitrus para Gmail/Calendar/Drive/Docs/Sheets/Slides: `~/Projects/agent-scripts/bin/gws-aitrus auth login --services gmail,calendar,drive,docs,sheets,slides`; não usar `--full`, pois ele adiciona `cloud-platform` e pode causar expiração frequente por `invalid_rapt`.
- Após autenticar a Aitrus, conferir `auth status`; `cloud-platform` deve estar ausente. Se persistir por grant anterior, revogar/limpar a autorização antiga e autenticar novamente.

## WhatsApp / wacli
- CLI local: `wacli`.
- Status de sync: usar sempre `wacli doctor --read-only --json`; fonte de verdade = `data.store.last_sync_at`.
- Defasagem máxima aceita: 30 minutos; se `last_sync_at` faltar, não avançar após sync, ou estiver >30 min atrás de agora, tratar como stale e sincronizar quando eu pedir mensagens atuais.
- Não concluir "sem mensagens novas" só por `Messages stored: 0`, principalmente com warnings de app state, `LTHash`, websocket, old counter, keys/session.
- Após `wacli sync --once`, validar com `wacli doctor --read-only --json` e, quando útil, `wacli messages list --read-only --json --limit 1`.

## Flow & Runtime
- Use repo's package manager/runtime; no swaps w/o approval.
- `aura-beta` e `aura-ui-beta` são os protótipos da esteira rápida do Aura; mantê-los sempre sincronizados, respectivamente, com a branch `beta` de `aura` e `aura-ui`. Neles, trabalhar no checkout existente; não criar worktree separada.
- Linear: slug `<ticket-number>-<descrição-curta>` sem o prefixo `aitrus-`; usar o mesmo slug em branch e worktree. Portless sem ticket: frontend `ui.<projeto>`; backend `api.<projeto>`. Com ticket: frontend `ui.<slug>.<projeto>`; backend `api.<slug>.<projeto>`. O `AGENTS.md` local registra apenas o slug estável e os comandos de desenvolvimento.
- Dev server: prefer `portless` (requires Node.js 24+); if missing, install global `npm install -g portless`; do not add dependency to project; do not say "subir o portless"; correct: subir o servidor do projeto usando `portless`, com URL no nome do projeto; para servidor iniciado por agente, passar nome explícito; `portless` sem args só quando `portless.json`/`package.json` definir nome/script e a URL inferida for clara; long-running server => `tmux` + `portless`; inside session prefer `portless <nome-do-projeto> <comando>` (ex.: projeto `api.myapp` -> `portless api.myapp pnpm dev` -> `https://api.myapp.localhost`); reportar a URL final exibida pelo `portless`; `portless` injects `PORT`, `HOST=127.0.0.1`, `PORTLESS_URL`, `NODE_EXTRA_CA_CERTS` quando HTTPS ativo; after start, always report `tmux attach -t <sessao>` + final URL.
- Servers via `tmux` (sessão sobrevive a crash): criar sessão (sem server) -> `send-keys` (start) -> informar `tmux attach -t <sessao>`. Ex:
```bash
s="$(basename "$PWD")"; tmux has -t "$s" 2>/dev/null || tmux new -d -s "$s" -c "$PWD"
tmux send -t "$s" "cd '$PWD' && portless <nome-do-projeto> pnpm dev" C-m; tmux attach -t "$s"
```

## Build / Test
- Before handoff: full gate (biome check/typecheck/tests/knip).
- Testes locais no WSL: limitar o test runner a no máximo 4 workers (`VITEST_MAX_WORKERS=4` ou opção equivalente).
- Mudança não trivial de código: usar `autoreview` antes do handoff; dispensar em docs-only, mudança trivial, revisão independente equivalente ou quando eu optar por não executar.
- Auto Review: congelar o escopo original; no máximo 2 ciclos de correção. Sem convergência, parar e classificar o restante em bloqueador do escopo, follow-up ou decisão necessária; não ampliar arquivos/LOC em mais de 2x sem aprovação.
- Segunda opinião solicitada: usar `second-opinion --repo <repository>` para chamar um único Codex ou Claude com acesso amplo para investigação e retornar um laudo Markdown livre, coerente com o tema; acompanhar heartbeat e timeout interno do runner, sem envolver a execução em timeout externo; instruir explicitamente a não alterar arquivos ou estado e não implementar a recomendação sem pedido separado.
- Mudança de comportamento observável em UI/browser: usar `visual-inspection` após a implementação e os testes; `behavior-validator` está temporariamente desabilitada.
- Quando ambos se aplicarem: `autoreview` primeiro; `visual-inspection` depois. Não executar painel ou múltiplos engines sem solicitação.
- Lint == `biome check` only (no `pnpm lint`).
- Testes visuais e browser QA: usar a skill `visual-inspection`, que chama um worker Codex externo fixado em `gpt-5.6-sol` com reasoning `medium`; entregar ao worker um handoff completo do contexto relevante e acesso total ao repositório; o worker usa `agent-browser` em sessão própria/isolada, com heartbeat e timeout interno. Não executar browser QA no agente principal, envolver o runner em timeout externo nem fazer fallback silencioso.
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
- Banco de dados relacional: preferir tipos nativos e semânticos para cada coluna; não armazenar como texto o que o banco pode representar corretamente como timestamp, número, boolean, data ou identificador. Para domínios pequenos e estáveis, usar enum no banco e enum/union tipada na aplicação, preservando o mesmo conjunto de valores. Primary keys e foreign keys devem ser fortes, compatíveis entre si e escolhidas com foco em integridade, clareza e performance.
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
- UIs devem funcionar corretamente em viewport mínima de 1024×768.
- Typography: pick a real font; avoid Inter/Roboto/Arial/system defaults.
- Theme: commit to a palette; use CSS vars; bold accents > timid gradients.
- Motion: 1-2 high-impact moments (staggered reveal beats random micro-anim).
- Background: add depth (gradients/patterns), not flat default.

Avoid: purple-on-white cliches, generic component grids, predictable layouts.
</frontend_aesthetics>
