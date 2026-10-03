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
- Paths ao usuário (arquivo/pasta que eu vou abrir): mostrar SEMPRE 2 linhas, nunca link markdown `[x](y)` (Codex reescreve o destino como path relativo e o clique quebra):
  1. path Windows absoluto dentro de crases (preserva `\\`): obter com `wslpath -w <path-linux-absoluto>`; ex.: `\\wsl.localhost\Ubuntu\home\drelu\Projects\beta\x.mp4`; `/mnt/c/...` → `C:\...`.
  2. URI `file://` em texto puro, sozinho na linha, sem crases/aspas/parênteses/pontuação: `/home/...` → file://wsl.localhost/Ubuntu/home/...; `/mnt/c/...` → file:///C:/...; espaço → `%20`. É essa linha que o herdr torna clicável (plugin `herdr-windows-paths`, abre no app padrão do Windows).
  - Nunca só path relativo. Em comandos shell, manter path Linux.
- "Make a note" => edit `AGENTS.md` (shortcut; not a blocker). Ignore `CLAUDE.md`.
- Bugs: add regression test when it fits.
- Commits: Conventional Commits (`feat|fix|refactor|build|ci|chore|docs|style|perf|test`).
- Prefer end-to-end verify; blocked => say what's missing.
- New deps: quick health check (recent releases/commits, adoption).
- Web: search early; quote exact errors; prefer current primary sources; compare publication date with event/version date.
- tmux: somente jobs longos (servers, watch, builds pesados). Session = nome da pasta do projeto.
- tmux: não usar para checagens estáticas (`vp check`, typecheck, lint, formatação) ou testes.

## Docs
- Follow links until domain makes sense; honor `Read when` hints.
- Keep notes short; update docs on behavior/API changes (no ship w/o docs).
- Add `read_when` hints on cross-cutting docs.
- EVE: consultar https://eve.dev/docs/getting-started e reutilizar componentes e diretrizes de `~/Projects/eve-kit` antes de reimplementar.
- EVE/Eval: local usa `~/Projects/agent-scripts/bin/eve-eval-isolated`; Production remota usa `~/Projects/agent-scripts/bin/eve-eval-remote-production`, identidade ES256 efêmera de `~/Projects/eve-kit`, alias Production com pin antes/depois e invalidação se mudar. Casos/oráculos ficam no agente; nunca usar OIDC de Development para atravessar ambientes nem copiar o executor para o projeto.
- EVE/Vercel: enquanto qualquer dependência não for instalável no builder remoto (`link:` ou Git privado sem credencial), fazer deploy prebuilt somente pelo fluxo canônico do projeto: gate → `vercel pull --environment=production` → `vercel build --prod` → `vercel deploy --prebuilt --prod` → validar `/eve/v1/health` e uma trajetória real. Não usar `eve deploy` nesse modo; reavaliar quando todas as dependências forem instaláveis no build remoto.
- Vercel/Agent Runs: consultar logs de runtime com `vercel logs` e trajetórias estruturadas com `vercel agent-runs list|inspect|trace`; usar `vercel --help` para confirmar os comandos disponíveis na CLI instalada.
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

## Secrets & Environment
- Infisical é o Secret Manager canônico; todos os segredos e variáveis de ambiente sensíveis devem vir dele.
- Instruções locais do projeto (`AGENTS.md`, scripts, `.infisical.json`, ambiente, caminho do cofre e comando de inicialização) têm precedência; aplicações continuam lendo variáveis de ambiente, sem SDK ou abstração adicional do Infisical.
- Na ausência de configuração própria do projeto, consulte `infisical run --help` e use `infisical run -- ./mvnw spring-boot:run` para Java ou `infisical run -- <package-manager> run dev` para TypeScript.
- Nunca expor valores de segredos em comandos, logs, commits, documentação ou arquivos temporários.

