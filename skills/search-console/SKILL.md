---
name: search-console
description: "Search Console da aitrus (sc-domain:aitrus.com.br) por linha de comando, só leitura: desempenho por consulta, página, dia, aparelho e país; inspeção de URL e de todo o sitemap; sitemaps. Usar para medir SEO, conferir indexação e posição média, comparar períodos ou separar marca de busca sem marca. Pedir indexação continua no Chrome."
---

# Search Console (aitrus)

Script: `~/Projects/agent-scripts/bin/gsc-aitrus` (bash + curl + jq). Saída em JSON (ou TSV no `inspect-sitemap`); filtrar com `jq`.

| Comando | O que traz |
|---|---|
| `gsc-aitrus query <início> <fim> [dimensões] [limite] [página-contém]` | desempenho; dimensões separadas por vírgula: `date`, `query`, `page`, `device`, `country`, `searchAppearance` (padrão `query,page`; limite padrão 1000, máximo 25000) |
| `GSC_TIPO=discover gsc-aitrus query …` | outro tipo de busca: `web` (padrão), `image`, `video`, `news`, `discover`, `googleNews` |
| `gsc-aitrus inspect <url>` | indexação, canônico escolhido, último rastreio |
| `gsc-aitrus inspect-sitemap` | todas as URLs do sitemap publicado: situação e último rastreio |
| `gsc-aitrus sitemaps` / `sites` | sitemaps enviados e lidos; propriedades e permissão |

## Receitas

```bash
G=~/Projects/agent-scripts/bin/gsc-aitrus
# por dia
$G query 2026-11-06 2026-11-12 date | jq -r '.rows[] | [.keys[0], .clicks, .impressions, (.position*10|round/10)] | @tsv'
# por página num período
$G query 2026-11-10 2026-11-10 page | jq -r '.rows[] | [.keys[0], .clicks, .impressions, (.position*10|round/10)] | @tsv'
# consultas de uma página
$G query 2026-11-06 2026-11-12 query 1000 tabela-cmed | jq -r '.rows[] | [.keys[0], .impressions, (.position*10|round/10)] | @tsv'
# sem a marca
$G query 2026-11-06 2026-11-12 query | jq '[.rows[] | select(.keys[0] | test("a[iy]t?r[uo]s|atirus|aitros"; "i") | not)] | {impressoes: (map(.impressions)|add), cliques: (map(.clicks)|add)}'
# computador × celular
$G query 2026-11-06 2026-11-12 device
```

Para comparar períodos, rode duas consultas e junte por `keys[0]` com `jq`.

## Cuidados de leitura

- **Datas** do Search Console seguem o fuso do Pacífico. O script usa `dataState: all`: os 2–3 últimos dias são preliminares e mudam. O dia corrente vem quase vazio.
- **Posição média** é ponderada por impressão e mistura aparelhos, países e personalização; compare por consulta e aparelho. Foto ao vivo sem login é com o DataForSEO (skill `dataforseo-seo`).
- **Consultas anônimas** não aparecem: a soma das consultas fica abaixo do total do dia.
- **Cliques fora da marca**: separar "aitrus" e grafias erradas antes de concluir.
- Visitas e cadastros vêm do PostHog (projeto `aura`), não daqui.

## O que fica fora da API (usar o Chrome, skill `windows-chrome-browser`, perfil `aitrus`)

- **Solicitar indexação**: na página inicial da propriedade, campo "Inspect any URL" → "Request indexing" (a URL `/search-console/inspect?...` dá 404).
- Relatório de indexação de páginas (motivos), Core Web Vitals, links, remoções, ações manuais, Insights e o relatório de recursos de IA.

## Credencial

Login separado do gcloud principal (`CLOUDSDK_CONFIG=$HOME/.config/gcloud-search-console`), escopo `webmasters.readonly`, projeto de cota `aitrus-aura-prod` (API `searchconsole.googleapis.com` ativada). Vence com a sessão do Google Workspace; o script avisa (código 2). Pedir ao André:

```
! CLOUDSDK_CONFIG=$HOME/.config/gcloud-search-console gcloud auth application-default login --scopes=openid,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/webmasters.readonly
```

Depois: `CLOUDSDK_CONFIG=$HOME/.config/gcloud-search-console gcloud auth application-default set-quota-project aitrus-aura-prod`. O token nunca vai na linha de comando (o script passa por `curl -K -`); não imprimir o token.

## Registro

Medições do site vão para `~/Projects/website/docs/seo-pautas.md` ("Medição de <data>"), com período, números por página e consulta e a leitura.
