# Agent Scripts

Esta pasta reune os helpers de guardrail para facilitar reuso em outros repositorios e compartilhamento durante onboarding.

## Sincronizando com outros repositorios
- Trate este repositorio como o espelho canonico dos helpers de guardrail compartilhados.
- Quando alguem disser "sincronizar agent scripts", puxe as mudancas mais recentes aqui, garanta que os repositorios downstream tenham o `AGENTS.MD` no formato ponteiro, copie as atualizacoes dos helpers e reconcilie diferencas antes de seguir.
- Mantenha todos os arquivos sem dependencias e portaveis: os scripts devem rodar isolados entre repositorios. Nao adicione alias de path do `tsconfig`, pastas de codigo compartilhadas, nem duplique codigo alem do minimo necessario para manter o espelho auto-contido.

## AGENTS no formato ponteiro
- O texto de guardrail compartilhado vive apenas neste repo: `AGENTS.md`.
- Codex e Claude usam links globais apontando para essa fonte canônica: `~/.codex/AGENTS.md`, `~/.claude/CLAUDE.md` e `~/.claude/AGENTS.md`.
- Os arquivos `AGENTS.md` e `CLAUDE.md` de cada repo consumidor começam com a linha `READ: ~/.codex/AGENTS.md` (regras específicas do repo só depois dessa linha, se realmente necessário).
- Nao copie mais os blocos `[shared]` ou `<tools>` para outros repositorios. Em vez disso, mantenha este repo atualizado e faca os downstream relerem o `AGENTS.MD` ao iniciar o trabalho.
- Ao atualizar as instruções compartilhadas, edite `agent-scripts/AGENTS.md`; os links globais e os ponteiros downstream passam a mudança adiante sem cópias.
- Sincronização completa de Skills e diretivas: `./script/sync-agent-environment.sh`
- Somente diretivas (global + projetos em `~/Projects`): `./script/ensure_agent_std.sh`

## Gate de qualidade (padrão)
<!-- read_when: Alterar ferramentas, scripts de validação ou instruções de qualidade dos projetos. -->

