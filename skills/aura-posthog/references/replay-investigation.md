---
read_when: Preparar sessão completa ou lote, investigar contexto local e exportar snapshots para um ticket.
---

# Sessão consultável

Um pipeline: snapshots API → cache validado → parser PostHog → sanitização → renderização contínua
com relógio virtual → vídeo indexado → eventos/contexto → snapshots e ticket. Implementação incluída em
`scripts/replay_runtime/`, com dependências fixadas pelo lockfile e fontes PostHog em `vendor/posthog/`.
Não usar exportação de vídeo hospedada nem scanners hospedados. O agente investiga os artefatos locais.

## Instalar e verificar

Requisitos: Linux/WSL, Python 3.11+, Node 24+, npm, pip com suporte a `--python`, FFmpeg/ffprobe, CLI global `posthog-cli` e
**chrome-headless-shell**. Chrome comum não atende ao capturador. Configurar `PUPPETEER_EXECUTABLE_PATH` com caminho
Linux absoluto do executável já instalado; não há caminho fixo de máquina nem download de browser.

```bash
<skill>/scripts/replay_investigate setup
<skill>/scripts/replay_investigate doctor
```

`setup` executa `npm ci --ignore-scripts`, o build e instala `analysis-requirements.txt` no venv privado
`private/analysis-venv`. Não modifica pacotes Python globais, não acessa sessões nem autentica.
O venv é criado sem `ensurepip`; pip externo instala nele com `--python`. `doctor` verifica também Jinja2/jsonschema,
o processo realmente iniciado e um frame via `HeadlessExperimental.beginFrame` numa página sintética local.
O pré-teste acontece antes da coleta de sessões novas. Não baixa navegador nem usa agent-browser.
`doctor` retorna JSON e status não zero para ferramenta, Chrome ou build ausentes/corrompidos. As fontes
PostHog são do commit `f339527d3ede876431f9da61cbc901a705f8f60a`; o build verifica o inventário e todos
os hashes do manifesto incluído. Nenhum clone externo é necessário. Node/npm/Python/FFmpeg/Chrome e
autenticação CLI são dependências do ambiente, não arquivos fornecidos pela skill.

Artefatos e caches ficam em `scripts/replay_runtime/private/`, ignorados pelo Git. Não copiar essa pasta
ou `node_modules/` ao distribuir a skill. Usar `setup` no destino. Gate do runtime: `npm run gate`;
aponta também exports/tipos sem uso presentes nas fontes upstream, sem ocultar essa dívida.

## Preparar

Em pilotos e lotes, selecionar sessões com `ongoing` exatamente `false`, conforme
`replay-download.md`, e revalidar antes de baixar. A seleção ignora sessões abertas ou de estado
desconhecido; um pedido explícito de uma sessão em andamento preserva esse escopo e seus limites.

Após a descoberta obrigatória do CLI, executar o wrapper da skill:

```bash
<skill>/scripts/replay_investigate prepare --latest 3 --name piloto --fps 3
# Uma sessão específica, pelo mesmo pipeline:
<skill>/scripts/replay_investigate prepare --session <uuid> --name sessao-completa --fps 3
```

`prepare` é a preparação determinística para análise posterior: seleciona por início mais recente,
ignora `ongoing: true`, ausente ou desconhecido, pagina a seleção e revalida imediatamente antes do
download. `--date-from` amplia o período (padrão `-3d`); `--service` identifica o serviço de logs
(padrão Aura). Seleção literal inclui contas internas; aplicar o escopo de farmácias quando a pergunta
exigir essa população. O executor verifica esquemas uma vez por lote, sem chamar Gemini.

O pacote privado `private/bundles/<nome>/` contém `package.json`, `context.json`, `events.json`,
`errors.json`, `backend-logs.json`, `backend-spans.json`, `clip.mp4` e `video-index.json`.
No lote, o nome é `<prefixo>-<session-id>`. O manifesto registra hashes, parâmetros, tempos por etapa
e cobertura. Usar prefixos de até 24 caracteres no lote; uma sessão específica aceita nome de até 61.
Eventos usam paginação por relógio do servidor + UUID e contagem antes/depois; logs usam
cursor e contagem. Traces com `sessionId` são expandidos para filhos, inclusive de outros serviços.
Não atribuir um log a uma sessão só por proximidade temporal.

