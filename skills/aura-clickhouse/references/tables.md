# Mapa inicial do ClickHouse Aura

Ler ao escolher fonte, grão ou identidade. O warehouse muda: confirmar colunas com `describe` e armazenamento com `show-create`.

## Bancos

| Banco | Papel |
|---|---|
| `analytics` | Dimensões, fatos atuais e marts consumidos pelo Aura e painel |
| `performance` | Agregações de venda, estoque, rede, loja e brick |
| `market` | Fontes externas de mercado e catálogo |
| `system` | Metadados do ClickHouse: colunas, tabelas, partes e consultas |

## Núcleo

| Tabela | Papel e grão inicial | Cuidados |
|---|---|---|
| `analytics.store` | Uma loja por `store_id`; CNPJ, rede, grupo, ERP, localização e status | Usar `store_id` para joins internos; CNPJ para identidade externa |
| `analytics.catalog` | Catálogo canônico por EAN | `ean_group_main` e `ean_secondaries` agrupam identidades; fração não garante unidade comercial |
| `analytics.sale` | Linhas de venda por loja, produto, documento e data | `ean_original` vem da loja; `ean` pode estar normalizado; horário armazenado em UTC |
| `analytics.quote` | Snapshot atual de ofertas por loja, EAN, provedor, CD e condição | Preço efetivo segue o contrato do backend; contém `distribution_center_product_code`, mas não fator de embalagem |
| `analytics.quote_history` | Histórico diário de cotações | Muito grande; TTL de 60 dias; `ORDER BY (quote_date, chain_id, store_id, ean, id)`; filtrar nessa ordem |
| `analytics.order_item` | Execução externa do pedido por item e distribuidor | Quantidades solicitada, atendida e faturada; preço e status do fornecedor |
| `analytics.order_item_internal` | Estado interno do pedido Aura por item | Quantidades solicitada, aceita e faturada; carrinho, status e responsável |
| `analytics.product_assortment` | Mart de Mix por loja/produto | Confirmar o grão da consulta e os EANs relacionados antes de agregar |

## Derivadas úteis

| Tabela | Uso inicial |
|---|---|
| `analytics.store_ean_best_quote_daily` | Melhor e média diária de cotação por loja/EAN |
| `analytics.store_sale_analysis` | Análise agregada de vendas por loja |
| `analytics.chain_sale_analysis` | Análise agregada de vendas por rede |
| `analytics.market_sale` | Métricas agregadas de mercado |
| `analytics.store_invoice_sale` | Relação entre venda e documento fiscal; confirmar o grão |
| `analytics.product_pricing` | Métricas derivadas de precificação |
| `analytics.product_price_benefit` | Indicadores derivados de benefício de preço |
| `analytics.product_price_regulation` | Referências regulatórias de preço |
| `analytics.product_tax` | Tributação e preço de fábrica |
| `analytics.imendes_product_base` | Referência de produto iMendes |

## Performance e mercado

- `performance.sale_agg`, `sale_performance`, `store_sale_performance`: agregações para análises amplas.
- `performance.store_sale_annualy`: venda anual; preserva também `ean_original`.
- `performance.sale_stock_invoice_agg`: consolidação de venda, estoque e nota.
- `performance.chain_sale_indicator`, `chain_sale_weekly`: indicadores por rede.
- `performance.*brick*`: agregações geográficas/IQVIA; confirmar janela e região.
- `market.iqvia_product_catalog_source`: fonte de catálogo IQVIA.

## Descoberta

Quando a tabela não estiver neste mapa:

```bash
"$ch" tables analytics
"$ch" columns termo
"$ch" describe banco.tabela
"$ch" show-create banco.tabela
```

Não usar tabelas `*_old` ou `*__dbt_backup` sem uma justificativa explícita.
