---
name: aura-packaging
description: Diagnosticar o empacotamento correto de um EAN numa loja Aura (cotação, NF, venda, custo). Usar quando Andre passar um EAN, CNPJ ou "qual a embalagem/caixa/cartela" — não montar SQL ad hoc.
---

# Aura Packaging

Andre passa um EAN (e opcionalmente um CNPJ). Rodar o script; interpretar; não escrever no KV.

```bash
pk=/home/drelu/Projects/agent-scripts/skills/aura-packaging/scripts/aura-packaging
"$pk" <ean>                  # loja padrão 05101867000157
"$pk" <ean> <cnpj>
"$pk" --days 90 <ean> <cnpj>
```

Consulta só leitura via runner `aura-clickhouse`. Janela padrão 365 dias em `America/Sao_Paulo`. Cotação = snapshot vigente.

## Receita (nesta ordem)

1. **Unidade da loja** = o que ela vende. Preço de venda + volume + `fraction`/`box_count` do catálogo. `X 240` no nome costuma ser comprimido, não unidade.
2. **Custo confiável** = `custo_erp` da venda se estiver entre ~15% e ~80% do preço de venda. Se custo ≈ líquido da cotação/NF, o ERP já gravou preço de caixa — não usar como denominador.
3. **Origem** = cotação (`bruto`/`líquido`) e NF (`unit_price` + `tipo`). `product_unit_type` mente; `CX`/`UN` não decide.
4. **Fator** = preço da origem ÷ custo confiável. `n_sugerido` prefere a `fraction` do catálogo/venda (±25%); senão inteiro próximo. `min(bruto) ≈ custo` e `max/min` grande → desconto, não caixa. Não cravar `n_sugerido` sozinho.
5. **Mesmo N em várias origens** (catálogo 24BL, NF ~N×custo, cotações no mesmo cluster) → hipótese forte. Um sinal só → ambíguo.
6. KV/API só se Andre pedir o que já está curado. Sem escrita.

## Relatar

- unidade vendável e fator (`Caixa com N` ou “ambíguo”);
- tabela curta das cotações (bruto, líquido, ≈R$/un se N claro);
- 1 linha de venda + NF que sustentam;
- o que ficou em dúvida.

Não reescrever as queries do script. SQL extra só para um furo pontual do relatório.
