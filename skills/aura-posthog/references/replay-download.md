---
read_when: Acessar PostHog, localizar sessões ou baixar uma ou várias gravações para reprodução e frames locais.
---

# Acesso e download de gravações

Para investigar um erro com sessão e horário conhecidos, usar `replay-lab.md`: mesma credencial e mesmo transporte, em uma chamada. Este arquivo cobre acesso, localização de sessões e download de sessões inteiras (por exemplo, amostras de jornada).

Resolver `<skill>` pela pasta do `SKILL.md`. Python 3.11+ e CLI global `posthog-cli` com `api`; captura de frames também precisa da CLI global `agent-browser`. Sem Infisical obrigatório, SDK PostHog, Docker ou dependência Python externa. Download significa **eventos rrweb e player local**, não exportação MP4 nem criação de Replay Vision pago.

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
posthog-cli api call --json query-session-recordings-list '{"date_from":"-24h","limit":10}'
posthog-cli api call --json session-recording-get '{"id":"<session-id>"}'
```

Reusar o schema consultado; fazer drill-down antes de campos com hints. Para usuário específico, confirmar schema de pessoa/filtros ou derivar sessões dos eventos relevantes. Usar `after` com o `next_cursor` retornado para paginar; dez resultados são amostra. Para sessões já identificadas, usar `session_ids` na listagem. Propriedades/eventos precisam de descoberta antes de filtros; `$session_id` não garante gravação. Não imprimir URLs cruas de login ou property bags.

## Baixar e preparar reprodução

```bash
python3 <skill>/scripts/replay_download.py <session-id> \
  --output /caminho/privado/fora-do-git

python3 <skill>/scripts/replay_download.py <session-id-1> <session-id-2> \
  --output /caminho/privado/fora-do-git
```

Host/projeto padrão: US/331102; usar `--host` e `--project-id` explícitos para outro alvo com credencial correspondente. Não sobrescreve sessões já baixadas. Saída por ID:

- `events.json`: eventos visuais normalizados por janela, sanitizados e deduplicados; tags conhecidas de visibilidade/inatividade preservadas sem payload de plugin.
- `reproducao.html`: player rrweb embutido, pausado e com `skipInactive=false`; seleção de janela. Scripts da aplicação gravada não são executados.
- `manifest.json`: origem global da gravação, limites por janela, fontes antes/depois, hashes/tamanhos de blocos, contagens e limitações.

Diretórios novos 0700 e arquivos 0600 em Linux; no Windows, confirmar ACL da pasta privada. Snapshots/HTML/frames podem conter dados de clientes mesmo após sanitização: não versionar nem publicar brutos. Valores de inputs, URLs com query/fragment e chaves sensíveis são redigidos; isso pode alterar a aparência. Imagens/estilos externos ainda podem exigir internet e divergir do histórico.

O pacote oficial rrweb-player 2.1.7 é obtido do npm, sem instalação global/local, com SHA-512 verificado antes de embutir. Versão latest e publicação em 02/10/2026 conferidas em 08/10/2026. Para um cache offline futuro, preservar verificação de origem/integridade.

## Transporte e cobertura

Catálogo `posthog-cli api` verificado em 08/10/2026: gravações/metadados disponíveis, download de snapshots ausente. Exceção explícita para o pedido de baixar replay: **GET autenticado na API de snapshots**, mantendo metadados pelo CLI. Não trocar um 403 do CLI por REST para contornar acesso negado; preflight CLI precisa funcionar.

[Documentação de snapshots](https://posthog.com/docs/session-replay/snapshot-api): listar fontes `blob_v2=true` e buscar lotes de até 21 blocos (`start_blob_key`..`end_blob_key`, inclusivo, `decompress=true`); cada requisição conta 1 na cota `SnapshotsBurst`/`SnapshotsSustained` da personal key, independentemente do tamanho do lote, normalizar/descomprimir dados internos. Esse formato serve à UI e pode mudar; o leitor falha explicitamente em fonte/compressão desconhecida. Este helper cobre replay **web/blob_v2/gzip**, não mobile ou todos os formatos históricos.

Ritmo de 5 s entre requisições. Limites padrão por sessão: quinze minutos de leituras de snapshots, 1.000 blocos/páginas, 256 MiB recebidos, 64 MiB por resposta ou valor gzip e 500 mil eventos. CLI tem timeout por chamada. `--max-bytes`/`--max-blocks` mudam limites explicitamente; não remover limites para fazer uma consulta passar. HTTP 401/403/404/429 (com `Retry-After` na mensagem), falta de snapshot completo ou erro de formato encerram a leitura com mensagem sem conteúdo privado.

Fonte mudou ou sessão ongoing: salvar recorte e retornar código 2 com `partial=true`. Código 0 significa leitura dos blocos listados com fonte estável e sessão não ongoing; **não comprova captura integral do SDK nem revisão visual**. Se falhar depois de salvar outra sessão, preservar os resultados anteriores e registrar quais IDs ficaram pendentes. Sem retries infinitos ou exportação paga automática.

Após baixar, seguir `replay-analysis.md`. Horário do frame é relativo à janela escolhida; link PostHog usa o `start_time` global do recording. Não usar esses relógios como equivalentes em sessões com várias janelas.

Referências de credencial: [provedores do CLI](https://github.com/PostHog/posthog/blob/master/cli/src/utils/auth.rs), [POSTHOG_HOME](https://github.com/PostHog/posthog/blob/master/cli/src/utils/homedir.rs).
