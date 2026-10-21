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
- Desde 07/10/2026 00:19 BRT (aura-ui `5b026ab`, story 11-2-2) a pessoa recebe `email`, `name`, `access_level`
  (`GLOBAL|CHAIN|ECONOMIC_GROUP|STORE`), `chain_name`/`chain_slug`, `economic_group_*` e traits de loja
  (`active_store_count`, `erp_types`, `store_states`; não para acesso global); o grupo `chain` tem `name`/`slug`.
  Só para quem logou depois do deploy: para histórico, resolver e-mail → ID em `aura.user` (ClickHouse).
- Sessão de browser automatizado (agent-browser headless) **não gera eventos**: o filtro de bots do posthog-js
  descarta o user-agent headless. Verificar instrumentação com tráfego real ou browser com UA normal.
- Eventos anônimos: páginas antes do login (`/login`), ~1% do volume.

## Contexto global (em todo evento próprio do Aura)

| Propriedade | Significado |
|---|---|
| `chain_id`, `chain_ids` | Rede ativa e redes do usuário |
| `store_ids` | Lojas **selecionadas** no seletor no momento (pode chegar a 1.250); não é "a loja do evento" |
| `user_role` | `OPERATOR`, `ADMIN`, `USER` |
| `has_global_access`, `is_internal` | Acesso global; interno (cobre poucas pessoas) |
| `experiment_offers_as_home` | Super-propriedade antiga; a flag `offers-as-home` parou de ser avaliada em 09/09/2026 — não usar como variante atual |

Contexto legado (06/10/2026): `app_surface`, `app_environment`, `user_id`, `user_email`,
`user_name`, `user_profile`, `store_id`, `store_cnpj`, `store_cnpj_root`, `store_name`, `store_state`,
`aura_store_id`. **Não é instrumentação do aura-ui**: são super-propriedades do `aura-web-app`
(`posthogClient.ts`, descontinuado) que ficaram no `localStorage` de quem nunca fez logout; o aura-ui não as
remove. Em 30 dias, só 10 pessoas. Contém dados pessoais: não expor e-mail/nome sem necessidade.
Person property `email`/`name`: 68 de 486 pessoas, gravadas pelo `identify` do `aura-web-app` (último em maio/2026);
o aura-ui identifica só com `userId` e traits sem PII.

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
| `product_searched`, `quote_search_succeeded`, `purchase_context_resolved` | Comprar produto (`/quote`), verificado em 17/10/2026 | `product_searched` (`search_term`, `result_count`) é o **catálogo**: só sai na busca por texto/EAN; escolher do autocomplete ou recentes não emite. `quote_search_succeeded` (`ean_count`, `quoted_ean_count`, `unquoted_ean_count`) é a **cotação**: "não achou" com `result_count ≥ 1` e `quoted_ean_count = 0` = produto existe, sem preço ativo para a loja; conferir `quote.quote_current` (tombstone) e `quote.quote_run_task.outcome_code` |
| `team_registry_*` | Cadastro da equipe (desde 25/09/2026) | `team_registry_modal_shown.pending_count`, `team_registry_opened.source` (`modal`, `banner`, `menu`), `team_registry_field_saved` (`field`, `status`, `self`). Verificado em 17/10/2026: `status` ignora o WhatsApp e nenhum evento leva o resultado; "preencheu" confirmar em `aura.user_team_profile` (MySQL). Usuário 803 "André Monteiro (teste)" é interno sem e-mail interno |

Eventos do PostHog: `$pageview` (`$pathname`, `$referrer`), `$pageleave`, `$dead_click`, `$exception`, `$set`, `$identify`.

## Carrinho e envio

| Evento | Propriedades próprias |
|---|---|
| `cart_item_added` | `source` (`offer`, `quote`, `minimum_helper`, `assortment`), `item_count`, `store_count` |
| `cart_checkout_started` | `total_price`, `item_count`, `bucket_count` |
| `cart_checkout_succeeded` | `total_price`, `item_count`, `bucket_count` |
| `cart_checkout_failed` | `reason` (ex.: `api_error`), `error_message` (ex.: `HTTP 502`, `EAN cannot be null or empty`, `Manufacturer name cannot be null or empty`) |
| `cart_cleared`, `cart_condition_removed`, `cart_minimum_helper_opened` | contagens, `gap_amount`, `condition_name`; `cart_minimum_helper_opened.level` = `condition` \| `distribution_center` (28/09/2026: 90% `condition`, quase tudo em `otimiza`; condições removidas são sobretudo campanhas "OL <laboratório>") |

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

## Lentidão: INP com atribuição e carrinho em todo evento (produção desde 21/10/2026 08:58, aura-ui #846/#847, versão `efdb7f0`)