## Flow & Runtime
- Use repo's package manager/runtime; no swaps w/o approval.
- `/home/drelu/Projects/beta` é o monorepo pessoal canônico `drelum/beta`; `aura-beta/`, `aura-ui-beta/` e `eve-quote-parser/` são diretórios normais, sem Git/worktree interno. Trabalho diário e pushes usam a raiz e `origin/main`. As branches `main` de Aura/Aura UI oficiais entram somente via Git subtree; as branches oficiais `beta` são apenas destinos de promoção explícita, nunca fontes. Não fazer rebase da história subtree; seguir o `AGENTS.md` local e os scripts canônicos do monorepo.
- Linear: slug `<ticket-number>-<descrição-curta>` sem o prefixo `aitrus-`; usar o mesmo slug em branch e worktree. Portless sem ticket: frontend `ui.<projeto>`; backend `api.<projeto>`. Com ticket: frontend `ui.<slug>.<projeto>`; backend `api.<slug>.<projeto>`. O `AGENTS.md` local registra apenas o slug estável e os comandos de desenvolvimento.
- Dev server: prefer `portless` (requires Node.js 24+); if missing, install global `npm install -g portless`; do not add dependency to project; do not say "subir o portless"; correct: subir o servidor do projeto usando `portless`, com URL no nome do projeto; para servidor iniciado por agente, passar nome explícito; `portless` sem args só quando `portless.json`/`package.json` definir nome/script e a URL inferida for clara; long-running server => `tmux` + `portless`; inside session prefer `portless <nome-do-projeto> <comando>` (ex.: projeto `api.myapp` -> `portless api.myapp pnpm dev` -> `https://api.myapp.localhost`); reportar a URL final exibida pelo `portless`; `portless` injects `PORT`, `HOST=127.0.0.1`, `PORTLESS_URL`, `NODE_EXTRA_CA_CERTS` quando HTTPS ativo; after start, always report `tmux attach -t <sessao>` + final URL.
- Servers via `tmux` (sessão sobrevive a crash): criar sessão (sem server) -> `send-keys` (start) -> informar `tmux attach -t <sessao>`. Ex:
```bash
s="$(basename "$PWD")"; tmux has -t "$s" 2>/dev/null || tmux new -d -s "$s" -c "$PWD"
tmux send -t "$s" "cd '$PWD' && portless <nome-do-projeto> pnpm dev" C-m; tmux attach -t "$s"
```

