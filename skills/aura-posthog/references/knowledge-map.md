# Mapa de conhecimento do PostHog do Aura

Verificado em 23/09/2026, janela de 30 dias. **Conhecimento datado:** reconfirme com `aura-posthog events`,
`props` e `values` antes de depender de um nome. Ao encontrar diferença, atualize este arquivo com a data.

## Projeto e hosts

- Projeto PostHog `331102` (`us.posthog.com`).
- Hosts observados: `otimiza.aitrus.com.br` (maior volume), `app.aitrus.com.br`, `aura.aitrus.com.br`,
  `adfar.aitrus.com.br`, `retailjedi.aitrus.com.br`, `jcruz.aitrus.com.br`, `v2.aitrus.com.br`, `*.localhost`.
  Todos podem ser uso real; trate host como dimensão.

## Identidade

- `distinct_id` = ID numérico do usuário no Aura; `$user_id` presente em ~99% dos eventos.
- Pessoas do PostHog **não** têm e-mail confiável. Resolver e-mail → ID em `aura.user` (ClickHouse).
- Eventos anônimos: páginas antes do login (`/login`), ~1% do volume.

## Contexto global (em todo evento próprio do Aura)

| Propriedade | Significado |
|---|---|
| `chain_id`, `chain_ids` | Rede ativa e redes do usuário |
| `store_ids` | Lojas **selecionadas** no seletor no momento (pode chegar a 1.250); não é "a loja do evento" |
| `user_role` | `OPERATOR`, `ADMIN`, `USER` |
| `has_global_access`, `is_internal` | Acesso global; interno (cobre poucas pessoas) |
| `experiment_offers_as_home` | Super-propriedade antiga; a flag `offers-as-home` parou de ser avaliada em 09/09/2026 — não usar como variante atual |

Contexto enriquecido (parcial, desde agosto/2026): `app_surface`, `app_environment`, `user_id`, `user_email`,
`user_name`, `user_profile`, `store_id`, `store_cnpj`, `store_cnpj_root`, `store_name`, `store_state`,
`aura_store_id`. Contém dados pessoais: não expor e-mail/nome sem necessidade.

## Eventos por módulo (prefixo)

| Prefixo | Módulo | Exemplos |
|---|---|---|
| `offer_*`, `synthetic_offer_*` | Ofertas | `offer_viewed`, `offer_clicked`, `offer_filter_applied`, `offer_quote_sent` |
| `cart_*` | Carrinho e envio | ver abaixo |
| `quote_*` | Cotação | `quote_products_searched`, `quote_item_selected`, `quote_bulk_searched` |
| `sale_pivot_*` | Análise de vendas | `sale_pivot_view_applied`, `sale_pivot_view_refused` |
| `assortment_*` | Mix / sortimento | `assortment_filter_applied`, `assortment_exported` |
| `pbm_analysis_*`, `market_analysis_*`, `order_analysis_*` | Análises | |
| `order_*` | Gestão de pedidos (poucos usuários) | `order_created`, `order_create_failed`, `order_status_changed` |
| `campaign_*` | Campanhas (indústria, poucos usuários) | `campaign_created`, `campaign_create_failed` |
| `login_*` | Login | `login_succeeded.login_method` (`token`, `cpf_password`), `login_failed.reason` |

Eventos do PostHog: `$pageview` (`$pathname`, `$referrer`), `$pageleave`, `$dead_click`, `$exception`, `$set`, `$identify`.

## Carrinho e envio

| Evento | Propriedades próprias |
|---|---|
| `cart_item_added` | `source` (`offer`, `quote`, `minimum_helper`, `assortment`), `item_count`, `store_count` |
| `cart_checkout_started` | `total_price`, `item_count`, `bucket_count` |
| `cart_checkout_succeeded` | `total_price`, `item_count`, `bucket_count` |
| `cart_checkout_failed` | `reason` (ex.: `api_error`), `error_message` (ex.: `HTTP 502`, `EAN cannot be null or empty`, `Manufacturer name cannot be null or empty`) |
| `cart_cleared`, `cart_condition_removed`, `cart_minimum_helper_opened` | contagens, `gap_amount`, `condition_name` |

Lacunas: **nenhum evento de carrinho tem EAN, produto, distribuidor ou ID de pedido**; `bucket_count` não é o número
de pedidos. **Não existe evento de falha ao adicionar item no carrinho.**

Validação (08–21/09/2026): `cart_checkout_succeeded` = 976 contra 910 carrinhos com pedido manual no ClickHouse
(`analytics.order_item_internal`, `invoice_type` ≠ `AUTO`), mesmo desenho diário. Cruzar só por usuário + horário.

## Erros

- `cart_checkout_failed` (com `reason` e `error_message`), `order_create_failed` (sem motivo nem mensagem), `campaign_create_failed`, `login_failed`, `sale_pivot_view_refused.code`
  (`COLUMN_NOT_COMBINABLE`, `RETRYABLE`, ...), `market_analysis_report_export_failed`.
- `$exception` (verificado em 23/09/2026): a captura **não está desligada** (`capture_exceptions: true` no Aura UI,
  SDK web 1.376.1). Só registra erro **não tratado** (`Uncaught`). O pico de 26/08 a 09/09/2026 foi
  `ReferenceError: Cannot access 't' before initialization`; depois disso, zero. Propriedades `$exception_types`,
  `$exception_values`.
- Erros que **não** viram evento:
  - erro de renderização capturado pela tela "Algo deu errado" (`GlobalErrorComponent` da rota raiz, que não reporta);
    ex. desde 10/09: `TypeError ... reading 'split'` (integrações, mix) e `... reading 'lastCompleteMonth'`
    (utilitários de análise de vendas);
  - falha ao adicionar item no carrinho: ~12 pontos do Aura UI tratam com `toast`/mensagem ("Falha ao adicionar ao
    carrinho", "Não foi possível adicionar o item") sem `analytics.track`;
  - `order_create_failed` é enviado sem propriedades.
- **Fonte para esses erros:** tabela `console_logs_log_entries` (console das gravações; colunas `log_source_id` =
  `$session_id`, `timestamp`, `level`, `message`). Filtrar `level = 'error'`, ignorar `ResizeObserver` e mensagens do
  próprio SDK. `query-session-recordings-list` dá `console_error_count` por sessão.
- Sinal de perda: console registrou `[PostHog.js] This capture call is ignored due to client rate limiting`.

## Instrumentação nova (produção desde 23/09/2026 08:04, aura-ui #645/#646, versão `3e000e0`)

- `app_version` (SHA curto do build) em todo evento do Aura UI; eventos antigos não têm.
- `cart_item_add_failed`: `source`, `item_count`, `reason` (`timeout`, `network_error`, `api_error`),
  `error_message` (truncada, com e-mail e CPF/CNPJ formatados mascarados), `http_status`.
- `$exception` com `source: 'route_error_boundary'` e `pathname`: erros da tela "Algo deu errado".
- `order_create_failed`: `failed_count`, `total_count`, `reason`, `error_message`, `http_status`.
- `cart_checkout_failed`: ganhou `http_status`.
- Deploy do Aura UI: produção sai da branch `prod` (PR `main → prod`); merge na `main` não publica.

## Sessões e origem

- ~80% das sessões vêm de portais: `app.otimizafarma.com.br` (vários destinos) e `super-app.grupohipersaude.com.br`
  (100% para `/offers`), via `/login?token=…&redirect_uri=…`.
- Home padrão sem `redirect_uri`: `/mix-produto` (Aura UI; conferir código se a pergunta depender disso).