- `$web_vitals` com atribuição (`capture_performance.web_vitals_attribution`). **Não há propriedade própria**: a
  atribuição fica dentro do objeto da métrica, `$web_vitals_<M>_event.attribution`. Para o INP:
  `interactionTarget` (seletor do elemento), `interactionType`, `interactionTime`, `inputDelay`, `processingDuration`,
  `presentationDelay`, `longestScript`, `totalScriptDuration`, `longAnimationFrameEntries`, `loadState`. Ler com
  `JSONExtractRaw(JSONExtractRaw(properties, '$web_vitals_INP_event'), 'attribution')`. Versões anteriores não têm
  `attribution`.
- `cart_item_count` e `cart_bucket_count` (buckets = distribuidores/condições do carrinho, mesma contagem do
  `cart_checkout_started`) em **todo** evento do Aura UI, inclusive `$web_vitals` e `$exception`. Ausentes antes de
  o carrinho carregar na página (ausente ≠ 0).
- Verificação 21/10/2026 ~09:10: 6 `$web_vitals` da `efdb7f0`, todos com as contagens; os de INP com `attribution`.
  Não existe evento próprio de interação lenta ou tela travada (monitor Event Timing/LoAF avaliado e retirado).

## Instrumentação nova (produção desde 23/09/2026 08:04, aura-ui #645/#646, versão `3e000e0`)

- `app_version` (SHA curto do build) em todo evento do Aura UI; eventos antigos não têm.
- `cart_item_add_failed`: `source`, `item_count`, `reason` (`timeout`, `network_error`, `api_error`),
  `error_message` (truncada, com e-mail e CPF/CNPJ formatados mascarados), `http_status`.
- `$exception` com `source: 'route_error_boundary'` e `pathname`: erros da tela "Algo deu errado".
- `order_create_failed`: `failed_count`, `total_count`, `reason`, `error_message`, `http_status`.
- `cart_checkout_failed`: ganhou `http_status`.
- Verificação 23/09/2026 15:30: `app_version` em ~90% dos eventos do dia (inclui `$pageview`); `cart_item_add_failed`
  e `order_create_failed` chegam com todas as propriedades; nenhum `$exception` nem erro de console desde o deploy,
  logo o caminho `route_error_boundary` ainda não foi exercitado em produção. Contexto enriquecido (`app_surface`,
  `store_id`...) **não** vem do Aura UI de produção (sem código em `aura-ui`); cobertura segue ~2,5%.
- Deploy do Aura UI: produção sai da branch `prod` (PR `main → prod`); merge na `main` não publica.
- Verificação 08/10/2026: `assortment_load_failed` novo (1º visto 08/10, Mix `/product-assortment`), com `reason`,
  `http_status`, `mode` (ex.: `PER_STORE`). `cart_item_add_failed` com `network_error` vem sem `http_status`
  nem `error_message`. `cart_checkout_failed` 500 emite `$exception` pareado no mesmo ms. A causa do 500
  não chega ao PostHog (`error_message` = `HTTP 500`): cruzar com Cloud Run `aura` (`aitrus-aura-prod`, severity ERROR).

## Sessões e origem

- ~80% das sessões vêm de portais: `app.otimizafarma.com.br` (vários destinos) e `super-app.grupohipersaude.com.br`
  (100% para `/offers`), via `/login?token=…&redirect_uri=…`.
- Home padrão sem `redirect_uri`: `/mix-produto` (Aura UI; conferir código se a pergunta depender disso).

## Campanhas (`utm_*`) — produção desde 17/10/2026; modelo revisto em 18/10/2026 (aura-ui #822/#824, aura #1392)

- **Visita × 7 dias:** os `utm_*` padrão valem só para a visita da campanha (PostHog na carga e
  `register_for_session` em navegação interna). A janela de 7 dias para carrinho e pedido é
  `attribution_utm_*` + `attribution_registered_at`. Entre 17/10 e 18/10/2026 os `utm_*` padrão iam por
  7 dias com `utm_registered_at`, e as sessões seguintes dessa época saem como sessões de campanha.
- **Sessão:** `$entry_utm_*` e `$channel_type` vêm do primeiro `$pageview` da sessão
  (`raw_sessions/sessions_v3.py`). A sessão vale para todas as abas, com 30 min de inatividade. O 302 do
  link curto vai para `/l/{código}?utm_…` desde 18/10/2026; antes, todo clique saía "Direct".
- **Canais próprios** (projeto 331102, `modifiers.customChannelTypeRules`, desde 18/10/2026, valem
  também para o histórico): `CRM e-mail`, `CRM SMS` e `CRM` (`utm_source=crm`).
- **Perfil:** `first_utm_*` (`$set_once`, primeira campanha), `utm_*` nativo (última) e `$initial_utm_*`
  nativo (primeiro acesso, com ou sem campanha). `last_utm_*` só existiu em 17/10/2026.
- Workers de QA (HeadlessChrome) não geram eventos (filtro de robôs): a conferência exige clique real.
