# Roteiros de análise

Cada roteiro começa pela descoberta. Troque os nomes de exemplo pelos que `aura-posthog events/props` mostrarem hoje.
Os trechos usam `{{USER_ID}}` e `{{IDENTIFIED}}`, expandidos pelo executor.

## 1. Jornada de um usuário

1. `aura-posthog user <email>`: ID, hosts, sessões, dias, primeiro e último evento.
2. Sessões com entrada e sequência de páginas, sem query string:

```sql
SELECT $session_id AS sessao, toString(properties.$host) AS host,
  formatDateTime(toTimeZone(min(timestamp), 'America/Sao_Paulo'), '%d/%m/%Y %H:%i') AS inicio,
  argMinIf(toString(properties.$pathname), timestamp, event = '$pageview') AS entrada,
  argMinIf(multiIf(coalesce(toString(properties.$referrer), '') IN ('$direct', ''), 'direta', domain(toString(properties.$referrer))), timestamp, event = '$pageview') AS origem,
  argMinIf(decodeURLComponent(extractURLParameter(toString(properties.$current_url), 'redirect_uri')), timestamp, toString(properties.$pathname) = '/login') AS destino_login,
  arrayStringConcat(arrayMap(x -> x.2, arraySlice(arraySort(x -> x.1, groupArrayIf((timestamp, toString(properties.$pathname)), event = '$pageview')), 1, 10)), ' > ') AS telas,
  countIf(event = 'cart_item_added') AS itens, countIf(event = 'cart_checkout_succeeded') AS envios, countIf(match(event, '(?i)fail|error|exception')) AS erros
FROM events
WHERE timestamp >= now() - INTERVAL 30 DAY AND notEmpty($session_id) AND {{IDENTIFIED}} AND {{USER_ID}} = '685'
GROUP BY sessao, host ORDER BY min(timestamp) DESC LIMIT 200
```

3. Para uma sessão específica, eventos em ordem (`timestamp`, `event`, `$pathname`, propriedades próprias relevantes).
   Normalizar IDs em rotas com `replaceRegexpAll(path, '/[0-9]+', '/:id')` ao agregar.

## 2. Carrinho e envio

- Funil por sessão: sessões com item adicionado → envio iniciado → envio com sucesso; separar falha explícita de
  abandono (iniciou sem sucesso e sem falha).
- Quebras úteis: `cart_item_added.source`, host, `user_role`, dia/hora em São Paulo, `total_price` do envio.
- Tempo entre o primeiro item e o envio na mesma sessão (`dateDiff('minute', minIf(...), minIf(...))`).
- Lembrar: sem EAN ou produto nos eventos; para itens e distribuidores, cruzar com o ClickHouse (roteiro 5).

## 3. Erros no carrinho e no envio (prioridade)

1. Descobrir eventos de falha vigentes: `aura-posthog events --match "fail|error|refus|invalid|reject|exception"`.
2. Falhas explícitas com motivo, por dia, host e usuário:

```sql
SELECT toDate(toTimeZone(timestamp, 'America/Sao_Paulo')) AS dia, toString(properties.$host) AS host, event,
  toString(properties.reason) AS motivo, left(toString(properties.error_message), 160) AS mensagem,
  count() AS ocorrencias, uniq(distinct_id) AS usuarios
FROM events WHERE timestamp >= now() - INTERVAL 30 DAY AND event IN ('cart_checkout_failed', 'order_create_failed')
GROUP BY dia, host, event, motivo, mensagem ORDER BY dia DESC, ocorrencias DESC
```

3. Contexto da falha: o que o usuário fez nos 5 minutos antes (eventos da mesma sessão com `timestamp` entre
   a falha − 5 min e a falha), se tentou de novo e se enviou com sucesso depois.
4. Erros sem evento próprio (ex.: ao adicionar item no carrinho, tela "Algo deu errado"):
   - `$exception` na mesma sessão (só erros não tratados; zero não prova ausência de erro);
   - console das gravações, agrupado por mensagem e ligado à sessão:

```sql
SELECT left(replaceRegexpAll(message, '[0-9a-f]{8}-[0-9a-f-]{27}|[0-9]{4,}', '#'), 150) AS mensagem,
  count() AS ocorrencias, uniq(log_source_id) AS sessoes, max(toDate(toTimeZone(timestamp, 'America/Sao_Paulo'))) AS ultimo
FROM console_logs_log_entries
WHERE timestamp >= now() - INTERVAL 14 DAY AND level = 'error' AND NOT match(message, 'ResizeObserver|PostHog.js')
GROUP BY mensagem ORDER BY ocorrencias DESC LIMIT 50
```

   - `log_source_id` é o `$session_id`: juntar com `events` para usuário, tela e ações próximas;
   - gravações da sessão com `console_error_count > 0` via `posthog-cli api call query-session-recordings-list`;
   - sinais de comportamento: vários `cart_item_added` seguidos sem avanço, `$dead_click` concentrado na tela do
     carrinho ou ofertas, `cart_checkout_started` sem sucesso nem falha.
5. Relatar separando **falha registrada** de **indício**. Se a pergunta exigir evento que não existe, dizer e sugerir
   a instrumentação (ex.: `cart_item_add_failed` com `reason` e `error_message`).

## 4. Navegação e origem

- Entrada por sessão: tabela `sessions` (`$entry_pathname`, `$entry_referring_domain`, `$session_duration`,
  `$pageview_count`) ou o `argMin` de `$pageview` (dá também o `redirect_uri` do login).
- Link ou escolha: entrada por `/login` com `redirect_uri` = destino definido pelo link do portal; sessão que começa
  num módulo e depois vai a outro = navegação escolhida dentro do Aura; entrada direta sem referrer = favorito,
  aba reaberta ou link externo (indistinguíveis).
- Perfil por usuário: módulo dominante pelos prefixos de eventos próprios; dias ativos; quantidade de módulos.

## 5. Cruzamento com pedidos no ClickHouse

- Usar a skill `aura-clickhouse`: `analytics.order_item_internal` (pedidos do Aura; `invoice_type` ≠ `AUTO` para
  manuais; `created_by_email`, `cart_id`, `order_created_at`).
- Casar envio do PostHog com carrinho do ClickHouse por usuário (e-mail do cadastro ↔ `created_by_email`) e janela
  de alguns minutos. Comparar contagens diárias antes de afirmar perda ou duplicidade.