O MP4 percorre todo o intervalo visual disponível, **incluindo inatividade**, em blocos contínuos de
até cinco minutos, unidos sem reencodar. Os blocos usam o mesmo renderer de `build`, com cache validado.
O renderer lê e verifica o dataset uma vez por lote de blocos. Até dois browsers processam a fila;
cada bloco usa uma página nova, fechada e desconectada do capturador ao terminar. Os browsers são
reutilizados somente durante esse lote e encerrados inclusive após falha. A ordem do vídeo segue os
timestamps, independentemente da ordem de conclusão dos blocos. Não há redução automática de FPS,
corte de inatividade nem mudança de renderer. Uma falha interrompe a fila, aguarda o cleanup dos
blocos ativos e preserva os blocos concluídos/verificados para uma nova tentativa.
Contagem, duração, cadência, decode completo e índice são verificados antes da publicação atômica.
Registrar o intervalo anterior ao primeiro snapshot e a quantização inicial/final de frames; não criar uma
tela fictícia para esses instantes. `prepare` divide os blocos também nos limites da cobertura visual
de cada aba (primeiro snapshot completo até último evento). Uma lacuna entre essas coberturas vira
cartão **Sem gravação disponível**, codificado diretamente por FFmpeg, sem browser ou DOM reutilizado.
Inatividade dentro de uma aba gravada continua no replay normal. O índice marca esses frames com
`visual_state: missing_recording`, `window: recording-gap` e clock declarado, sem hash de captura rrweb.
`coverage.video.recording_gaps`, `gap_duration_s` e `visual_complete: false` expõem os limites: MP4
integral no tempo não significa cobertura visual completa. Eventos de abas reais não são associados
aos cartões. Corrupção, falta de snapshot completo ou falha do renderer continuam interrompendo a
publicação; não são convertidas em cartões. Os blocos reais usam o mesmo renderer PostHog.
O vídeo é amostrado no FPS configurado (padrão 3), não uma cópia de cada estado intermediário do DOM.
O índice guarda o horário observado de cada frame; o primeiro pode chegar até uma cadência depois do
snapshot inicial. Eventos transitórios entre frames podem não aparecer visualmente. Aumentar `--fps`
usa o mesmo pipeline, com outro nome para preservar a evidência já preparada.

`export.json` registra tempos de leitura compartilhada, browsers e cada bloco: preparação do player,
captura, fechamento do encoder, contagem, decode e fechamento da página. Os acumulados
`begin_frame_ms` e `state_read_ms` fazem parte de `capture_ms`; não somá-los como etapas adicionais.
Com dois workers, a soma dos tempos dos blocos também não representa tempo de parede. A preparação
registra separadamente o lote, concatenação e validações do MP4 final. A identidade do cache inclui
o agendador e renderer; nova versão exige outro nome de pacote, preservando os anteriores.

Piloto local de 11/10/2026, mesma sessão de 68min51s, mesmo hash rrweb e 3 FPS: vídeo + validação
passaram de 523,4s para 204,4s (61% menos tempo). Os 12.391 frames mantiveram os mesmos timestamps
e abas do vídeo anterior. Em dois recortes controlados de cinco minutos, um worker levou 64,4s e dois
levaram 41,3s (36% menos); 1.799/1.800 hashes JPEG coincidiram. A diferença restante foi inspecionada
e ficou no placeholder do logo externo em um frame. Não afirmar equivalência visual absoluta.
O pacote da sessão levou 281,8s, sem a descoberta compartilhada; o download também aproveitou cache.
Reuso do pacote completo levou 8,6s no comando, incluindo validação do projeto/sessão, sem renderizar.
São medidas deste piloto/máquina, não SLA nem garantia de aceleração para qualquer gravação.

"Completo" significa fontes disponíveis nos períodos declarados, com propriedades diagnósticas
sanitizadas. Eventos são buscados entre início−1 dia e fim+1 dia, com filtro exato de sessão; logs e
spans usam início/fim expandido pelos eventos retornados, com margem de cinco minutos. Isso não prova
instrumentação integral, ausência de sampling ou captura de logs de plataforma. Fonte indisponível
fica explícita em `coverage` e `telemetry_complete: false`; erros de consulta/paginação não publicam
pacote pronto. Inputs, payloads, headers e variáveis locais não são contexto exportável.

