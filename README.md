# Agent Scripts

Esta pasta reune os helpers de guardrail para facilitar reuso em outros repositorios e compartilhamento durante onboarding.

## Sincronizando com outros repositorios
- Trate este repositorio como o espelho canonico dos helpers de guardrail compartilhados.
- Quando alguem disser "sincronizar agent scripts", puxe as mudancas mais recentes aqui, garanta que os repositorios downstream tenham o `AGENTS.MD` no formato ponteiro, copie as atualizacoes dos helpers e reconcilie diferencas antes de seguir.
- Mantenha todos os arquivos sem dependencias e portaveis: os scripts devem rodar isolados entre repositorios. Nao adicione alias de path do `tsconfig`, pastas de codigo compartilhadas, nem duplique codigo alem do minimo necessario para manter o espelho auto-contido.

## AGENTS no formato ponteiro
- O texto de guardrail compartilhado agora vive apenas neste repo: `AGENTS.MD` (regras compartilhadas + lista de ferramentas).
- O `AGENTS.MD` de cada repo consumidor fica reduzido a linha: `READ: ~/.codex/AGENTS.md` (regras especificas do repo so depois dessa linha, se realmente necessario).
- Nao copie mais os blocos `[shared]` ou `<tools>` para outros repositorios. Em vez disso, mantenha este repo atualizado e faca os downstream relerem o `AGENTS.MD` ao iniciar o trabalho.
- Ao atualizar as instrucoes compartilhadas, edite `agent-scripts/AGENTS.MD`, replique a mudanca em `~/.codex/AGENTS.md` e deixe os repos downstream continuarem referenciando o ponteiro.
- Padronizacao (global + projetos em `~/Projects`): `./script/ensure_agent_std.sh`

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
- Publicacao global: `./script/sync-codex-skills.sh`
- Destino padrao: `~/.agents/skills`, que o Codex CLI atual descobre automaticamente; reinicie o Codex se uma skill nova nao aparecer.
- Dry-run: `./script/sync-codex-skills.sh --dry-run`
- Destino customizado: `./script/sync-codex-skills.sh --target /caminho/skills`

## Slash commands legados
- Fonte legada: `commands/*.md`.
- Publicacao legada: `./script/sync-codex-prompts.sh`
- O Codex CLI 0.117+ nao lista mais `~/.codex/prompts` no menu `/`; use skills com `$` ou pelo menu de skills.
