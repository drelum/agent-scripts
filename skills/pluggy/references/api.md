# Contratos de leitura

Read when: parâmetros, paginação, erros, cobertura, atualização ou drift do OpenAPI.

Referência consultada em 01/10/2026. Base: `https://api.pluggy.ai`.
`POST /auth` recebe `clientId`/`clientSecret`; resposta `apiKey`, enviada em `X-API-KEY`,
com validade de 2 horas. Connect Token não permite produtos detalhados.
[Autenticação](https://docs.pluggy.ai/en/reference/authentication).

| Comando gerado | Endpoint GET | Seleção |
|---|---|---|
| items-retrieve | `/items/{id}` | Estado e coleta |
| accounts-list | `/accounts?itemId=...` | type BANK/CREDIT |
| accounts-retrieve | `/accounts/{id}` | Detalhe |
| transactions-list-by-cursor | `/v2/transactions?accountId=...` | Datas ISO; next |
| transactions-retrieve | `/transactions/{id}` | Detalhe |
| bills-list / bills-retrieve | `/bills?accountId=...` / `/bills/{id}` | Conta de cartão; página |
| investments-list / investments-retrieve | `/investments?itemId=...` / `/investments/{id}` | Tipo; página |
| investment-transactions-list | `/investments/{id}/transactions` | Página |

## Paginação

Restish tem duas configurações locais: `pluggy` para páginas e `pluggy-cursor` para `next`.
O adaptador escolhe automaticamente. Numéricas começam em 1 e terminam numa lista vazia;
Restish não usa `totalPages` como condição final. Conferir `results` versus `total`.
Cursores seguem `next` até fim; Restish restringe próximo link à mesma origem.
`--rsh-collect` agrega antes do filtro, `--rsh-max-pages 0` remove o limite padrão de 25.
Warnings/erros são tratados como falha pelo adaptador; saída parcial descartada.
Envelope agregado mantém metadados iniciais: não repetir `next` desse envelope.
`--rsh-no-paginate` retorna apenas uma página.

- Accounts sem parâmetro page: exigir `totalPages==1` e `len(results)==total` para afirmar lista completa.
- Legado `GET /transactions` retornou **410**; usar `/v2/transactions`, sem fallback.
- `billId` não é filtro remoto documentado: filtrar localmente os registros completos por `creditCardMetadata.billId`.
- [Restish paginação](https://rest.sh/docs/guides/pagination/), [Pluggy convenções](https://docs.pluggy.ai/en/reference/basic-concepts).

## Configuração e drift

`pluggy setup` busca o [OpenAPI oficial](https://docs.pluggy.ai/openapi/pluggy-api.json),
seleciona apenas os dez GETs e fixa a origem. Parâmetros/schemas/ajuda vêm desse documento;
nomes estáveis definidos por `x-cli-name`. A especificação completa pública fica local,
com os paths limitados; não contém dados da conta. Operações fora do escopo não ficam disponíveis.
Binário fixado em 2.3.0 com checksum: atualização de versão exige nova verificação de contratos.
[OpenAPI Restish](https://rest.sh/docs/reference/openapi-cli-integration/).

## Cobertura e erros

- `401`: credenciais/chave; `403`: permissão/plano; `404`: recurso inacessível; `429`: limite; `5xx`: upstream. Nunca inferir conta vazia de falha HTTP. O adaptador omite corpo de erro e headers; investigar sem imprimir segredos.
- Restish faz retries de rede/HTTP transitório conforme versão; espera máxima de retry fixada em 30 segundos. Não repetir autenticação por registro: um processo autentica uma vez.
- MeuPluggy: atualização original diária e propagação ao proxy, sem atualização manual. `nextAutoSyncAt=null` não prova falha. [Items](https://docs.pluggy.ai/en/docs/connections/item).
- `GET /connectors/{id}` pode esclarecer cobertura numa investigação autorizada separada; não foi incluído nesta superfície curada.
- `GET /accounts/{id}/balance` busca saldo ao vivo **e altera o recurso**; excluído. [Saldo ao vivo](https://docs.pluggy.ai/en/docs/products/real-time-balance).
- Sincronização futura precisa processar criação/alteração/exclusão. Referência lista `transactions/created`, `transactions/updated`, `transactions/deleted`; guia de parcelas usa singular. Usar contrato atual/payload real. Criar webhook requer tarefa específica. [Webhooks](https://docs.pluggy.ai/en/reference/webhooks).
