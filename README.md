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
