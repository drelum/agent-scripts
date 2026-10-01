# Interpretação financeira

Read when: analisar saldos, gastos de cartão, faturas, compras parceladas, patrimônio ou movimentos de investimentos.

## Contas e cartões

Cartões são recursos Account com `type=CREDIT`; contas bancárias usam `BANK`. Identificadores não são números de conta. `bankData` pode informar saldo de fechamento, aplicação automática e limites de cheque especial; `creditData` pode informar limite total/disponível, vencimento, pagamento mínimo e limites desagregados.

Não somar saldo de cartão como patrimônio positivo. Em conectores Open Finance, `balance` do cartão representa limite utilizado; não presumir que seja total de uma fatura. `closingBalance` de conta regulada pode incluir saldo bloqueado. Aplicação automática e posição de investimento podem representar o mesmo dinheiro: conferir antes de agregar patrimônio. [Contas](https://docs.pluggy.ai/en/docs/products/accounts).

## Transações e faturas

- Preservar `id`, `accountId`, `amount`, `type`, `currencyCode`, `date`, `status` e descrição. `amountInAccountCurrency` pode auxiliar compras em moeda diferente; não somar moedas sem conversão explícita.
- `paymentData` pode trazer método, pagador e recebedor. São dados pessoais; consultar só o necessário. Categorias e merchant podem aparecer, mas cobertura/plano variam; não prometer permanência dessas informações só porque um trial as retornou.
- `creditCardMetadata` pode trazer parcela atual/total, data de compra, `billId`, previsão de fatura e cartão. Campos variam por instituição.
- Bill informa total, moeda, vencimento, fechamento, mínimo, encargos e pagamentos. Consultar os lançamentos ligados ao `billId` antes de reconciliar. Não concluir que total da fatura é igual à soma simples de compras: pagamentos, ajustes, encargos e lançamentos faltantes podem explicar diferença.
- Compra parcelada pode aparecer integralmente ou mês a mês. Não extrapolar parcelas futuras como registros existentes; não inferir vínculo certo entre compras por descrição/valor. Não há identificador universal de agrupamento da compra.
- `PENDING` pode mudar para `POSTED` e receber vínculo com fatura; não tratar como duas compras. Deduplicar por `id` dentro da fonte; exclusão/recriação com outro ID exige investigação, não heurística automática.
- Documentação do guia afirma que `billPostDate` não é exposto, mas o campo apareceu no JSON da conexão durante exploração. Preservar quando presente, validar o comportamento observado e não garantir disponibilidade universal.

[Transações](https://docs.pluggy.ai/en/docs/products/transactions), [faturas](https://docs.pluggy.ai/en/docs/products/credit-card-bills), [parcelas](https://docs.pluggy.ai/en/docs/products/credit-card-installments).

## Boletos pagos

Histórico vem das transações BANK, selecionando DEBIT/POSTED com `operationType=BOLETO`,
`paymentData.paymentMethod=BOLETO` ou `boletoMetadata` presente. Estes sinais identificam
lançamentos de boleto; não substituem conciliação de estornos nem comprovante bancário em PDF.
Descrição isolada é indício, não classificação certa. Tributos/convênios podem ter classificação
própria: não incluir automaticamente em boleto sem evidência.

`paymentData` pode informar beneficiário/referências; `boletoMetadata` inclui `digitableLine`,
`barcode`, `baseAmount`, `interestAmount`, `penaltyAmount`, `discountAmount`. Cobertura varia
por instituição e histórico coletado. Não interpretar ausência de metadados como ausência de pagamento.
Pluggy não oferece DDA para descobrir boletos pendentes; API de gestão emite cobranças, e
iniciação de pagamento exige uma linha digitável já conhecida. São produtos distintos da consulta
do extrato, fora do escopo atual. [Boletos em transações](https://docs.pluggy.ai/pt/docs/products/transactions).

## Investimentos

`/investments` é posição, não histórico de negociação. Tipos incluem `FIXED_INCOME`, `EQUITY`, `ETF`, `MUTUAL_FUND`, `SECURITY`, `COE`, `OTHER`; conferir também `subtype` e `status`.

- Identificação: `name`, `code`, `isin`, emissor e CNPJ quando disponíveis.
- Posição: `quantity`, `value`, `amount` bruto, `balance` líquido conforme documentação, `amountOriginal`, lucro/resgate quando informados.
- Renda fixa: indexador `rateType`, percentual `rate`, componente prefixado `fixedAnnualRate`, emissão/compra, vencimento, carência, isenção e cupons quando disponíveis.
- `date` é a referência da posição/cotação; não equivale à hora da consulta ou da sincronização. Finais de semana podem retornar referência do último dia útil.
- `taxes` e `taxes2` são valores informados pela instituição, não orientação tributária nem cálculo completo de DARF. Null não significa zero.
- Movimentações estão em `/investments/{id}/transactions`, com BUY/SELL, crédito/débito, quantidade, valor, bruto/líquido, datas e despesas conforme fonte. Não depender do array `transactions` embutido, depreciado.
- Movimentações vazias não provam que nunca houve compra/resgate. Conferir cobertura e histórico disponível.

[Posições](https://docs.pluggy.ai/en/docs/products/investments), [movimentações](https://docs.pluggy.ai/en/docs/products/investment-transactions).

Relatórios ao André: datas brasileiras; timestamps convertidos para São Paulo; preservar datas de negócio sem deslocar um vencimento só porque a API o serializou como meia-noite UTC. Não inventar rentabilidade histórica sem série de posições e fluxos.