- Seguir o gate canônico de cada repositório; conferir os scripts e a configuração local. O nome `check` não garante que testes e builds estejam incluídos.
- Novos projetos TypeScript (frontend, backend Node.js, CLIs e bibliotecas): preferir Vite+ com os defaults oficiais para checagens e testes. Projetos existentes mantêm sua stack até uma migração autorizada; Biome continua válido onde instalado.
- Em projetos Vite+, `vp check` reúne formatação, lint e tipos. Confirmar `lint.options.typeAware: true` e `typeCheck: true`; consultar a [documentação oficial](https://viteplus.dev/guide/check).
- O gate completo acrescenta testes com no máximo três workers, Knip e builds aplicáveis. Preferir versões e comandos locais; manter `tsc` adicional apenas quando atende outro escopo ou requisito de build/declarações.
- Adaptar build e desenvolvimento ao alvo: `vp build` para aplicações web e [`vp pack`/tsdown](https://viteplus.dev/guide/pack) quando adequado ao empacotamento Node.js, CLIs ou bibliotecas. Manter os comandos de runtime, build e deploy exigidos pelo framework ou provedor; o backend pode usar Vite+ para checagens e testes com build próprio.
- Exemplo mínimo com pnpm: `check`: `vp check`; `test`: `vp test run --maxWorkers=3`; `gate`: `pnpm check && pnpm test && pnpm exec knip --no-progress && pnpm build`. Incluir os demais gates do workspace; não sobrescrever scripts existentes com este exemplo.
- Corrigir avisos sem ocultá-los com `--quiet`, desligar regras ou reduzir a cobertura. Reportar dívida preexistente e exceções aprovadas separadamente.
- O Painel já usa Vite+ e seu `pnpm gate` inclui os agentes e o Eve Kit externo; cada componente conserva suas verificações próprias.

## agent-browser
<!-- read_when: Instalar, atualizar ou diagnosticar versões do agent-browser no WSL e Windows. -->

- Usar a CLI global: WSL nos fluxos Linux; Windows no wrapper `windows-chrome-browser`. Evitar `npx` e dependências locais nos projetos.
- Consultar `npm view agent-browser version`; instalar a mesma versão explícita com `npm install -g agent-browser@<versão>` no WSL, em cada Node utilizado pelo NVM, e no Windows.
- Validar `agent-browser --version` em cada ambiente e carregar `agent-browser skills get core`. O clone em `~/Projects/oss/agent-browser` é fonte de consulta, não uma instalação da CLI.
- Atualizações não encerram sessões existentes. Daemons antigos ou backups bloqueados por processos Windows devem ser tratados após o encerramento autorizado dessas sessões.
- Em 05/10/2026, versão 0.38.2 instalada nos dois ambientes; execução validada no WSL. No Windows, Device Guard bloqueou o novo executável por requisito de assinatura (evento Code Integrity 3077). Instalação concluída não comprova execução; não desabilitar a política como parte da atualização.

## Exclusão recuperável
- `./bin/trash <caminho> [...]`: wrapper canônico para `gio trash`; publicar como `~/.local/bin/trash` para funcionar também em agentes e shells não interativos.

## Google Workspace / GWS
- CLI base: `gws`.
- Wrappers por conta:
  - `./bin/gws-aitrus`: usa `~/.config/gws-aitrus`; conta esperada `andre@aitrus.com.br`.
  - `./bin/gws-pessoal`: usa `~/.config/gws-pessoal`; conta esperada `drelum@gmail.com`.
- Use sempre o wrapper explicito quando a conta importar. Evite chamar `gws` diretamente para Drive/Gmail/Docs/Sheets/Slides.
- Login Aitrus para os serviços usados pelo assistente:
  `./bin/gws-aitrus auth login --services gmail,calendar,drive,docs,sheets,slides`
- Não usar `--full` nesse fluxo: ele acrescenta `cloud-platform`, submetendo o token ao Google Cloud Session Control e ao erro `invalid_rapt`. Após o login, confirmar em `./bin/gws-aitrus auth status` que `cloud-platform` não aparece em `scopes`; se persistir por grant anterior, revogar/limpar a autorização antiga e autenticar novamente.
- Login pessoal:
  `./bin/gws-pessoal auth login --services gmail,calendar,drive,docs,sheets,slides`
- GWS pessoal: cliente OAuth Desktop no projeto Google Cloud `pessoal-drelum` (número `267502056062`), conta `drelum@gmail.com`; evitar `--full` e conferir ausência de `cloud-platform` após login.
- Cofre pessoal: projeto Infisical **Pessoal** (`afbf1c7e-b8ce-4ec6-a1da-128767aad718`), ambiente `dev`, pasta `/GWS`. Segredos `GWS_PESSOAL_CLIENT_JSON` e `GWS_PESSOAL_CREDENTIALS_JSON`; acessar pelo perfil autorizado, sem imprimir valores. O wrapper mantém a configuração nativa local; outros hosts precisam provisionar as credenciais a partir desse cofre.
- Em 05/10/2026, OAuth pessoal External/In production, com nova autorização validada após a mudança. Página inicial `https://drelum.github.io/` e política `https://drelum.github.io/privacidade/`; fontes no repositório público `drelum/drelum.github.io`. O aplicativo continua sem verificação formal do Google e pode exibir esse aviso no login. Se retornar a Testing, as autorizações voltam a ter limite de sete dias; conferir a audiência e o status antes de reautenticar.

## Eve Eval isolado
- Timeouts de transporte pertencem ao EVE instalado. O wrapper não define `WORKFLOW_LOCAL_BODY_TIMEOUT_MS`/`WORKFLOW_LOCAL_HEADERS_TIMEOUT_MS`; preserva overrides explícitos e registra `null` quando ausentes. EVE ≥0.45.2 já evita replay de entregas longas. Limite a bateria com `timeoutMs`/`--timeout` nativos, não com um timeout HTTP menor.
- `./bin/eve-eval-isolated [argumentos]`: em Linux/WSL com `flock` (`util-linux`), executa `eve eval` local com `.eve/.workflow-data` novo, preserva `.eve/m` e arquiva os stores anterior e produzido em `.eve/eval-isolated-runs/`.
- `./bin/eve-eval-remote-production --audience <aud> -- <comando>`: usa a identidade efêmera do `eve-kit`, fixa o deployment Production antes/depois e invalida a bateria se o alias mudar.
- Skill canônica: `eve-isolated-evals`. Ela separa isolamento local de workflow e isolamento remoto de identidade/deployment.
- `eve-experiment`: coordena baseline, hipótese, alteração, bateria e decisão; reutiliza gates, artefatos e deployments quando o estado não mudou.

## Skills do Codex
- Fonte canonica unica: `skills/*/SKILL.md`.
- `linkedin-x-readonly`: consultas de LinkedIn e X via executável global `opencli` no PATH, com perfil `social` explícito e operações exclusivamente de leitura; sem dependência do laboratório.
- Validação de front matter, campos obrigatórios e nomes duplicados: `./script/validate-skills`
- Validação antes de cada commit: `git config core.hooksPath hooks`
- Sincronização completa recomendada: `./script/sync-agent-environment.sh`
- Somente publicação global para Codex e Claude: `./script/sync-codex-skills.sh`
- O script cria links simbólicos individuais para a fonte canônica; não copia skills e não substitui diretórios reais ou links estrangeiros.
- Destinos padrão: `~/.agents/skills` para Codex e `~/.claude/skills` para Claude.
- Dry-run: `./script/sync-codex-skills.sh --dry-run`
- Destinos customizados: `--codex-target /caminho` e `--claude-target /caminho`.
- Substituição explícita de diretórios reais com nomes canônicos: `./script/sync-codex-skills.sh --replace-existing`.

### Skills canônicas
- `aura-incident-investigation`: investigação somente leitura de frontend, backend, cotação e Sync; correlaciona logs, eventos/sessões PostHog e dados persistidos, prioriza impacto e prepara diagnósticos/tickets. Usa `aura-posthog` para download, reprodução e frames; inclui onboarding e auxiliares de acesso portáteis.
- `aura-store-data-diagnosis`: diagnóstico somente leitura de divergências de estoque, vendas e custo do ERP; rastreia aquisição, transformação, bases, API e tela, com identidade e horários comparáveis.
- `aura-posthog`: análise somente leitura do uso do Aura no PostHog (navegação, carrinho, envio de pedido e erros), com descoberta de eventos a cada uso, resolução de e-mail pelo cadastro Aura e mascaramento de tokens; executor em `skills/aura-posthog/scripts/aura-posthog`.
- Desabilitadas (`.disabled`, fora da publicação): `aura-beta-promotion`, `aura-beta-browser` e `aura-novidades` (monorepo Beta); `behavior-validator`.
- `aura-packaging`: diagnostica empacotamento de um EAN (cotação, NF, venda, custo) via script somente leitura; CNPJ padrão `05101867000157`.
- `autoreview`: revisão source-aware isolada com Codex ou Claude; aceita segredos e caminhos sensíveis no bundle/repositório, sem herdar credenciais do ambiente; valida a resposta estruturada internamente e entrega relatório Markdown; Codex usa `gpt-6.1-sol` com reasoning `high` por padrão.
- `behavior-validator`: temporariamente desabilitada por `skills/behavior-validator/.disabled`.
- `codex-session-restorer`: localiza sessões interativas recentes do Codex e reabre cada uma em uma aba nomeada do Windows Terminal a partir do WSL.
- `eve-experiment`: executa ciclos medidos de melhoria de agentes EVE sem repetir gates, builds ou deployments do mesmo estado.
- `eve-isolated-evals`: executa baterias locais sobre workflow store novo e baterias remotas em Production com identidade efêmera e pin de deployment.
- `implementation-delegator`: permite ao Claude Code delegar uma implementação delimitada a um worker Codex com acesso total ao repositório, progresso incremental e sem timeout automático.
- `second-opinion`: consulta independente com Codex ou Claude e acesso amplo ao repositório informado; produz laudo Markdown livre e coerente com o tema, progresso/heartbeat em stderr, timeout interno e logs incrementais, instruído a não alterar estado, sem usar clipboard.
- `skill-cleaner`: auditoria de inventário, orçamento de contexto, uso recente, duplicações e descrições; `--no-logs` desativa a leitura de histórico.
- `visual-inspection`: browser QA em worker Codex externo, fixado em `gpt-6-luna` com reasoning `medium` e Fast habilitado por padrão; recebe handoff completo e acesso total ao repositório, usa `agent-browser`, sessão isolada, progresso/heartbeat em stderr, timeout interno, evidências em `/tmp` e relatório Markdown.
- `windows-chrome-browser`: controla somente páginas e abas em perfis persistentes do Chrome Windows a partir do WSL, preservando autenticação humana e isolando CDP, sessão e aba.

Uma skill com marcador `.disabled` permanece na fonte canônica, mas não é publicada para Codex ou Claude. Remova o marcador e execute a sincronização para reativá-la.
