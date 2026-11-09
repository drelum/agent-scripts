---
name: dataforseo-seo
description: "Pesquisa de SEO com o DataForSEO (MCP dfs-mcp): volume de busca, autocompletar, posição ao vivo no Google, palavras e páginas de um domínio, links e concorrência. Usar para escolher pautas, medir posições, auditar concorrentes ou comparar a aitrus com eles. Inclui o contexto do site da aitrus e os concorrentes conhecidos."
---

# DataForSEO para SEO

Ferramenta: `mcp__dfs-mcp__api_request` (carregar com ToolSearch `select:mcp__dfs-mcp__api_request`). Documentação: `mcp__dfs-mcp__docs_search` com o caminho do endpoint.

## Regras de chamada

- O corpo vai no parâmetro **`data`** (lista de tarefas), nunca em `body` ("POST Data Is Empty").
- Brasil: `"location_code": 2076, "language_code": "pt"`.
- A resposta resumida (modo IA, padrão) pode cortar listas em 10 itens. Se faltar item, repita com `noAiMode: true`.
- Erros temporários (`40101 Internal SE Server Error`): repetir uma vez.
- Salvar as respostas brutas em arquivo (pasta de rascunho da sessão) quando forem usadas num relatório.

## Endpoints úteis

| Pergunta | Endpoint (POST) | Observação |
|---|---|---|
| Quanto se busca? | `/v3/keywords_data/google_ads/search_volume/live` | até 1.000 palavras por tarefa; média de 12 meses e série mensal |
| Que ideias existem? | `/v3/keywords_data/google_ads/keywords_for_keywords/live` | traz muito ruído de consumidor; filtrar |
| Como a pessoa digita? | `/v3/serp/google/autocomplete/live/advanced` | uma tarefa por chamada; melhor sinal de cauda longa sem volume |
| Quem aparece hoje? | `/v3/serp/google/organic/live/regular` (só orgânicos) ou `/live/advanced` (também "As pessoas também perguntam", resumo de IA, mapa) | **uma tarefa por chamada**; `"device": "desktop"`, `"depth": 30` |
| Em que palavras um domínio aparece? | `/v3/dataforseo_labs/google/ranked_keywords/live` | inclui subdomínios; ordenar por `keyword_data.keyword_info.search_volume,desc` |
| Força e páginas de um domínio | `/v3/dataforseo_labs/google/domain_rank_overview/live`, `/relevant_pages/live`, `/competitors_domain/live` | |
| Ideias por semente (Labs) | `/v3/dataforseo_labs/google/keyword_suggestions/live`, `/related_keywords/live` | cobertura fraca em nichos B2B do Brasil |
| Links | `/v3/backlinks/summary/live`, `/v3/backlinks/referring_domains/live` | separar spam: domínios com nota de spam abaixo de 30 são os "de verdade" |

## Armadilhas conhecidas

- **Links disfarçados na SERP:** a `url` orgânica costuma vir como `google.com/goto?...` e o `domain` como `google.com`. O site real está no **`breadcrumb`**. Por isso o filtro `target` da SERP não funciona; identificar o domínio pelo `breadcrumb`.
- **Atraso do Labs:** a base é mensal (setembro/outubro na última leitura). Páginas novas não aparecem. Para posição atual, usar SERP ao vivo; para buscas reais do próprio site, o Search Console.
- **Volume nulo do Google Ads** quer dizer abaixo do limiar (menos de 10 por mês, ou agrupado em variante), não "ninguém busca". Confirmar com autocompletar e com quem aparece na SERP.
- **Posição oscila** em páginas recém-indexadas e entre coletas (a mesma busca pode mudar 10 posições em horas). Uma coleta não mede; repetir e preferir a posição média do Search Console.
- **Busca logada ≠ sem login:** o Chrome do usuário personaliza. O DataForSEO dá a visão sem login.
- **SERP contaminada:** algumas buscas genéricas vêm cheias de spam (ex.: "cotação online"). Anotar e repetir outro dia.
- **Intenção mista:** muitas buscas de farmácia misturam consumidor (preço de remédio), estudante e hematologia (PBM). Ler a primeira página antes de concluir que o volume é do comprador.
- **Links de spam:** o nicho tem fazendas de domínios `.shop` e diretórios automáticos. Contar só os de verdade.

## Contexto da aitrus

- Site: `~/Projects/website` (aitrus.com.br). Páginas de conteúdo: `/sistema-para-farmacia`, `/curva-abc-farmacia`, `/tabela-cmed`, `/medicamentos-intercambiaveis`, `/ruptura-de-estoque-farmacia`, `/pbm-farmacia`, `/cotacao-para-farmacia`, além da home.
- Pesquisas anteriores e decisões: `docs/seo-pautas.md` (pautas, posições, concorrentes) e `docs/guias-de-conteudo.md` (como cada guia foi feito). Ler antes de pesquisar de novo; registrar resultados novos lá, com data.
- Público: dono, gerente e comprador de farmácia, rede e associativismo. Busca de consumidor, estudante e carreira fica de fora.
- Concorrentes conhecidos (plataformas de cotação e compras para farmácias):
  - Cienty (`cienty.com.br`, ex-Covalenty; `covalenty.com.br` redireciona);
  - SimPed (`simped.com.br`, `blog.simped.com.br`) e SmartPed (`smartped.net.br`, `smartped.com.br`), do mesmo grupo;
  - Cotefácil (`cotefacil.com`), a marca mais buscada do setor;
  - também vistos: Siscota, Central de Cotações, Club da Cotação, Dicto, Cota Todos, Cota Medicamentos, Mercado Farma, Tudo Farma.
- **No site da aitrus não se cita concorrente, distribuidora, laboratório, rede cliente nem ERP** (salvo exceções registradas em `docs/guias-de-conteudo.md`). A pesquisa pode citá-los; o texto publicado, não.

## Entrega

Português do Brasil, datas no formato brasileiro e horário de São Paulo. Tabelas curtas: termo, volume, posição, URL. Marcar o que é inferência. Registrar chamadas que falharam com o erro exato.
