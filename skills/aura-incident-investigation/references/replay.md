# Gravações e links

Read when: encontrar sessões, gerar links com tempo ou avaliar jornada gravada.

```bash
posthog-cli api info session-recording-get
python3 <skill>/scripts/incident_lab.py replay-metadata <session_id>
posthog-cli api info generate-app-url
posthog-cli api call generate-app-url '{"url":"/replay/{id}","params":{"id":"<session_id>"}}'
```

Para listagem por janela, descubra `query-session-recordings-list` com search/info/schema; para sessões de um erro, derive IDs dos eventos do erro. A chave `$session_id` não garante recording. Confira `found`, período, retenção, múltiplas janelas e ongoing. Não confundir metadados de replay com snapshots baixados.

Use a URL canônica retornada pelo CLI como base. Start/end vêm da gravação; erro vem do evento selecionado. Exemplo sintético:

```bash
python3 <skill>/scripts/incident_lab.py replay-link \
  --base-url '<URL canônica da gravação>' \
  --start '2026-10-08T12:00:00Z' \
  --error '2026-10-08T12:08:21Z' \
  --end '2026-10-08T12:15:00Z'
```

Resultado: `t=491`, erro em 08/10/2026 09:08:21 São Paulo; começa 10 s antes. Offset sempre em relação ao recording start; arredondar para baixo e limitar mínimo zero. O parâmetro posiciona a reprodução, não delimita seu fim. Nunca derivar URL de um momento fora da gravação. Sem end, declarar limite superior não verificado (`bounds_verified=false`). Acesso ao link ainda exige permissão no PostHog.

## Avaliação

Primeiro, reconstrua eventos antes/durante/depois da falha, separando timestamps, tentativas e resultado. Se já existir summary do Replay Vision, pode consultá-lo; texto automático é outra fonte, não prova de inspeção própria. Criar scanners pode consumir créditos/mudar recursos: não disparar por padrão.

Assistir ao trecho relevante, com antecedência e contexto após retry; anotar ação visível, estado da tela, mensagem e resultado. Se reconstruir localmente, desativar skipInactive e validar cada janela separadamente. Imagens/estilos externos carregados hoje podem divergir do estado histórico. O agente investigador pode usar `agent-browser` diretamente em sessão própria/isolada, sem depender de `visual-inspection`. Sem reprodução e conferência das imagens, entregar análise estrutural explicitamente limitada.

`replay-summary <events.json>` lê artefato local `{window_id: [rrweb events]}` e resume interações sem entradas de formulário, DOM completo ou chamadas externas. Não baixa eventos, não reproduz o player e não afirma completude. Input permanece privado, fora do Git; relatório também pode conter identificadores e exige revisão humana antes de anexar ticket.

## Download e reprodução local

Caminho único: `scripts/replay_investigate` da skill `aura-posthog`; seguir
`references/replay-investigation.md` dessa skill. Runtime, dependências fixadas e fontes PostHog estão
incluídos na skill, sem laboratório externo. Uma chamada `prepare --session <uuid> --name <nome>`
revalida encerramento, baixa snapshots em lotes com cache e gera contexto paginado de eventos/erros,
logs/traces disponíveis e vídeo integral indexado. Investigar e extrair snapshots desse mesmo pacote;
a missão/contexto do problema para Gemini entram depois da preparação determinística.

O instante do erro usa o relógio do cliente (`properties.$time` × 1000), relativo ao início dos snapshots;
não usar diretamente o timestamp corrigido pelo servidor. O `window_id_map` do manifesto liga o
`$window_id` original à aba numérica de `--window`. Procurar eventos, extrair snapshots antes/durante/depois
e conferir as imagens. Associação por horário/aba é aproximada; causa ou persistência exigem evidência própria.

Abrir o painel com `replay_investigate serve`, loopback e portless. O agente pode usar `agent-browser`
em sessão isolada de investigação, sem exigir `visual-inspection`, e fecha somente sua sessão. Capturas vêm do vídeo já indexado; não
reabrir/reconstruir o player para cada imagem. `annotate` salva observações e hipóteses referenciadas;
`ticket` cria ZIP local com imagens, texto e JSON/hashes, sem publicar ou enviar.

Catálogo CLI verificado em 08/10/2026: snapshots não expostos; metadados continuam pelo CLI. Download
usa exceção explícita GET na API de snapshots. Não contornar acesso negado; em 429 respeitar Retry-After.
Não usar exportação/scanner hospedado nem o laboratório/player anterior como outro caminho. Não versionar
snapshots, DOM de clientes, vídeo, frames ou credenciais no Context.
