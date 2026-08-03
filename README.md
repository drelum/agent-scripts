# Agent Scripts

Esta pasta reune os helpers de guardrail para facilitar reuso em outros repositorios e compartilhamento durante onboarding.

## Sincronizando com outros repositorios
- Trate este repositorio como o espelho canonico dos helpers de guardrail compartilhados.
- Quando alguem disser "sincronizar agent scripts", puxe as mudancas mais recentes aqui, garanta que os repositorios downstream tenham o `AGENTS.MD` no formato ponteiro, copie as atualizacoes dos helpers e reconcilie diferencas antes de seguir.
- Mantenha todos os arquivos sem dependencias e portaveis: os scripts devem rodar isolados entre repositorios. Nao adicione alias de path do `tsconfig`, pastas de codigo compartilhadas, nem duplique codigo alem do minimo necessario para manter o espelho auto-contido.

## AGENTS no formato ponteiro
- O texto de guardrail compartilhado agora vive apenas neste repo: `AGENTS.MD` (regras compartilhadas + lista de ferramentas).
- O Codex recebe uma cópia idêntica em `~/.codex/AGENTS.md`; o Claude recebe links globais em `~/.claude/CLAUDE.md` e `~/.claude/AGENTS.md` apontando para a fonte canônica.
- Os arquivos `AGENTS.md` e `CLAUDE.md` de cada repo consumidor começam com a linha `READ: ~/.codex/AGENTS.md` (regras específicas do repo só depois dessa linha, se realmente necessário).
- Nao copie mais os blocos `[shared]` ou `<tools>` para outros repositorios. Em vez disso, mantenha este repo atualizado e faca os downstream relerem o `AGENTS.MD` ao iniciar o trabalho.
- Ao atualizar as instrucoes compartilhadas, edite `agent-scripts/AGENTS.MD`, replique a mudanca em `~/.codex/AGENTS.md` e deixe os repos downstream continuarem referenciando o ponteiro.
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
- Login com escopos completos:
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
- `autoreview`: revisão source-aware isolada e estruturada com Codex ou Claude; Codex usa `gpt-5.6-sol` com reasoning `high` por padrão; suporta mudanças locais, branch e commit.
- `behavior-validator`: validação de comportamento observável; aplicações web e Electron delegam para o worker context-aware de `visual-inspection`.
- `codex-session-restorer`: localiza sessões interativas recentes do Codex e reabre cada uma em uma aba nomeada do Windows Terminal a partir do WSL.
- `second-opinion`: consulta independente com Codex ou Claude e acesso amplo ao repositório informado; produz laudo Markdown livre e coerente com o tema, progresso/heartbeat em stderr, timeout interno e logs incrementais, instruído a não alterar estado, sem usar clipboard.
- `skill-cleaner`: auditoria de inventário, orçamento de contexto, uso recente, duplicações e descrições; `--no-logs` desativa a leitura de histórico.
- `visual-inspection`: browser QA em worker Codex externo, fixado em `gpt-5.6-sol` com reasoning `medium`; recebe handoff completo e acesso total ao repositório, usa `agent-browser`, sessão isolada, progresso/heartbeat em stderr, timeout interno, evidências em `/tmp` e relatório estruturado.
