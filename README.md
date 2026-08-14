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
- Lint: usar `biome check` (nao usar `pnpm lint`).
- Incluir `knip` no check para detectar dependencias, exports e arquivos nao utilizados.
- Exemplo de script `check`:
  `biome check && pnpm exec tsc -p tsconfig.json --noEmit && pnpm test && pnpm dlx knip --no-progress`

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
  `./bin/gws-pessoal auth login --services drive,docs,sheets,slides,gmail`
- Se a conta pessoal falhar com permissao do projeto Google, confirmar que `drelum@gmail.com` esta como OAuth test user e com IAM `Service Usage Consumer` no projeto OAuth.

## Skills do Codex
- Fonte canonica unica: `skills/*/SKILL.md`.
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
- `autoreview`: revisão source-aware isolada com Codex ou Claude; valida a resposta estruturada internamente e entrega relatório Markdown; Codex usa `gpt-5.6-sol` com reasoning `high` por padrão; suporta mudanças locais, branch e commit.
- `behavior-validator`: temporariamente desabilitada por `skills/behavior-validator/.disabled`.
- `codex-session-restorer`: localiza sessões interativas recentes do Codex e reabre cada uma em uma aba nomeada do Windows Terminal a partir do WSL.
- `second-opinion`: consulta independente com Codex ou Claude e acesso amplo ao repositório informado; produz laudo Markdown livre e coerente com o tema, progresso/heartbeat em stderr, timeout interno e logs incrementais, instruído a não alterar estado, sem usar clipboard.
- `skill-cleaner`: auditoria de inventário, orçamento de contexto, uso recente, duplicações e descrições; `--no-logs` desativa a leitura de histórico.
- `visual-inspection`: browser QA em worker Codex externo, fixado em `gpt-5.6-sol` com reasoning `medium`; recebe handoff completo e acesso total ao repositório, usa `agent-browser`, sessão isolada, progresso/heartbeat em stderr, timeout interno, evidências em `/tmp` e relatório Markdown.
- `windows-chrome-browser`: controla somente páginas e abas em perfis persistentes do Chrome Windows a partir do WSL, preservando autenticação humana e isolando CDP, sessão e aba.

Uma skill com marcador `.disabled` permanece na fonte canônica, mas não é publicada para Codex ou Claude. Remova o marcador e execute a sincronização para reativá-la.