## Build / Test
- Antes da entrega: executar o gate canônico do repositório, conforme `AGENTS.md`, scripts e configuração locais; cobrir formatação, lint, tipos, testes, Knip e builds aplicáveis. `check` pode ser apenas a etapa estática; conferir seu conteúdo antes de tratá-lo como gate completo.
- Projetos TypeScript novos (frontend, backend Node.js, CLIs e bibliotecas): preferir Vite+ com os defaults oficiais para checagens e testes. Projetos existentes: respeitar a stack instalada; migrar somente quando autorizado, preservando runtime e gerenciador de pacotes.
- Em projetos com Vite+: usar o script local que executa `vp check` para formatação Oxfmt, lint Oxlint e tipos; verificar `lint.options.typeAware: true` e `typeCheck: true` na configuração do workspace. Referência: https://viteplus.dev/guide/check.
- Não repetir `tsc --noEmit` quando apenas duplica a cobertura de tipos do `vp check`; manter checagens adicionais quando cobrem outros tsconfigs, pacotes, declarações ou requisitos do build.
- Build e desenvolvimento devem atender ao alvo: `vp build` para aplicações web; `vp pack`/tsdown quando adequado ao empacotamento Node.js, CLIs ou bibliotecas; preservar o builder, runtime e deploy exigidos pelo framework ou provedor. Vite+ também pode fornecer checagens e testes a um backend com build próprio. Referência: https://viteplus.dev/guide/pack.
- Testes locais no WSL: limitar o test runner a no máximo 3 workers (`VITEST_MAX_WORKERS=3` ou opção equivalente).
- Mudança não trivial de código: usar `autoreview` antes do handoff; dispensar em docs-only, mudança trivial, revisão independente equivalente ou quando eu optar por não executar.
- Auto Review: congelar o escopo original; no máximo 2 ciclos de correção. Sem convergência, parar e classificar o restante em bloqueador do escopo, follow-up ou decisão necessária; não ampliar arquivos/LOC em mais de 2x sem aprovação.
- Segunda opinião solicitada: usar `second-opinion --repo <repository>` para chamar um único Codex ou Claude com acesso amplo para investigação e retornar um laudo Markdown livre, coerente com o tema; acompanhar heartbeat e timeout interno do runner, sem envolver a execução em timeout externo; instruir explicitamente a não alterar arquivos ou estado e não implementar a recomendação sem pedido separado.
- Mudança de comportamento observável em UI/browser: usar `visual-inspection` após a implementação e os testes; `behavior-validator` está temporariamente desabilitada.
- Quando ambos se aplicarem: `autoreview` primeiro; `visual-inspection` depois dos testes/builds, sem concorrência com eles; até 3 inspeções simultâneas (limite do runner). Não executar painel ou múltiplos engines sem solicitação.
- Lint e formatação seguem a ferramenta configurada no projeto; Biome continua aplicável onde ainda é adotado. Não presumir o conteúdo de `lint`, `check` ou `gate` pelo nome.
- Corrigir avisos sem usar `--quiet`, desligar regras ou reduzir escopo, asserções e cobertura para aprovar o gate. Se houver dívida preexistente ou uma exceção aprovada, reportar separadamente; não declarar zero avisos sem evidência.
- Testes visuais e browser QA: usar a skill `visual-inspection`, que chama um worker Codex externo fixado em `gpt-6-luna` com reasoning `medium` e Fast habilitado por padrão; entregar ao worker um handoff completo do contexto relevante e acesso total ao repositório; o worker usa `agent-browser` em sessão própria/isolada, com heartbeat e timeout interno. Não executar browser QA no agente principal, envolver o runner em timeout externo nem fazer fallback silencioso.
- Dependency/unused check: use `knip` to find unused dependencies, exports and files; preferir a versão e o comando locais.
- Exemplo mínimo para um projeto Vite+ com pnpm: `check`: `vp check`; `test`: `vp test run --maxWorkers=3`; `gate`: `pnpm check && pnpm test && pnpm exec knip --no-progress && pnpm build`. Adaptar ao escopo real do workspace e incluir gates de agentes, bibliotecas e validações do destino de deploy quando aplicáveis; não substituir scripts existentes por este exemplo.
- Keep it observable (logs, panes, tails).
- Observabilidade (sempre): se eu iniciar algo em `tmux`, logo em seguida informar o comando completo de attach (`tmux attach -t <sessao>`). Se eu redirecionar output para arquivo, logo em seguida informar o comando completo de tail com caminho absoluto (sem precisar `cd`): `tail -n 200 -f /caminho/completo/para/arquivo.log`.

## Git
- Safe by default: `git status/diff/log`. Push only when user asks.
- Commit/push: sempre perguntar + esperar OK explicito do Andre antes de executar (mesmo se ja foi solicitado).
- Branch changes require user consent.
- Deletes: use `trash`; permanent/destructive ops require explicit authorization (`rm`, `git reset --hard`, `git clean`, `git restore`, ...).
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
- Vite+ para novos projetos TypeScript, incluindo frontend, backend Node.js, CLIs e bibliotecas; lint e formatação conforme a configuração local nos existentes.
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
- Testes visuais e de UI usam viewport padrão de 1366×768.
- Typography: pick a real font; avoid Inter/Roboto/Arial/system defaults.
- Theme: commit to a palette; use CSS vars; bold accents > timid gradients.
- Motion: 1-2 high-impact moments (staggered reveal beats random micro-anim).
- Background: add depth (gradients/patterns), not flat default.

Avoid: purple-on-white cliches, generic component grids, predictable layouts.
</frontend_aesthetics>

<posthog>
## PostHog

Use `posthog-cli api` for all PostHog-related data queries and operations. You should use `posthog-cli api` over direct MCP tool calls whenever the CLI is available.

Before your first PostHog command in a session, run `posthog-cli api --agent-help` and load its full output into your context. It prints the complete agent guide — command reference, schema drill-down rules, data discovery workflow, and the tool index — for interacting with PostHog APIs. Treat that output as instructions to follow, not just documentation.

Before starting a PostHog task, run `posthog-cli api skill list` and check for a skill matching the task. If one matches, install it with `posthog-cli api skill install <skill-id>` (add `--force` to refresh an already-installed skill), then read `.agents/skills/<skill-id>/SKILL.md` and follow it. Skills contain task-specific workflows that individual tools do not.
</posthog>