Pacotes prontos com a mesma origem/configuração são verificados por hash e reutilizados sem novo
download/render. São snapshots da coleta, não uma atualização de eventos que chegaram depois;
para nova coleta, escolher novo nome. Preparação concorrente é recusada para proteger o cache compartilhado.
Falhas conservam staging privado e blocos válidos para diagnóstico/reuso. Novas preparações mantêm
`packages-staging/<nome>/checkpoint.json`: dataset, eventos, logs, spans e vídeo só são reutilizados após
conferir configuração e hashes. Repetir `prepare` com o mesmo nome retoma fases concluídas, sem recolher
esse contexto. Mudança de versão/configuração ou corrupção exige nome novo; nada anterior é apagado.
Os stagings antigos sem checkpoint continuam apenas diagnósticos. O lote interrompe no primeiro
erro e registra quantas sessões ficaram prontas, sem apresentar o restante como processado.

Depois: `context.json + clip.mp4 + video-index.json + prompt da tarefa + contexto do problema → Gemini`.
Trocar a pergunta/modelo não exige reconstruir a sessão. `analyze` reutiliza o pacote e salva a
análise separadamente, conforme seção abaixo. `search`, `snapshot`, `annotate` e `ticket` recebem o mesmo nome
do pacote integral; snapshots saem desse MP4.

## Manutenção da captura

`build` é o detalhe interno de captura usado por `prepare`. Comandos diretos servem para testar o
renderer/fixtures; para investigação e análise Gemini, usar o pacote integral de `prepare` e seus
comandos de consulta/snapshot. O contexto próximo de `build` não substitui a coleta completa.

```bash
<skill>/scripts/replay_investigate build --dataset <dataset-preparado> --name <nome-debug> \
  --start <segundos-desde-inicio> --duration 15 --fps 12 --window <aba-numerica>
```

`--start` usa o relógio do cliente, relativo ao início dos snapshots. Para um erro conhecido,
calcular a partir de `$time` × 1000, não do timestamp do servidor. O manifesto preparado guarda
`window_id_map`, que liga `$window_id` à aba numérica. A aba original é preservada no contexto.
`--session` baixa os snapshots e consulta eventos próximos pelo CLI, descobrindo o esquema primeiro;
`--context <json>` permite fornecer contexto já consultado, inclusive logs. Nenhuma propriedade bruta,
header, payload ou valor de input é incluído nesse contexto. A sanitização dos snapshots **não anonimiza
toda informação pessoal/comercial do DOM**, portanto imagens e pacotes continuam privados.

Sessão já preparada: `build --dataset <nome> ...`. Mesmo nome/configuração/fontes/renderer válidos
reutiliza o vídeo; configurações divergentes são recusadas para preservar evidências anteriores.
Lotes fechados de até 21 blocos ficam em cache; a cauda é revalidada isoladamente.
Limites de transporte por sessão: 1.000 blocos e 256 MiB. Reprocessamento ocorre em staging;
falha preserva o dataset e as evidências anteriores. Eventos novos que divergem de pacote publicado
exigem outro nome. Metadados de uma tentativa malsucedida não são apresentados como resultado atual.

Snapshots JSONL já baixados: `build --input /caminho/privado/snapshots.jsonl --name <nome> ...`.
Essa opção alimenta a mesma preparação/captura, sem consultar o serviço; não é outro renderer.

## Investigar

```bash
<skill>/scripts/replay_investigate search <pacote> '500'
<skill>/scripts/replay_investigate context <pacote> <event-id>
<skill>/scripts/replay_investigate snapshot <pacote> --frame <indice>
<skill>/scripts/replay_investigate ticket <pacote> --frame <indice> --title 'Descrição objetiva'
```

O painel `/investigate?bundle=<pacote>&frame=<indice>` oferece busca, contexto, vídeo, avanço de frame,
snapshots e exportação. Iniciar o servidor com a entrada única, em tmux e com nome explícito no portless:

```bash
portless ui.posthog-investigate <skill>/scripts/replay_investigate serve
```

Reportar a URL final do portless e o comando de attach da sessão tmux. O servidor fica em loopback;
não abrir o player rrweb
para cada screenshot. Imagens são extraídas do mesmo vídeo, sem novo download ou renderização.

O índice é observado após cada `beginFrame`, antes do próximo tick. Validar contagem real do encoder,
cadência, aba e decode completo antes de publicar. Não associar lacunas/outra aba ao frame mais próximo.
Associação por request/trace ID é identificada; associação por relógio/aba é aproximada. Não comparar
timestamp do backend ao relógio rrweb sem uma referência de relógio do servidor.

## Conferir a análise Gemini com o agente

