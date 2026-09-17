# Consultas e diagnóstico

Ler ao consultar o Cloud Logging ou resolver erros de acesso/filtro. Exemplos em Bash; substituir a janela e os filtros pelo incidente solicitado. Os destinos abaixo são referências históricas a confirmar.

## Destino e acesso

```bash
gcloud auth list --filter=status:ACTIVE --format='value(account)'
gcloud config get-value project
cloud_project=aitrus-aura-prod
cloud_service=aura-beta
gcloud run services list --project="$cloud_project" \
  --format='table(metadata.name,region,status.url)'
```

Usar a região retornada pela listagem. Para o Aura Beta, a referência observada é `us-central1`:

```bash
cloud_region=us-central1
gcloud run services describe "$cloud_service" \
  --project="$cloud_project" --region="$cloud_region" \
  --format='json(status.latestReadyRevisionName,status.traffic,status.conditions)'
```

A listagem valida acesso ao Cloud Run; confirmar separadamente acesso ao Logging pela consulta abaixo. Não pedir todas as variáveis de ambiente do serviço para descobrir seu destino.

## Requisições e mensagens

Este exemplo cobre 17/09/2026 das 08h às 09h de São Paulo, em UTC. Ajustar ambos os limites; não reutilizar a data literalmente para um incidente novo.

```bash
cloud_start='2026-09-17T11:00:00Z'
cloud_end='2026-09-17T12:00:00Z'
cloud_filter="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$cloud_service\" AND timestamp>=\"$cloud_start\" AND timestamp<\"$cloud_end\""
gcloud logging read "$cloud_filter AND logName=\"projects/$cloud_project/logs/run.googleapis.com%2Frequests\" AND httpRequest.status>=400" \
  --project="$cloud_project" --limit=30 --order=desc \
  --format='json(timestamp,severity,resource.labels.revision_name,httpRequest.status,httpRequest.latency,trace)'
```

Acrescentar `httpRequest.requestUrl:"/caminho-do-endpoint"` quando o endpoint for conhecido. Inspecionar URL completa somente quando necessário, omitindo credenciais e parâmetros sensíveis do relato. Para uma falha específica, preferir status exato, por exemplo `httpRequest.status=413`.

Para mensagens da aplicação no mesmo intervalo:

```bash
gcloud logging read "$cloud_filter AND NOT logName=\"projects/$cloud_project/logs/run.googleapis.com%2Frequests\"" \
  --project="$cloud_project" --limit=30 --order=desc \
  --format='json(timestamp,severity,logName,resource.labels.revision_name,textPayload,jsonPayload.message,trace)'
```

A segunda consulta pode incluir mensagens de sistema. Observar `logName` antes de restringir a stdout, stderr ou logs próprios como `java.log`. Se há registros mas o campo de mensagem está vazio, inspecionar a estrutura de um registro delimitado: a aplicação pode usar outro campo em `jsonPayload`.

Quando houver trace, copiar o valor completo retornado e acrescentar `trace="projects/PROJETO/traces/IDENTIFICADOR"` ao filtro. Se a correlação depender de contexto anterior à falha, remover a restrição de severidade/status e ampliar a janela de forma controlada. Nem todo log de aplicação possui trace.

Restringir `resource.labels.revision_name` à revisão que atendeu o incidente ou à nova revisão em uma validação pós-deploy. Não filtrar automaticamente pela última revisão em incidentes históricos.

## Falhas e limites

| Sinal | Próxima ação |
| --- | --- |
| `Cannot find service` | Confirmar projeto e listar serviços/regiões antes de repetir `describe`. Não inferir indisponibilidade da aplicação. |
| `Reauthentication failed` / `cannot prompt during non-interactive execution` | Orientar `gcloud auth login` no terminal interativo do usuário e repetir a leitura após a renovação. Conta ativa listada não basta. |
| `PERMISSION_DENIED` | Identificar conta, projeto e API/operação negada; relatar o acesso faltante. Não alterar IAM ou trocar de identidade automaticamente. |
| Comando falha antes do JSON | Ler stderr; não interpretar como lista vazia. Em scripts, verificar o código de saída antes de decodificar stdout; manter stderr separado. |
| Consulta válida sem resultados | Conferir destino, janela/timezone, revisão e filtros; relaxar um filtro por vez mantendo o escopo delimitado. Se persistir, informar que não foram encontrados registros nesse recorte. |
| Limite atingido / saída truncada | Reduzir intervalo, filtrar endpoint/status/trace ou projetar menos campos. Não contar a amostra limitada como total de ocorrências. |
| Request log mostra erro, mas não há exceção | Verificar se a versão publicada registra a exceção ou apenas responde HTTP. Não inventar uma causa; indicar outra fonte de evidência. |

Em consultas históricas, explicitar início e fim. `--freshness` tem padrão de um dia e só se aplica com ordenação descendente e sem filtro de timestamp. Não usar esse padrão como janela implícita de um incidente antigo.

Para falha de build, localizar o Cloud Build pelo SHA/trigger do deploy e consultar seu log no projeto/região confirmados; usar `gcloud builds log --help` para a CLI instalada. Isso não substitui os logs de runtime.

## Fontes

- [gcloud logging read: filtros, limites e janela](https://docs.cloud.google.com/sdk/gcloud/reference/logging/read).
- [Cloud Run: request logs, logs de contêiner e correlação](https://docs.cloud.google.com/run/docs/logging).
