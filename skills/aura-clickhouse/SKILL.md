---
name: aura-clickhouse
description: Consultar com segurança e somente leitura o ClickHouse do Aura, incluindo descoberta de esquema, vendas, cotações, pedidos, catálogo e marts analíticos. Usar quando Codex precisar executar SQL, conferir dados atuais, localizar tabelas ou investigar o warehouse do Aura sem redescobrir conexão e credenciais.
---

# Aura ClickHouse

Usar o runner canônico. Não montar conexão, procurar credenciais ou chamar `curl` manualmente.

```bash
ch=/home/drelu/Projects/agent-scripts/skills/aura-clickhouse/scripts/aura-clickhouse
```

## Consultar

```bash
"$ch" ping
"$ch" databases
"$ch" tables analytics
"$ch" describe analytics.quote
"$ch" show-create analytics.quote_history
"$ch" columns ean
"$ch" query <<'SQL'
SELECT count()
FROM analytics.store
SQL
```

O runner:

1. Usar o conjunto completo de variáveis `CLICKHOUSE_DATASOURCE_*` do ambiente atual.
2. Se todas estiverem ausentes, reutilizar um conjunto único encontrado em processos locais.
3. Falhar com segurança diante de configuração parcial, credenciais ambíguas ou conexão ausente.
4. Proteger os segredos e executar o ClickHouse com `readonly=2`.

## Escolher a tabela

Ler [references/tables.md](references/tables.md) ao escolher fonte, grão ou identidade. Revalidar sempre o esquema vivo:

1. Executar `describe` antes de usar tabela desconhecida.
2. Executar `show-create` antes de varrer tabela grande; respeitar `ORDER BY`, partição e TTL.
3. Começar por contagem ou amostra limitada; só então agregar.
4. Distinguir campos originais, normalizados e agregados. Não inferir o grão pelo nome da tabela.

## Datas e segurança

- Trabalhar somente em leitura. Nunca executar DDL, DML, manutenção ou mutações.
- Para dias de negócio, interpretar a solicitação em `America/Sao_Paulo` e converter os limites para UTC.
- Não usar `max(data)` como definição implícita de hoje; definir a janela explicitamente.
- Em falha HTTP, ler o corpo `DB::Exception`: ele contém o erro real do ClickHouse.
- Nunca imprimir variáveis, ambiente de processo, senha, autenticação ou URL completa.

## Relatar

Informar concisamente:

- tabela e grão usados;
- período, timezone e filtros;
- resultado objetivo;
- limitação de cobertura ou semântica relevante.