1. Buscar eventos relevantes e extrair snapshots antes/durante/depois.
2. Abrir as imagens com a ferramenta de visão; texto do DOM sozinho não demonstra o estado visual.
3. Correlacionar eventos e logs disponíveis. Imagem de erro não confirma perda ou persistência de pedido.
4. Salvar observações locais com referências verificáveis:

```json
[{"observation":"Descrição do que foi observado nas imagens", "hypothesis":"Hipótese ou vazio",
  "frames":[12,24,36], "events":["ctx-0","rrweb-10"]}]
```

```bash
<skill>/scripts/replay_investigate annotate <pacote> --input <json-privado>
```

`prepare` não chama LLM. Pedido de analisar sessões, frustração ou bloqueios inclui `analyze`;
pedido de somente preparar/baixar termina antes dele. O script gera o vídeo, Gemini o avalia e o
agente confere a análise. `agent-browser` serve apenas à inspeção manual adicional do replay.
O agente confere os snapshots citados antes de apresentar a conclusão como validada; o painel e os tickets exibem suas observações e hipóteses com referências.
O ticket ZIP reúne texto, snapshots citados e JSON de evidência com hashes e horários.
Preparar arquivos localmente não publica tickets nem envia imagens a terceiros.

## Analisar com Gemini

Entrada única: `prepare → analyze → conferir snapshots → annotate/ticket`. `analyze` recebe a missão
e, opcionalmente, o contexto do problema em arquivos de texto. Exige um pacote com `package.json`
e hashes válidos; não baixa sessões, não consulta PostHog e não reconstrói o browser.

```bash
infisical run --project-config-dir <config-do-projeto> --env=<ambiente> --path=<pasta-autorizada> -- \
  <skill>/scripts/replay_investigate analyze <pacote> \
  --mission /caminho/missao.txt --problem /caminho/problema.txt --name avaliacao
```

`OPENROUTER_API_KEY` deve ser injetada pelo Infisical; nunca copiar a chave para arquivos ou argumentos.
Usar a configuração do projeto que contém a credencial e confirmar a presença sem imprimir o valor;
Sentinel não fornece `.infisical.json` próprio. Não presumir ambiente/path a partir do nome do projeto.
Configuração verificada em 16/10/2026: `--project-config-dir ~/Projects/painel --env=dev --path=/eve-quote-parser`.
`--problem` é opcional. O default verificado é `google/gemini-3-flash-preview`; `--model` aceita outro
modelo com vídeo, verificando o catálogo público atual antes da primeira chamada paga. Não trocar de
modelo/provider por fallback automático. As duas chamadas preservam o modelo efetivamente retornado,
provider, latência e `usage.cost`. Não inferir custo só da tabela nominal.

O vídeo completo do pacote é usado por padrão. `--start`/`--duration` limitam explicitamente um cenário,
extraindo um recorte do mesmo MP4 a partir dos frames indexados. O manifesto guarda os índices de origem,
hash do input e a quantização. Um recorte não permite concluir sobre toda a sessão. Não remover períodos
inativos nem reduzir FPS automaticamente. O provedor faz sua própria amostragem, que pode perder estados
breves.

Os templates `preamble`, `lookups_step`, `summarizer_summary_step` e macros são snapshots PostHog do
commit `f65db4f579d795aab05b8eb01671e5e2ba6a9d05`, em `prompts/`, com proveniência e hashes. Não precisa
`.state/`, clone OSS ou Pydantic no destino. O adaptador descreve o nosso vídeo sem cortes/rodapé e acrescenta
campos de intenção, fricção, erros, hipóteses e IDs. Confiança declarada pelo modelo não faz parte da saída.
Jinja2 renderiza os templates; jsonschema valida a resposta local. A representação enviada ao Gemini
omite restrições numéricas/limites de listas que tornam o schema nativo complexo; os limites completos
continuam sendo verificados localmente antes da publicação.

Normalmente duas chamadas: vídeo + missão → até oito consultas de eventos/rede locais; mesma conversa, com
`reasoning_details` preservados, + resultados consultados → análise estruturada. Lookups são janelas
numéricas, não SQL livre. IDs desconhecidos, tempos fora do vídeo, capítulos desordenados, erro visual
sem instante/lookup e veredito contraditório impedem publicação. Backend mantém clock separado; um
span com erro não prova que o usuário viu mensagem. O executor preserva contagens de telemetria mesmo
quando o modelo não comenta uma falha. Perda/persistência de pedido e emoção não são conclusões do vídeo.

