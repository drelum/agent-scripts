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

Caminho padrão: `replay_lab.py` da skill `aura-posthog` (`references/replay-lab.md`). Com o `$session_id` e o
horário do evento de erro, uma chamada baixa a sessão em lotes de 21 blocos para cache, reconstrói e entrega um
laboratório local para o `agent-browser`: relógio relativo ao erro, `lab.ir`, `lab.tocar`, `lab.linha`,
`lab.janela`, e aviso explícito quando não há gravação no instante do erro. Passar `--window-id` com o
`$window_id` do evento quando houver várias janelas. Outro intervalo reaproveita o cache, sem requisição nova.

Alternativa para sessões inteiras ou amostras: `replay_download.py` (mesmos lotes e ritmo) e
`replay_evidence.py frame --window-id <id>`, com tempo relativo àquela janela, não ao erro.

Catálogo CLI verificado em 08/10/2026: snapshots não expostos; metadados continuam pelo CLI, download usa exceção
explícita GET na API de snapshots do PostHog. Não contornar acesso negado nem fazer fallback silencioso. A cota
de snapshots é por personal key; 429 traz `Retry-After`: esperar, não trocar de chave.

O agente investigador opera o laboratório ou o player diretamente, em sessão própria de `agent-browser`. Para
conclusões sobre sequência, acompanhar o trecho antes/depois, pois um frame isolado não prova a transição. Ao
concluir, fechar somente a sessão de browser criada para a investigação. Não versionar snapshots, HTML com DOM de
clientes, frames ou credenciais no Context; incluir apenas scripts, testes e instruções.
