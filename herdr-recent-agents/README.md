# Agentes recentes no Herdr

Ordena o painel **Agents** por estado (`blocked`, `working`, inativos) e, dentro de cada grupo, pela última mudança de estado. Agentes em atividade contínua permanecem acima dos parados, mesmo quando os outros mudaram de estado depois. Hooks atualizam a ordem quando o Herdr detecta um agente ou muda seu estado. Não equivale ao horário da última mensagem; uma mensagem sem transição de estado não muda a posição dentro do grupo.

Herdr 0.9.0 ou superior, Linux, Python 3. Sem dependências externas.

```bash
herdr plugin link /home/drelu/Projects/agent-scripts/herdr-recent-agents
herdr plugin action invoke apply --plugin andre.recent-agents
```

O hook `startup` reaplica a ordenação após reiniciar o servidor. Para desativar e remover o vínculo:

```bash
herdr plugin unlink andre.recent-agents
```
