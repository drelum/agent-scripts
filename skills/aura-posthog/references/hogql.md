# HogQL no PostHog do Aura

Ler antes de montar consultas não triviais. Verificado em 23/09/2026 com chave pessoal via `posthog-cli`.

## Limites

- `execute-sql` devolve **no máximo 500 linhas**, mesmo com `LIMIT` maior (`LIMIT 50000` também para em
  500). **Sem `LIMIT`, só 100.** Remedido em 19/10/2026: `numbers(500)` sem `LIMIT` → 100; `numbers(3000)
  LIMIT 50000` → 500. Resultado com exatamente 100 ou 500 linhas está cortado, sem aviso do PostHog.
- Para mais, paginar por chave: `ORDER BY <chave> LIMIT 500` e, na próxima chamada, `AND <chave> > '<última>'`;
  por instante: `timestamp >= <último>` com `ORDER BY timestamp, uuid` e descartar `uuid` repetido; ou dividir a
  lista do `IN` em lotes e repartir o lote que voltar com 500.
- `"$ph" sql` exige `LIMIT` no fim e sai com erro (código 3) quando o resultado chega ao teto.
- **`OFFSET` não é aceito** com chave pessoal.
- Alias de `SELECT` nem sempre resolve em `GROUP BY` com expressões longas: declare `expr AS nome` no `SELECT`
  e agrupe por `nome`.

## Funções

| Evitar | Usar |
|---|---|
| `toUInt64OrZero` | `toIntOrZero` |
| `toUnixTimestamp64Micro` | `toUnixTimestamp64Milli` |
| `uniqArray` | `uniq` com `ARRAY JOIN` |
| `arr[1]` em propriedade possivelmente nula | `arrayElement(coalesce(...), 1)` |

Úteis: `cutQueryStringAndFragment`, `extractURLParameter`, `extractURLParameterNames`, `decodeURLComponent`,
`domain`, `JSONExtractArrayRaw`, `JSONExtractKeys`, `JSONHas`, `argMin/argMinIf`, `toTimeZone`.

## Propriedades

- Acesso por ponto só para chaves válidas (`properties.$pathname`); demais com colchetes: `properties['chave-x']`.
- Propriedade inexistente gera aviso de taxonomia (o executor mostra em stderr): trate como nome errado ou evento
  que mudou, não como zero.
- `store_ids` é JSON: `arrayMap(x -> replaceAll(x, '"', ''), JSONExtractArrayRaw(coalesce(toString(properties.store_ids), '[]')))`.

## Tabelas

- `events`: fonte principal.
- `sessions`: `$entry_pathname`, `$end_pathname`, `$entry_referring_domain`, `$session_duration`, `$pageview_count`,
  `$channel_type`, `$urls` (**contém tokens**), `$emails` (dados pessoais).
- `persons`: propriedades de pessoa (`user_role`, `chain_ids`, `store_count`); sem e-mail confiável.
- Gravações: `posthog-cli api call --json query-session-recordings-list '{"date_from":"-7d","limit":20}'`
  (rodar `info` antes para os filtros); campos `start_url` (mascarar), `console_error_count`, `click_count`,
  `recording_duration`.

## Assíncrono

A API do PostHog pode responder 504 em consultas síncronas longas. O `posthog-cli` cuida disso; se escrever
cliente próprio, usar `async: true` e polling de `GET /api/projects/331102/query/<id>/` (ver `server/posthogClient.ts`
no repositório `painel`).
