---
name: pluggy
description: "Consultar Open Banking pessoal pela Pluggy e MeuPluggy: contas, cartões, transações, histórico de pagamentos (boletos, Pix, TED), faturas e investimentos. Usa Restish/OpenAPI com Infisical; exclui empréstimos, SCR e iniciação de pagamentos."
---

# Pluggy pessoal

Usar `~/Projects/agent-scripts/bin/pluggy`: adaptador de autenticação que delega consultas,
ajuda, filtros e paginação ao **Restish 2.3.0**. Não reimplementar um cliente financeiro.
Dez operações GET selecionadas da especificação oficial; sem mutações de recursos.
**Incluído:** consultar pagamentos já realizados, como boletos, Pix, TED e pagamentos de faturas,
conforme registros fornecidos pelo banco. **Fora do escopo:** efetuar/agendar novos pagamentos,
emitir cobranças, empréstimos e SCR. A exclusão de iniciação de pagamentos não exclui seu histórico.

## Acesso e configuração

- Infisical: projeto **Pessoal**, ambiente **dev**, pasta **/Pluggy** (case-sensitive).
- Login do cofre: `andre@aitrus.com.br`. Projeto fixado em `config/.infisical.json`.
- Variáveis: `PLUGGY_CLIENT_ID`, `PLUGGY_CLIENT_SECRET`, `PLUGGY_ITEM_ID`.
- `@item` é substituído pelo ID do cofre, sem mostrar seu valor. Outros recursos recebem UUID explícito: confirmar que pertencem à conexão desejada antes de selecionar.
- API Key gerada por `POST /auth`, apenas na memória; não reutilizar chave estática expirada. Não ler valores do cofre para diagnosticar.
- Setup e autenticação usam `curl` com validação TLS e suporte a `HTTPS_PROXY`/`https_proxy` via CONNECT; `NO_PROXY`/`no_proxy` define exceções. Corpo de autenticação passa por stdin, sem segredos em argumentos, arquivos ou logs. `.curlrc` é ignorado e logs de chaves TLS são desabilitados.
- Configuração, binário e cache de OpenAPI ficam em `.state/pluggy` no repositório, ignorados pelo Git. Cache HTTP das consultas financeiras desabilitado. Não persistir extratos/posições sem necessidade da tarefa.
- Instalar em Linux x86_64/WSL: `bash ~/Projects/agent-scripts/skills/pluggy/scripts/install-restish`. Download oficial com checksum fixado. Atualizar só a especificação: `pluggy setup`.
- `--help`, ajuda de operação e `setup` não exigem credenciais. Ajuda gerada pode mencionar flags gerais do Restish: o adaptador aceita só filtros, formato, parâmetros financeiros e ajuda; bloqueia verbos arbitrários, origem alternativa, verbose e impressão de headers.

## Consultas

```bash
CLI=~/Projects/agent-scripts/bin/pluggy
"$CLI" --help
"$CLI" items-retrieve @item -f 'body.{status,lastUpdatedAt}'
"$CLI" accounts-list @item -f 'body.results.{id,type,subtype}'
"$CLI" accounts-list @item --type CREDIT -f 'body.results.{id,type,subtype}'
"$CLI" transactions-list-by-cursor UUID_CONTA --date-from 2026-09-01 --date-to 2026-09-30 --rsh-filter-lang jq -f '.body.results | length'
"$CLI" bills-list UUID_CARTAO --rsh-filter-lang jq -f '.body.results | length'
"$CLI" investments-list @item --type FIXED_INCOME --rsh-filter-lang jq -f '.body.results | length'
"$CLI" investment-transactions-list UUID_INVESTIMENTO --rsh-filter-lang jq -f '.body.results | length'
"$CLI" investments-list --help
```

Sem filtro, a saída JSON contém dados completos. Preferir projeções/agregações relevantes;
consumir JSON em um processo local e levar ao contexto só o necessário. Não usar verbose,
`api auth inspect` ou imprimir o ambiente. Datas nos parâmetros: ISO `AAAA-MM-DD`.
Datas/timestamps ao André: formato brasileiro e São Paulo; preservar datas de negócio.

Detalhes individuais: `accounts-retrieve`, `transactions-retrieve`, `bills-retrieve`,
`investments-retrieve`, cada um com o UUID. A ajuda de operação traz parâmetros e schemas atuais.

