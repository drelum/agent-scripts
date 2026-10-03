# Aquisição e transformação upstream

Read when: a divergência já aparece na base integrada, ou é necessário comparar
cargas do ERP e execuções do pipeline.

## Descoberta orientada pelo caso

Confirmar conta, projeto, tabela, armazenamento e execução atuais. Usar instruções
locais e referências do código antes de procurar conexões. Não imprimir ambientes,
configurações de provider ou credenciais para descobrir destinos.

Pontos observados em 01/10/2026, revalidar antes do uso:

- `aitrus-sync-prod`: aquisição de ERP; bucket `aitrus-sync-prod-staging`.
- Prefixo bruto `sync/v3/<tipo>/dt=AAAA-MM-DD/`; arquivos podem começar com CNPJ e
  load ID. Há também `sync/v3-compacted/`, com outro layout e retenção.
- `aitrus-data-prod`: transformação; Cloud Run job `dbt-data-transform-job`, região
  `us-central1`. Agendamento observado de estoque: `dbt-transform-stock`.
- O bucket de aquisição `aitrus-data-prod-acquisition` também contém exportações:
  um arquivo ali não é automaticamente a resposta bruta do ERP.

Preferir prefixo exato de tipo, data e CNPJ. Consultar os metadados/manifesto da carga
quando precisar comprovar conclusão, quantidade de partes e snapshot completo. Ler
uma parte não comprova ausência do produto no conjunto.

```bash
gcloud storage ls 'gs://aitrus-sync-prod-staging/sync/v3/stock/dt=AAAA-MM-DD/CNPJ*'
gcloud scheduler jobs describe dbt-transform-stock \
  --project=aitrus-data-prod --location=us-central1 \
  --format='yaml(schedule,timeZone,lastAttemptTime,status,httpTarget.uri)'
gcloud run jobs executions describe EXECUCAO \
  --project=aitrus-data-prod --region=us-central1 \
  --format='yaml(metadata.name,status.startTime,status.completionTime,status.conditions,status.failedCount)'
```

`lastAttemptTime` do Scheduler não comprova conclusão do modelo. A execução iniciada
mais recentemente pode ainda estar em andamento; correlacionar a execução do incidente.
Para logs, projetar timestamp, mensagem e `labels."run.googleapis.com/execution_name"`;
o nome da execução nem sempre está em `resource.labels`. Restringir janela e modelo,
ler também as linhas próximas ao erro e seguir as regras de `aura-cloud-logs`.

## Parquet sem materializar a base do cliente

Inspecionar o esquema antes de escolher campos: no bruto Alpha7 observado, o EAN era
`codigo_barra_produto`, não `ean`. Saldo e custo vieram como strings; normalização e
fuso precisam ser verificados na transformação. O load ID pode lembrar um epoch em
milissegundos, mas o horário da extração deve ser conferido pelo campo/manifesto.

Exemplo Python; substituir URI, identidade e campos após ler o esquema. Não instalar
bibliotecas se já houver runtime disponível no projeto. O exemplo filtra a saída,
mas baixa uma parte inteira em memória: conferir seu tamanho antes.

```python
import io
import json
import subprocess
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

uri = "gs://BUCKET/PREFIXO/PARTE.parquet"
result = subprocess.run(["gcloud", "storage", "cat", uri], capture_output=True)
if result.returncode:
    raise RuntimeError("Falha na leitura do objeto; verificar acesso e caminho")

parquet = pq.ParquetFile(io.BytesIO(result.stdout))
print(parquet.schema_arrow.names)
# Campos confirmados pelo esquema, limitados ao diagnóstico.
columns = ["codigo_barra_produto", "saldo_estoque", "load_id", "extracted_at"]
table = parquet.read(columns=columns, use_threads=False)
rows = table.filter(pc.equal(pc.cast(table["codigo_barra_produto"], pa.string()), "EAN"))
print(json.dumps(rows.to_pylist(), default=str, ensure_ascii=False), flush=True)
```

Para múltiplas partes/cargas, filtrar cada uma sem imprimir linhas de outros produtos.
Evitar repetir downloads só para corrigir nome de coluna. Se precisar de arquivo local,
usar destino confidencial ignorado pelo Git e não incluir o payload no relatório.

## BigQuery e camadas analíticas

Listar datasets/tabelas e inspecionar esquema, partição, clusterização e tamanho antes
de consultar. Tabelas antigas de staging e exports podem não participar mais do fluxo.
Limitar período/loja/produto, estimar scan com dry-run e definir teto de bytes quando
necessário. `PERMISSION_DENIED` é lacuna de acesso; não ampliar IAM durante diagnóstico.

No ClickHouse, reutilizar o runner de `aura-clickhouse`. Para estoque, começar por
`analytics.stock` e `analytics.product_assortment` quando forem as fontes apontadas pelo
código. `load_id`/`loaded_at` identificam carga; `stock_update_date` pode representar o
último movimento do produto. Uma linha carregada hoje pode ter movimento antigo válido.

Para vendas, verificar identidade original versus EAN normalizado, documentos,
devoluções, exclusões e limites do dia de negócio antes de somar. Comparar o mesmo
intervalo e grão no ERP, aquisição, fato e agregado; registros de hoje ainda não
extraídos não comprovam perda no pipeline. Para custo, distinguir ERP, NF e fonte
substituta escolhida pelo mart. Empacotamento/caixa/cartela usa `aura-packaging`.

O teste decisivo é a continuidade do mesmo registro entre camadas, não apenas um
horário global recente ou sucesso de outro job. Anotar o primeiro valor divergente e
o último passo confirmado; revalidar a métrica final após uma correção autorizada.