Artefatos privados em `private/analyses/<nome>/`: `analysis.json`, `analysis-manifest.json`, `report.md`,
contexto consultado, prompts, respostas originais e métricas. A publicação é atômica após validação.
Limitações são aplicadas pelo executor a partir do pacote, independentemente da resposta do modelo.
`status: requires_visual_review` distingue inferência de observação conferida. Referências associam
segundo solicitado, segundo observado, frame, aba, horário de sessão e hash da imagem. Snapshots citados
são extraídos do MP4 em uma decodificação; não são capturas novas do browser.

Mesmo nome/configuração/fontes/prompts/implementação reutiliza a análise validada sem nova chamada;
origem/missão/modelo divergentes exigem outro nome. Corrupção de arquivo ou snapshot é recusada. Após
mudanças de implementação, manter resultados anteriores como evidência da versão usada, com nome novo
para nova execução. Uma chamada ativa impede outra análise simultânea. Cada fase admite **uma correção**
de JSON/schema/referências inválidas, dentro do prazo total da fase, com mesmo modelo/provider e contexto.
São no máximo quatro chamadas; todas as respostas/custos ficam no staging. Recusa, troca de modelo,
erro de transporte ou segunda resposta inválida interrompem a análise; não há fallback.

O contexto inclui navegação da aba efetivamente capturada em cada frame, URLs sem query/fragmento e
descrições comerciais datadas em `event-semantics.json`. Evento desconhecido fica sem definição;
redescobrir semântica se houver divergência. `cart_checkout_started` significa ativação do carrinho,
não tentativa de envio. A meta de capítulos varia de 3 a 20 pela duração, sem afirmar maior acurácia.

Metadados dos plugins `posthog/network@1`/`rrweb/network@1` são coletados durante a mesma decodificação,
antes da exclusão de plugins do player. Guardar até 500 falhas/requisições lentas, sem headers/corpos,
com aba e clock do cliente. Lookups retornam até 20 por janela, associados somente à aba compatível.
O clock usa o início de cada requisição, nunca o horário posterior do envelope em lote; se faltar,
a requisição permanece sem associação a uma tela e sua contagem é explicitada.
Captura ausente, incompleta, status desconhecido e truncamento permanecem explícitos; resultado vazio
nunca comprova rede limpa. Pacotes antigos podem não conter URLs por frame ou rede: informar a lacuna,
sem preencher a partir de outra aba/evento. Nenhum novo download ocorre em `analyze`.

Leituras transitórias PostHog (429/500/502/503/504 e timeout) admitem até três tentativas, com espera e
prazo de 120s por operação, respeitando o prazo da sessão. Acesso negado, corrupção, schema e paginação
inválidos interrompem sem retentativa. O diagnóstico conserva fase, ferramenta, HTTP e exit code;
argumentos e saída bruta não são publicados. Artefatos diagnósticos permanecem privados.

Pilotos de 11/10/2026: recorte negativo de 60s, 8,7s/US$ 0,009661; fixture real positivo de 17s com
HTTP 500 visível, 10,2s/US$ 0,009235; vídeo integral de 68min51s, 47,2s/US$ 0,2982945. São medidas de
inferência, sem download/render. O positivo usa um trecho histórico já capturado com contexto parcial
explicitado; a gravação de origem tem uma lacuna visual e sua preparação integral foi recusada. Não
apresentar o fixture como sessão completa. O vídeo integral recebeu resumo, intenção como hipótese e
fricção possível no modal de cadastro; snapshots desses pontos foram conferidos. Generalizações sobre
recuperação/compra exigiram ressalvas do investigador: um smoke não demonstra acurácia geral.

## Limites

Assets externos bloqueados, animações reduzidas, canvas/mídia não comprovados. Relógio observado na
captura não é garantia de fidelidade absoluta ao browser original. O contexto próximo de `build`
continua limitado a 200 eventos; para sessão inteira, usar `prepare` com paginação e cobertura.
Falhas de captura, fontes alteradas, corrupção ou aba
sem snapshot completo interrompem a publicação. Lacunas comprovadas entre abas têm cartões explícitos,
sem evidência de interface; `analyze` informa os intervalos ao Gemini e recusa citações visuais de erro,
intenção ou fricção em frames desses cartões. Os scripts antigos permanecem como histórico; este é o fluxo
de investigação de vídeo, frames e tickets.