## Paginação e interpretação

- Transações percorrem `next`; faturas, investimentos e movimentos usam página numérica iniciada em 1 automaticamente. Restish agrega `results` antes do filtro, sem limite de páginas. Warning/erro descarta a saída, para não entregar um extrato parcial.
- Envelope agregado conserva metadados da **primeira página**, inclusive `next` e `page`: não seguir esse `next` novamente. Em listas numéricas conferir `len(results)==total` antes de afirmar completude. `--rsh-no-paginate` ou `--page N` são recortes deliberados.
- Accounts não tem parâmetro `page` no OpenAPI atual: verificar `totalPages==1` e `len(results)==total`. Se tiver mais páginas, informar cobertura incompleta e investigar contrato oficial; não chamar a primeira página de lista completa.
- Fatura específica: filtrar transações **localmente após paginação** por `creditCardMetadata.billId`; API atual não documenta filtro remoto `billId`. Não estreitar datas sem conferir quais lançamentos compõem a fatura.
- Começar pelo estado do Item e data de atualização. Consulta bem-sucedida não prova atualização recente de todos os produtos.
- MeuPluggy (conector 200) espelha a conexão original, com atualização diária; não usar PATCH para atualizar o proxy. Banco novo exige outra autorização/Item. `nextAutoSyncAt=null` não prova falha.
- Null não significa zero; lista vazia não prova inexistência histórica. Cartão é Account `CREDIT`; saldo de cartão não equivale a patrimônio positivo nem necessariamente ao total da fatura.

## Histórico de pagamentos realizados

Consultar `transactions-list-by-cursor` de cada conta **BANK** relevante. Para saídas já
lançadas, selecionar `type=DEBIT` e `status=POSTED`; identificar a modalidade por
`operationType` e `paymentData.paymentMethod`, quando disponíveis. Isso inclui boletos,
Pix, TED, DOC e outras modalidades informadas pelo banco. Não classificar toda saída como
pagamento: saques, tarifas e transferências entre contas próprias podem exigir tratamento separado.
Dados disponíveis podem incluir data, valor, moeda, beneficiário, referências e motivo.
Para pagamentos de fatura, conciliar o débito bancário com o crédito no cartão e os pagamentos
informados na fatura, sem contar o mesmo pagamento duas vezes.

Exemplo: contar Pix enviados e lançados, após paginação completa:

```bash
"$CLI" transactions-list-by-cursor UUID_CONTA --rsh-filter-lang jq -f '.body.results | map(select(.type == "DEBIT" and .status == "POSTED" and (.operationType == "PIX" or .paymentData.paymentMethod == "PIX"))) | length'
```

### Boletos pagos

Está incluído em `transactions-list-by-cursor` da conta **BANK**, não exige endpoints de
iniciação/emissão de pagamentos. Ler todas as páginas; selecionar saídas `DEBIT`, status
`POSTED`, com `operationType=BOLETO`, `paymentData.paymentMethod=BOLETO` ou
`paymentData.boletoMetadata` presente. Exemplo só de contagem:

```bash
"$CLI" transactions-list-by-cursor UUID_CONTA --rsh-filter-lang jq -f '.body.results | map(select(.type == "DEBIT" and .status == "POSTED" and (.operationType == "BOLETO" or .paymentData.paymentMethod == "BOLETO" or .paymentData.boletoMetadata != null))) | length'
```

Consultar data, valor, moeda, descrição e beneficiário conforme necessidade. Metadados podem
trazer linha digitável/código de barras, principal, juros, multa e desconto. Não inferir boleto
com certeza só pelo texto; identificar candidatos separadamente se faltarem campos estruturados.
Não prometer PDF de comprovante ou cobertura integral histórica. Não inclui DDA de boletos
pendentes: a Pluggy documenta que esse produto não é suportado.

Para saldos, parcelas, reconciliação e investimentos, ler [references/data.md](references/data.md).
Para endpoints, erros, paginação ou mudanças, ler [references/api.md](references/api.md).
Usar documentação oficial atual: [Pluggy](https://docs.pluggy.ai/en/reference),
[MeuPluggy](https://meu.pluggy.ai/api-guide), [Restish](https://rest.sh/docs/).
Esta skill não autoriza alterar consentimentos, criar webhooks, emitir cobranças ou iniciar pagamentos.
