---
name: aura-posthog
description: Analisar o uso do Aura no PostHog (projeto 331102), com foco em navegação, itens no carrinho, envio de pedido e erros. Usar para jornada de um usuário, funil do carrinho ao envio, erros no carrinho ou no envio, perfis de navegação, origem das sessões e cruzamento com pedidos do ClickHouse. Descobre eventos e propriedades a cada uso, porque a instrumentação muda.
---

# Aura PostHog

Análise de comportamento no Aura via PostHog, somente leitura. Eventos e propriedades mudam com o produto:
**descobrir primeiro, consultar depois**. O que está em `references/` é conhecimento datado, não contrato.

```bash
ph=/home/drelu/Projects/agent-scripts/skills/aura-posthog/scripts/aura-posthog
```

## Antes de começar

1. Na primeira consulta ao PostHog da sessão, rodar `posthog-cli api --agent-help` (regra global do workspace).
2. Descobrir o que existe agora, sem supor nomes:

```bash
"$ph" events --days 30                         # eventos vigentes, volume, último dia e hosts
"$ph" events --match "cart|checkout|order"     # recorte por tema
"$ph" events --match "fail|error|refus|exception"
"$ph" props cart_checkout_failed --custom      # propriedades próprias do Aura e cobertura
"$ph" values cart_item_added source            # valores reais de uma propriedade
"$ph" user fulano@farmacia.com.br              # e-mail → ID no cadastro Aura + atividade por host
"$ph" sql consulta.sql                         # HogQL livre; aceita {{USER_ID}} e {{IDENTIFIED}}
```

3. Comparar o que encontrou com `references/knowledge-map.md`. Divergência é informação: diga ao usuário o que mudou e siga pelos dados atuais.

## Regras fixas

- **Host é dimensão, não filtro.** Há vários hosts (tenants e ambientes). Mostrar a quebra por `$host` quando relevante; filtrar só quando o usuário pedir.
- **Usuário:** use `{{USER_ID}}` (mesma identidade do Painel) e `{{IDENTIFIED}}` (exclui eventos marcados como anônimos). E-mail não está no PostHog de forma confiável: resolva com `"$ph" user <email>`.
- **Internos:** excluir e-mails `@hipersaude.com.br` e `@aitrus.com.br` (regra do Painel) quando a análise for de uso por farmácias. A propriedade `is_internal` cobre poucas pessoas; não depender só dela.
- **Nunca exibir URL crua.** URLs de `/login` e a coluna `$urls` de sessões trazem token de login. O executor mascara tokens e JWTs, mas prefira `cutQueryStringAndFragment(...)`, `$pathname` ou `extractURLParameterNames(...)`. Não salvar resultados brutos fora do scratchpad.
- **Datas e horas em São Paulo:** `toTimeZone(timestamp, 'America/Sao_Paulo')`; limites de dia em São Paulo.
- **Somente leitura.** Não criar insights, dashboards, flags ou anotações sem pedido explícito.

## Roteiros

Ler `references/playbooks.md` e escolher pelo tipo de pergunta. Cada roteiro diz o que descobrir, o que consultar e como interpretar:

- **Jornada de um usuário:** sessões, entrada, telas visitadas, ações e erros em ordem.
- **Carrinho e envio:** funil item → início do envio → sucesso, abandono e valor.
- **Erros no carrinho e no envio (prioridade):** falhas explícitas, exceções, erros de console nas gravações e sinais de comportamento.
- **Navegação e origem:** página de entrada, referrer, destino do link de login, perfis por módulo.
- **Cruzamento com pedidos:** confirmar no ClickHouse (skill `aura-clickhouse`) se o envio virou pedido.

Para detalhes de HogQL (funções que não existem, teto de 500 linhas, paginação por chave, tabela `sessions`,
gravações), ler `references/hogql.md` antes de montar consultas não triviais.

## Relatar

- Período em São Paulo, hosts incluídos, filtros (internos, usuários) e eventos usados com a data da verificação.
- Números em tabela curta; separar fato observado de interpretação.
- Apontar lacunas de instrumentação quando a pergunta não puder ser respondida (ex.: carrinho sem EAN, falha ao adicionar item sem evento próprio).
- Atualizar `references/knowledge-map.md` quando a descoberta mostrar evento ou propriedade nova, removida ou com significado diferente, com a data.
