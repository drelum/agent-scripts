---
name: portless-hygiene
description: Auditar rotas e servidores locais do Portless, identificar ambientes esquecidos e encerrar alvos autorizados ao finalizar tarefas ou revisar worktrees. Não executa limpeza durante uma auditoria.
---

# Higiene do Portless

Separar saúde técnica de necessidade de manter um ambiente. Servidor vivo no
tmux pode sobreviver ao encerramento do trabalho; commit, merge e silêncio da
conversa não provam que pode ser desligado.

## Auditoria

Usar a CLI global instalada. Confirmar `portless --version`, `portless --help`
e a ajuda dos subcomandos relevantes; opções e formato do estado podem mudar.
Começar sem alterações:

```bash
portless list
portless doctor
tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index} pid=#{pane_pid} command=#{pane_current_command} cwd=#{pane_current_path}'
```

Consultar o diretório de estado indicado pelo `doctor`, incluindo override de
`PORTLESS_STATE_DIR`. Se necessário, ler somente os campos de rotas; não
imprimir chaves privadas, certificados ou ambientes dos processos. Na versão
0.15.7, `routes.json` é uma lista com `hostname`, `port` e `pid`; isto é uma
observação, não um contrato permanente. `pid=0` representa alias estático.

Para cada rota, correlacionar:

- PID registrado, identidade/início do processo, cwd e árvore de descendentes.
  O PID da rota é do controlador Portless; o listener pode ser um descendente.
- Porta escutando, PID do listener e vínculo com essa árvore. Conexão TCP
  sozinha não identifica o dono nem comprova funcionamento da aplicação.
- Pane exato de tmux encontrado pela cadeia de ancestrais; não deduzir apenas
  pelo nome da sessão. Um pane pode executar vários serviços.
- Repositório/worktree e branch, quando houver: `git -C <cwd> rev-parse
  --show-toplevel`, `git -C <raiz> worktree list --porcelain` e status curto.
  Cwd temporário, ausente ou marcado como removido é sinal para investigação.
- Situação da tarefa na fonte canônica: `beta-tickets.md` para Beta; Linear
  somente quando pertinente. Ausência de registro significa desconhecido.
- Dependências entre aplicações e infraestrutura compartilhada, consultando
  configuração com saída restrita a URLs não secretas. Não desligar backend,
  mock ou túnel usado por outro ambiente que será mantido.

Evitar comandos com argumentos completos e dumps de logs/ambientes: podem
conter tokens. Não fazer checkout, fetch, prune de worktrees ou editar fontes
de tickets para completar a auditoria.

Entregar tabela agrupada por ambiente: rotas, diretório, pane, tempo de
execução, saúde observada, tarefa, recomendação e evidência. Horários em
São Paulo, formato brasileiro. Explicitar incertezas; idade do processo não
é tempo sem uso, e HTTP 404/401 na raiz não prova falha de uma API.

## Decisão

| Classe | Critério | Ação proposta |
| --- | --- | --- |
| Manter | Necessidade explícita atual ou dependência de ambiente mantido | Preservar; registrar motivo |
| Revisar | Piloto, preview, tarefa encerrada ou servidor antigo sem necessidade confirmada | Propor encerramento; idade sozinha não basta |
| Órfão técnico | Controlador morto; verificar dono atual da porta e descendentes | Propor recuperação delimitada |
| Desconhecido | Identidade, tarefa ou dependências sem evidência suficiente | Preservar até esclarecer |

Separar a recomendação da autorização. Pedido de diagnóstico não autoriza
encerrar processos. Pedido explícito para encerrar alvos identificados autoriza
esse escopo; não pedir de novo se a autorização já foi dada na conversa.

## Encerramento autorizado

Antes da ação, revalidar rota, PID, início do processo, cwd, listener e pane:
PID e porta podem ser reutilizados entre auditoria e execução. Se a identidade
mudar ou houver dependência não resolvida, parar aquele alvo e explicar.

Encerrar pelo controlador Portless com sinal gracioso ou pelo pane exclusivo
confirmado. `Ctrl+C` num pane com tarefa diferente pode interromper outro
trabalho; não usar indiscriminadamente. Aguardar a saída dos descendentes e
confirmar rota ausente, processos encerrados e porta livre. Registrar eventual
órfão restante. Não escalar automaticamente para SIGKILL.

Na versão 0.15.7, `portless prune` é uma mutação global: remove rotas cujo
controlador morreu e pode sinalizar quem estiver usando suas portas. Não tem
dry-run nem seleção por nome. Só usar se todos os alvos encontrados estiverem
autorizados e a identidade dos listeners estiver comprovada. Não resolve um
servidor esquecido cujo controlador continua vivo.

Para aliases, remoção da rota e encerramento do servidor são ações distintas;
usar `portless alias --remove <nome>` somente no alias autorizado. Não editar
`routes.json` manualmente para simular encerramento.

Não usar `portless clean`, `proxy stop`, `--force`, `pkill` amplo ou
`tmux kill-server` como higiene rotineira. Não remover worktrees, arquivos,
certificados ou sessões tmux inteiras. Finalizar com inventário antes/depois,
`portless doctor` e estado das rotas preservadas. Informar limites do teste;
porta aberta e doctor verde não equivalem a uma trajetória E2E.

## Prevenção no ciclo de trabalho

Ao iniciar um servidor, conferir se o ambiente correto já existe. Registrar
na tarefa as rotas, cwd/worktree, pane, finalidade e dependências, usando a
fonte existente; não criar um segundo cadastro de tickets. Distinguir ambiente
temporário de ambiente que André pediu para manter, com motivo explícito.

Ao concluir ou cancelar a tarefa, e antes de remover a worktree, incluir no
handoff a decisão sobre seus servidores: encerrados, mantidos com motivo ou
aguardando autorização. Se já houver autorização para o ciclo completo de
criar e encerrar os servidores temporários, executar dentro desse escopo.

Revisão diária pode gerar relatório, quando solicitada; desligamento por TTL
exige política explícita. Não instalar cron/daemon nem configurar fechamento
automático por inatividade. A skill atua quando invocada ou selecionada pelo
agente; sozinha não agenda nem observa o encerramento de outras conversas.

Fonte dos comandos: https://github.com/vercel-labs/portless
