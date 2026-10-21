---
name: aura-incident-investigation
description: Investigar incidentes do Aura envolvendo frontend, backend, cotação ou Sync. Usar para triagem de erros recentes, identificação de usuários/lojas/pedidos afetados e preparação ou revisão de tickets, correlacionando logs, eventos PostHog, sessões gravadas e dados persistidos, com links no instante da falha.
---

# Investigação de incidentes Aura

Fonte canônica em `agent-scripts/skills/aura-incident-investigation`, disponibilizada globalmente por symlinks para Codex e Claude. Resolver `<skill>` pela pasta deste `SKILL.md`.

Diagnóstico de leitura por padrão. Criar/editar/atribuir ticket apenas quando solicitado. Não corrigir produção, alterar IAM, enviar Slack ou gerar scanners pagos automaticamente.

## Entrada e acesso

1. Identifique janela, ambiente e objetivo. Sem período explícito, use últimas 24 horas com corte fresco; horários em São Paulo e UTC nas consultas. Carrinho/checkout e completude/defasagem de estoque, vendas e cotações são fluxos prioritários.
2. Resolva a pasta desta skill pela localização deste arquivo. Execute `python3 <skill>/scripts/incident_lab.py doctor`. Para pessoa nova, dependência ausente ou acesso falhando, leia [onboarding.md](references/onboarding.md). Infisical é opcional; não procurar credenciais em outros processos, históricos ou arquivos do colega.
3. Rode `doctor --live` para validar fontes individualmente. Não confundir ferramenta instalada com acesso nem consulta vazia com sistema saudável. Antes de PostHog, leia `posthog-cli api --agent-help`, confira `api skill list`, instale/leia a skill pertinente quando houver. Use `api search`, `info` e `schema` antes de montar payloads desconhecidos.

## Investigação

Leia [investigation.md](references/investigation.md) para correlação, priorização e ticket. Descubra esquemas antes de SQL; execute uma instrução de leitura por chamada, com janela e campos mínimos. `scripts/incident_lab.py clickhouse|mysql` recebem SQL por stdin ou `--sql-file`. Os servidores também precisam garantir leitura; a guarda SQL não substitui grants.

PostHog: use o CLI para eventos, Error Tracking, usuários e metadados de replay. Para métricas, consulte o catálogo primeiro conforme o guia; para eventos, confirme nomes/propriedades pelo schema. Sessão não equivale a usuário, loja, pedido ou causa. Separe erro de negócio tratado de `$exception`; valide release/chunk/resolução de cada stack.

Para um replay, consulte `replay-metadata <session_id>` e leia [replay.md](references/replay.md). Use `generate-app-url` ou URL canônica retornada pelo PostHog como base e `replay-link` para adicionar o instante. `t` é relativo ao `start_time` da gravação, com 10 s de antecedência por padrão, sem pular tempo inativo. Nunca usar o primeiro snapshot de uma janela como origem. Ausência de gravação ou limites desconhecidos precisam ficar explícitos.

Para autenticar no PostHog, localizar sessões e produzir vídeo/frames locais, usar a skill complementar `aura-posthog`: acesso em `references/replay-download.md`; investigação pelo único comando `scripts/replay_investigate`, conforme `references/replay-investigation.md`. O pacote do Context deve incluir a skill inteira, com seu runtime e fontes PostHog, sem caches privados ou node_modules. Consulta de metadados não substitui o download nem a revisão visual. Para investigar replays históricos, o agente pode usar `agent-browser` diretamente no painel local, em sessão própria/isolada, sem exigir `visual-inspection`; seguir [replay.md](references/replay.md).

## Entrega

Produza diagnóstico sanitizado: janela, fontes e limites, prioridade, sintoma/impacto, pessoas/lojas/pedidos com fonte e confiança, causa confirmada ou hipótese, links de gravações e lacunas. Observação estrutural não é revisão visual; contagem de requisições não é pedidos perdidos. Não copiar payloads, entradas de formulário ou credenciais. Use o modelo de ticket da referência, procure duplicatas e confirme responsável antes de publicar; após publicação autorizada, releia conteúdo e atribuição.

Os auxiliares validam acesso, consultas, metadados, links e análise estrutural offline. Download/player usam os auxiliares de `aura-posthog`; reportar sua validação separadamente, incluindo formato suportado, cobertura de janelas e inspeção visual efetivamente realizada. Incorporação no Context, validação real do MySQL e instalação em máquina limpa continuam pendentes.

Verificação offline: `python3 -m unittest discover -s <skill>/scripts -p 'incident_lab_test.py'`. Os pilotos e evidências privadas ficam no laboratório Sentinel, fora do pacote da skill.
