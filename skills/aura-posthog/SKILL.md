---
name: aura-posthog
description: Analisar eventos, jornadas e erros do Aura no PostHog; acessar e baixar sessões gravadas, reconstruir a reprodução local, avaliar vídeo/contexto com Gemini e capturar frames no instante relevante. Usar para entender o que ocorreu numa sessão, investigar bloqueios no carrinho/checkout, comparar antes/depois de uma falha ou correlacionar a jornada com pedidos no ClickHouse. Descobrir eventos e propriedades a cada uso.
---

# Aura PostHog

Análise de comportamento no Aura via PostHog, somente leitura. Eventos e propriedades mudam com o produto:
**descobrir primeiro, consultar depois**. O que está em `references/` é conhecimento datado, não contrato.

```bash
ph=<skill>/scripts/aura-posthog   # <skill> = pasta deste SKILL.md
```

## Antes de começar

1. Na primeira consulta ao PostHog da sessão, rodar `posthog-cli api --agent-help` (regra global do workspace).
   **Teto de linhas:** `execute-sql` devolve no máximo 500 linhas (100 sem `LIMIT`), sem avisar. Resultado com
   500 está cortado: paginar (`references/hogql.md`). `"$ph" sql` exige `LIMIT` e falha no teto.
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

## Gravações

Entrada única: `scripts/replay_investigate`. O runtime, lockfile e fontes PostHog verificadas estão
incluídos em `scripts/replay_runtime/`; não precisa do laboratório nem de um clone OSS. Ler
`references/replay-investigation.md` para `setup`, `doctor`, preparação, painel e evidências.
Para pacote de sessão inteira ou lote recente, usar `prepare --session <uuid>` ou
`prepare --latest <n> --name <prefixo>`. Prepara deterministicamente contexto paginado e MP4 integral
disponível; a pergunta, o problema e a análise Gemini entram somente depois, reutilizando esse pacote.
O renderer lê o dataset uma vez e captura até dois blocos em paralelo, com páginas isoladas, ordem
temporal validada e tempos internos no manifesto; mantém FPS, inatividade e snapshots do mesmo MP4.
Intervalos sem gravação entre abas recebem cartões explícitos e cobertura parcial no manifesto;
não são telas do usuário nem evidência de frustração. Corrupção/falha do renderer continuam rejeitadas.
Pilotos e lotes usam sessões encerradas (`ongoing: false`) por padrão; selecionar e revalidar conforme
`references/replay-download.md`. Sessões abertas só entram quando o pedido exigir isso explicitamente.

| Objetivo | Caminho | Referência |
|---|---|---|
| Avaliar sessão, frustração ou objetivo não atingido | `prepare` → `analyze` com Gemini → conferir snapshots/eventos → priorizar → `annotate/ticket` | `references/replay-investigation.md` |
| Acesso, login, localizar sessões | `posthog-cli api` (metadados) | `references/replay-download.md` |
| Somente preparar pacote ou lote | `prepare`: contexto, MP4 integral, índice e cobertura; ainda sem análise Gemini | `references/replay-investigation.md` |

O download usa a API de snapshots, ausente no catálogo do CLI verificado; essa exceção GET é explícita, não
fallback silencioso. **O script produz o vídeo**, com Puppeteer + `chrome-headless-shell` + FFmpeg;
**Gemini avalia vídeo e contexto**; **o agente confere as evidências e prioriza o impacto**.
`agent-browser` não participa da geração nem é pré-requisito da análise. Para inspeção manual adicional
no painel de replays históricos, o agente pode usar a CLI global
`agent-browser` em sessão isolada `replay-`; fecha somente essa sessão. Sem conferir as imagens,
declarar a análise como estrutural. QA de desenvolvimento do painel exige `visual-inspection`.

Os scripts `replay_download.py` e `replay_evidence.py` fornecem transporte, sanitização e análise estrutural
ao runtime. Seus comandos anteriores e `replay_lab.py`/JS permanecem históricos; não usá-los como outro
fluxo de investigação. `prepare` não chama LLM. Pedido de avaliar sessões/frustração inclui executar
`analyze`; pedido apenas de download/preparação não inclui essa etapa. Se Gemini não rodou, declarar
"pacote preparado; análise Gemini pendente", sem apresentar triagem estrutural como avaliação concluída.
Tickets continuam locais.

Para avaliação por Gemini, usar `analyze <pacote> --mission <arquivo> --name <análise>`, depois de `prepare`.
Ler **Analisar com Gemini** em `references/replay-investigation.md`: credencial Infisical, fontes dos
prompts, limites e referências. A missão/problema são variáveis; o vídeo/contexto já preparados são
reutilizados. O executor aplica limitações, valida IDs/timestamps, extrai snapshots numa passagem e
marca o resultado como pendente de conferência visual. Não tratar resposta do modelo como fato validado.

## Relatar

- Período em São Paulo, hosts incluídos, filtros (internos, usuários) e eventos usados com a data da verificação.
- Números em tabela curta; separar fato observado de interpretação.
- Apontar lacunas de instrumentação quando a pergunta não puder ser respondida (ex.: carrinho sem EAN, falha ao adicionar item sem evento próprio).
- Atualizar `references/knowledge-map.md` quando a descoberta mostrar evento ou propriedade nova, removida ou com significado diferente, com a data.
