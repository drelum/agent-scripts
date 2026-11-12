---
name: google-ads
description: "Google Ads da aitrus (conta 4835940158) por linha de comando, só leitura, via GAQL: campanhas, grupos, palavras-chave com índice de qualidade, termos de pesquisa, anúncios, canais da Display, conversões, parcela de impressões. Usar para diagnosticar a conta, medir custo e conversão por período, achar termos para negativar ou conferir a configuração. Alterações na conta só pela interface, com OK do André."
---

# Google Ads (aitrus)

Script: `~/Projects/agent-scripts/bin/gads-aitrus` (bash + curl + jq). Fala direto com a API do Google Ads (`googleAds:searchStream`, só leitura). É muito mais rápido e completo que ler a interface no Chrome: use a interface só para o que a API não mostra (abaixo).

| Comando | O que traz |
|---|---|
| `gads-aitrus campanhas [início] [fim]` | TSV por campanha: tipo, status, orçamento/dia, estratégia, impressões, cliques, CTR, CPC, custo, conversões, custo/conversão |
| `gads-aitrus grupos [início] [fim]` | o mesmo por grupo de anúncios |
| `gads-aitrus palavras [início] [fim]` | por palavra-chave, com correspondência e índice de qualidade |
| `gads-aitrus termos [início] [fim]` | termos de pesquisa reais (somados no período), do mais caro ao mais barato |
| `gads-aitrus conversoes` | ações de conversão: status, primária, contagem, janelas, atribuição |
| `gads-aitrus query '<GAQL>'` | qualquer consulta; devolve a lista de linhas em JSON |

Sem datas, o padrão é os últimos 30 dias até ontem. Datas `AAAA-MM-DD` no fuso da conta (São Paulo). Custos em R$ (a API dá micros: dividir por 1.000.000).

## Receitas GAQL

```bash
G=~/Projects/agent-scripts/bin/gads-aitrus
P="segments.date BETWEEN '2026-11-05' AND '2026-11-12'"
# configuração das campanhas (redes, lance, geo, URL final)
$G query "SELECT campaign.name, campaign.status, campaign.primary_status_reasons, campaign.bidding_strategy_type, campaign.network_settings.target_content_network, campaign.geo_target_type_setting.positive_geo_target_type, campaign.final_url_suffix, campaign.start_date_time, campaign_budget.amount_micros FROM campaign"
# parcela de impressões e perdas (só Pesquisa)
$G query "SELECT campaign.name, metrics.search_impression_share, metrics.search_budget_lost_impression_share, metrics.search_rank_lost_impression_share FROM campaign WHERE $P"
# por dia
$G query "SELECT campaign.name, segments.date, metrics.clicks, metrics.cost_micros, metrics.conversions FROM campaign WHERE $P"
# anúncios: títulos, descrições, força, URL final
$G query "SELECT ad_group.name, ad_group_ad.status, ad_group_ad.ad_strength, ad_group_ad.ad.final_urls, ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.ad.responsive_search_ad.descriptions FROM ad_group_ad"
# palavras-chave: estado, lance, estimativas de 1ª página
$G query "SELECT ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, ad_group_criterion.negative, ad_group_criterion.system_serving_status, ad_group_criterion.effective_cpc_bid_micros, ad_group_criterion.position_estimates.first_page_cpc_micros FROM ad_group_criterion WHERE ad_group_criterion.type = 'KEYWORD'"
# Display: onde apareceu (apps, sites, YouTube)
$G query "SELECT campaign.name, group_placement_view.placement_type, group_placement_view.display_name, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions FROM group_placement_view WHERE $P"
# segmentos: aparelho, hora, região, conversão por ação
$G query "SELECT campaign.name, segments.device, segments.hour, metrics.clicks, metrics.cost_micros FROM campaign WHERE $P"
$G query "SELECT campaign.name, segments.conversion_action_name, metrics.conversions FROM campaign WHERE $P AND metrics.all_conversions > 0"
# recursos (sitelinks etc.), negativas da campanha, listas compartilhadas, públicos personalizados
$G query "SELECT campaign.name, asset.type, asset.sitelink_asset.link_text, asset.final_urls FROM campaign_asset"
$G query "SELECT campaign.name, campaign_criterion.type, campaign_criterion.negative, campaign_criterion.keyword.text, campaign_criterion.location.geo_target_constant FROM campaign_criterion"
$G query "SELECT shared_set.name, shared_set.type, shared_set.member_count FROM shared_set"
$G query "SELECT custom_audience.name, custom_audience.members FROM custom_audience"
```

Campos e recursos: https://developers.google.com/google-ads/api/fields/v26/overview (troque a versão se `GADS_API_VERSION` mudar).

## Armadilhas

- **Métrica exige data finita**: `FROM ... WHERE segments.date BETWEEN 'a' AND 'b'` (ou `DURING LAST_30_DAYS`); sem isso, erro `EXPECTED_FILTERS_ON_DATE_RANGE`.
- **Campo inexistente** volta como `UNRECOGNIZED_FIELD` (ex.: `campaign.start_date` virou `campaign.start_date_time`). O script mostra a mensagem da API.
- **Termos de pesquisa** cobrem só parte do custo: o Google esconde termos raros. Compare a soma com o custo da campanha antes de concluir.
- **Conversões** do Ads contam a ação primária (`lead_created`, 1ª etapa do formulário = cadastro parcial). Qualidade (cadastro completo, cidade, sistema) vem do PostHog (projeto `aura`) e do D1 do site, não daqui.
- **Somas por período**: consultas com `segments.date` voltam uma linha por dia; agregue antes de comparar.
- Fusos: a conta está em São Paulo; o PostHog guarda em UTC.

## O que fica fora da API (Chrome, skill `windows-chrome-browser`, perfil `aitrus`)

Insights de leilão (concorrentes no leilão), recomendações e pontuação de otimização em texto, diagnóstico de anúncio reprovado com detalhe, e qualquer alteração.

## Regras

- **Só leitura.** O script nunca chama `mutate`. Qualquer mudança (orçamento, lance, palavra, negativa, anúncio, conversão, aplicar ou dispensar recomendação) é feita pela interface e só com OK explícito do André.
- Não copie dados de lead (e-mail, telefone, nome) para fora do relatório interno.
- Texto de anúncio sugerido segue a marca: "farmácia", nunca "loja"; sem "tempo real", sem promessa de economia ou percentual, sem preço; sem citar distribuidoras, laboratórios, concorrentes nem ERPs; "aitrus" minúsculo.

## Credencial

Usa o login principal do gcloud do André, que impersona `google-ads-agent@aitrus-shared-prod.iam.gserviceaccount.com` com escopo `adwords` (IAM Credentials `generateAccessToken`). Não há chave local; o token passa por `curl -K -` e nunca vai à linha de comando. Se vencer (código 2, `invalid_rapt`/`invalid_grant`), pedir ao André:

```
! gcloud auth login --update-adc
```

Variáveis opcionais: `GADS_CUSTOMER` (padrão 4835940158), `GADS_API_VERSION` (padrão v26).
