---
read_when: Acessar PostHog, localizar sessões ou baixar uma ou várias gravações para reprodução e frames locais.
---

# Acesso e download de gravações

Este arquivo cobre acesso e localização de sessões. Para download, preparação, investigação e evidências,
usar somente `scripts/replay_investigate`, conforme `replay-investigation.md`. O transporte baixa eventos
rrweb pela API de snapshots; o vídeo e seus frames são produzidos localmente pelo mesmo pipeline.

## Primeiro acesso

Na própria máquina, executar interativamente:

```bash
posthog-cli --host https://us.posthog.com login
posthog-cli api --agent-help
posthog-cli api skill list
posthog-cli api info project-get
```

Selecionar o projeto Aura **331102**. O retorno de projeto contém token de captura: não despejar nem salvar a resposta completa; projetar ID, nome e timezone. O login usa a autorização suportada pela versão instalada do CLI; nunca pedir a credencial de um colega. Conferir acesso de leitura ao projeto e `session_recording:read`; erro 403 exige conferir o escopo específico, sem ampliar permissões automaticamente.

O downloader escolhe uma fonte inteira, em memória:

- Ambiente: `POSTHOG_CLI_API_KEY` + `POSTHOG_CLI_PROJECT_ID` + host opcional `POSTHOG_CLI_HOST`; aliases legados TOKEN/ENV_ID também reconhecidos. O cofre da pessoa pode injetá-los no processo, sem valores nos comandos.
- Login do CLI, quando não há credencial no ambiente: `credentials.json` em `POSTHOG_HOME` ou `~/.posthog`, padrão público do CLI. O downloader lê apenas o arquivo da própria pessoa, sem imprimir/copiar o token. Não busca históricos, credenciais de outros processos ou caminhos da máquina de André.

Ambiente parcialmente definido é erro; não misturar fontes. Host/projeto da credencial precisam corresponder ao pedido. Não passar API key por argumento nem criar arquivo temporário com o segredo. O script não interpreta arquivos dotenv: usar login ou ambiente já injetado.

## Localizar gravações

```bash
posthog-cli api search 'session-recording'
posthog-cli api info query-session-recordings-list
posthog-cli api info session-recording-get
posthog-cli api call --json query-session-recordings-list '{"date_from":"-24h","order":"start_time","order_direction":"DESC","limit":20}'
posthog-cli api call --json session-recording-get '{"id":"<session-id>"}'
```

Reusar o schema consultado; fazer drill-down antes de campos com hints. Para usuário específico, confirmar schema de pessoa/filtros ou derivar sessões dos eventos relevantes. Usar `after` com o `next_cursor` retornado para paginar; dez resultados são amostra. Para sessões já identificadas, usar `session_ids` na listagem. Propriedades/eventos precisam de descoberta antes de filtros; `$session_id` não garante gravação. Não imprimir URLs cruas de login ou property bags.

Para pilotos e lotes, selecionar **sessões encerradas por padrão**: ordenar por `start_time DESC`,
reter somente resultados com `ongoing` exatamente `false` e então pegar a quantidade pedida.
`true`, `null` ou campo ausente não confirmam encerramento. Buscar uma página maior que o lote e,
se faltar quantidade, paginar pelo cursor retornado; não completar o lote com sessões abertas nem
inventar um filtro de API não previsto no schema. Guardar IDs, horários e estado na seleção privada.
Revalidar os IDs pela listagem imediatamente antes do download. Manter a verificação de estabilidade
dos snapshots: `ongoing: false` não garante que todo bloco já terminou de chegar. Sessão aberta só
entra quando o pedido exigir explicitamente aquela gravação ou investigação em andamento.

## Preparar a sessão localizada

Seguir `replay-investigation.md`: `replay_investigate prepare --session <uuid> --name <nome>`.
Para lote recente: `prepare --latest <n> --name <prefixo>`. O executor seleciona/revalida sessões
encerradas e prepara contexto paginado, vídeo integral disponível e índice antes da análise.
Host/projeto padrão: US/331102; outro alvo exige `--host` e `--project` com credencial correspondente.
Não usar o player/download antigo como caminho alternativo. Diretórios privados novos 0700 e arquivos
0600; snapshots, imagens e pacotes podem conter dados de clientes mesmo após sanitização.

## Transporte

Catálogo CLI verificado em 08/10/2026: snapshots não expostos; metadados continuam pelo CLI. Exceção
explícita: GET autenticado na [API de snapshots](https://posthog.com/docs/session-replay/snapshot-api).
Não contornar um 403 do CLI nem ampliar escopos automaticamente. A cota é por personal key; respeitar
`Retry-After` em 429. Lotes de até 21 blocos, cache verificado e cauda revalidada no pipeline canônico.
Fontes que mudam durante o download impedem publicação; não apresentar sessão parcial como completa.
