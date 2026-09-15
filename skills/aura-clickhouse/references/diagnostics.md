# Diagnóstico e consumo de resultados

Ler quando uma chamada falhar, houver timeout ou o resultado for processado por outro programa.

## Erros SQL

Ler o corpo da resposta antes de repetir a chamada. HTTP 500 com `DB::Exception` pode ser erro da consulta; não implica indisponibilidade do serviço.

| Sinal | Correção |
| --- | --- |
| `Multi-statements are not allowed` | Enviar uma instrução por chamada. Separar as consultas em chamadas do runner ou combinar a análise em uma instrução com CTEs/subconsultas. |
| `ILLEGAL_AGGREGATION` | Verificar agregações aninhadas e aliases iguais a colunas de entrada. Usar `sum(stores) AS total_stores` e `countIf(rolling_base > 0) AS rolling_base_count` quando essas colunas também forem usadas em outras agregações. Se houver duas etapas de agregação, separá-las em subconsulta/CTE. |
| `UNKNOWN_TABLE` / `UNKNOWN_IDENTIFIER` | Confirmar banco/tabela com `tables`, localizar colunas com `columns` e conferir `describe`; corrigir a consulta a partir do esquema vivo. |
| `arquivo SQL não encontrado` | O argumento de `query` deve ser um caminho existente. Para SQL inline, usar stdin com heredoc de delimitador entre aspas (`<<'SQL'`). |

## Resultados para scripts

Escolher o formato explicitamente na consulta: `FORMAT JSON` retorna um documento com as linhas em `data`; `FORMAT JSONEachRow` retorna um objeto por linha. Não interpretar a saída tabular padrão como JSON.

Confirmar sucesso do processo antes de interpretar stdout e manter stderr separado. Uma falha pode deixar texto de erro ou saída incompleta em stdout. Exemplo com consulta sem dados de negócio:

```python
import json
import subprocess

result = subprocess.run(
    ["/home/drelu/Projects/agent-scripts/skills/aura-clickhouse/scripts/aura-clickhouse", "query"],
    input="SELECT 1 AS value FORMAT JSON",
    text=True,
    capture_output=True,
    check=True,
)
rows = json.loads(result.stdout)["data"]
```

Se houver `CalledProcessError`, inspecionar o corpo em `stdout` e o diagnóstico em `stderr` antes de corrigir a causa; não tentar decodificar a resposta como resultado válido.

## Timeout

O runner usa timeout HTTP de **60 segundos** e envia `max_execution_time=55` ao servidor. `AURA_CLICKHOUSE_TIMEOUT_SECONDS` aceita inteiros de 1 a 300 e altera somente o timeout do cliente; aumentá-lo não amplia o limite de execução SQL.

Conferir `show-create`, filtros de período/loja e volume lido antes de repetir uma consulta lenta. `LIMIT` no resultado de uma agregação não garante uma varredura pequena. Distinguir timeout do cliente de `DB::Exception` do servidor antes de ajustar a consulta ou a espera.

## Configuração e conexão

Configuração ausente, parcial ou ambígua exige conferir o comando de inicialização canônico do projeto e seu contexto Infisical. Não completar variáveis copiando segredos de arquivos ou processos; a descoberta de processos é responsabilidade do runner.

Com a configuração disponível, `info` informa a origem usada e consulta o servidor sem imprimir credenciais. Usar o erro retornado para distinguir configuração, autenticação, transporte e SQL; repetir a mesma consulta não corrige configuração inválida.
