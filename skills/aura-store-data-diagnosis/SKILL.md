---
name: aura-store-data-diagnosis
description: Investigar divergências de estoque, vendas, custo e outros dados do ERP da loja no Aura/Beta, rastreando coleta, transformação, bases, API e tela para localizar a primeira etapa divergente. Diagnóstico somente leitura; empacotamento usa aura-packaging.
---

# Diagnóstico de dados da loja no Aura

Localizar onde o dado diverge, com evidências por etapa e horários comparáveis. Uma
referência nova no Mix não comprova estoque ou vendas novos. A falha observada num
incidente não deve virar causa presumida no próximo.

## Delimitar o caso

- Identificar loja/CNPJ, produto (EAN e código ERP), métrica, valor esperado,
  valor observado, ambiente e horário da evidência. Resolver o cadastro atual da
  loja e seu grupo; não usar o CNPJ padrão dos testes para um cliente identificado.
- Preservar rota, loja selecionada, filtros, período e agrupamento da tela. Para
  vendas, distinguir quantidade, valor, devoluções e janela; para estoque, loja,
  grupo, embalagem e saldo físico versus trânsito. Custo exige a mesma base unitária.
- Relato/print do ERP é evidência naquele contexto e horário, não uma leitura ao
  vivo do banco. Ler os anexos necessários; mensagens usam `wacli`. Browser QA
  segue `aura-beta-browser` e `visual-inspection`, quando realmente necessário.

## Rastrear por etapa

1. No código atual, identificar endpoint e campo exibido. Seguir mapper, service e
   repository até a tabela e consulta reais. Distinguir checkout, processo local e
   versão publicada; uma API local não comprova a revisão que serviu o print.
2. Usar `aura-clickhouse` para descobrir esquemas e consultar fonte e derivados no
   recorte loja/produto/período. Confirmar grão, aliases de EAN, duplicatas, unidade,
   regras de elegibilidade e escopo autorizado antes de somar.
3. Comparar fonte integrada, mart e resposta da API. Estoque zero, dado ausente,
   snapshot parcial e erro de acesso são estados diferentes. Não usar
   `max(data)` para definir hoje nem data de último movimento como frescor da coleta.
4. Havendo divergência antes da API, rastrear a aquisição bruta e as transformações.
   Ler [references/upstream.md](references/upstream.md) para descoberta de arquivos,
   inspeção de Parquet, BigQuery, agendamentos e logs. Evitar listar buckets inteiros.
5. Comparar cargas anteriores/posteriores ao incidente. Registrar horário do
   movimento, extração, ingestão, transformação e consulta separadamente. Converter
   timestamps com timezone conhecido para São Paulo; não inventar fuso para campos
   de ERP sem timezone.
6. Correlacionar modelo e execução nos logs com `aura-cloud-logs`; conferir estado
   terminal do job. Um `PASS` de outro modelo/execução não valida a etapa investigada.
   Se houver falha, registrar erro exato e efeito nos dependentes. Mesmo com o Mix
   reconstruído, uma fonte preservada após falha pode continuar antiga.

Avançar pelo caminho que a evidência exigir; não consultar todos os serviços por
rotina. Parar a busca causal quando o ponto de divergência e seu mecanismo estiverem
comprovados, ou quando a próxima prova depender de acesso indisponível. Informar a
lacuna e a leitura específica que falta; não converter ausência de permissão em
ausência de dado.

## Interpretar

| Evidência | Diagnóstico sustentado |
| --- | --- |
| ERP mais novo que a última coleta; nenhuma carga posterior | Defasagem/cadência possível; extração incorreta ainda não comprovada |
| Aquisição diverge de ERP comparável | Investigar extração, filtro, identidade, unidade ou réplica |
| Aquisição correta; fonte integrada antiga/divergente | Investigar ingestão/transformação, seleção de carga e proteção de snapshot |
| Fonte correta; mart divergente | Investigar join, agregação, aliases, deduplicação e atualização do mart |
| Mart correto; API divergente | Investigar SQL, mapper, cache, autorização e versão em execução |
| API correta; tela divergente no mesmo contexto | Investigar chave/cache, seleção de loja, conversão e apresentação |

Uma diferença localiza a etapa; a causa exige evidência adicional. Um erro de memória
comprova interrupção por limite de memória, não prova qual join, concorrência ou
configuração consumiu esse recurso. Não recomendar aumento de memória sem essa análise.

## Entrega e limites

Entregar conclusão primeiro, tabela curta dos valores por camada/loja, linha do tempo,
modelo/endpoint/execução envolvidos, impacto no usuário e próximo trabalho necessário.
Separar fatos, hipóteses e lacunas. Indicar se o dado ainda diverge na última leitura.

O diagnóstico não autoriza reprocessamento, trigger de sync/dbt, rewind de cursor,
reinício, alteração de dados/configuração/IAM, deploy ou envio de mensagens. Leituras
necessárias podem prosseguir; correção operacional ou implementação depende do escopo
autorizado pelo usuário. Não expor segredos nem guardar amostras completas de clientes
na skill ou no Git; preferir filtro em memória e relatar apenas os campos necessários.
