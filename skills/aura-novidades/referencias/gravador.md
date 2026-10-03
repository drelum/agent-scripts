# Gravador v2 — referência

Ler quando for escrever ou depurar um roteiro, regravar um vídeo ou entender uma reprovação do
gravador. O **padrão do vídeo** (o que o leitor vê) está em `novidades/CONVENCOES.md`, Parte 4; a
**ordem das etapas**, no `SKILL.md`. Aqui ficam os comandos, os campos do roteiro, o que o gravador
garante e os aprendizados de gravação.

## Pré-requisitos

- API e UI Beta no ar (`https://api.beta.aura.localhost`, `https://ui.beta.aura.localhost`; subida
  no `AGENTS.md` da raiz do monorepo: Cloud SQL Auth Proxy, `aura-beta`, `aura-ui-beta` em tmux) e
  `./scripts/beta-api-token.sh` devolvendo token. Depois de reboot, tudo precisa subir de novo.
- `agent-browser` ≥ 0.38 (`record --cursor`, `click --human`, `--init-script`), `ffmpeg`,
  `ffprobe`, Node ≥ 24, `python3` com Pillow e PyYAML, fonte DM Sans em
  `~/.cache/aura-novidades/DMSans.ttf` (Google Fonts, `ofl/dmsans`).
- `vinheta.json` válido e cada som com linha em `som/LICENCA.md`.
- Nada pesado rodando na máquina (outro navegador, ffmpeg, build grande): o codificador fica para
  trás e a tomada sai com quadros perdidos.

## Comandos

```bash
<skill-dir>/scripts/aura-novidades-gravar <slug>                 # captura + montagem + publicação da mídia
<skill-dir>/scripts/aura-novidades-gravar <slug> --capturar      # só a tomada validada, em /tmp
<skill-dir>/scripts/aura-novidades-gravar <slug> --compor <dir>  # remonta uma tomada (recusa se entrada, roteiro ou máscara mudaram)
```

Variáveis de ambiente (padrões entre parênteses): `AURA_BETA_ROOT` (`~/Projects/beta`), `NOV_UI`,
`NOV_API`, `NOV_FONTE`, `NOV_ESCALA` (1,5; 2 faz o codificador atrasar), `NOV_LIMITE_S` (45; só para
vídeo avulso), `NOV_CONGELA_CLIQUE` (1,0 s), `AGENT_BROWSER_ARGS` (ex.: `--lang=pt-BR` para campos
nativos de mês e data em português).

Uma captura por vez na máquina (trava em `/tmp/aura-novidades-gravar.lock`). `/tmp` é limpo no
reboot: tomadas antigas somem e `--compor` deixa de ser possível.

## O roteiro (`entradas/roteiros/<slug>.yaml`)

Copiar de `novidades/modelos/roteiro.yaml`. Um passo por item de "Como usar", na mesma ordem; a
legenda de cada passo vem da entrada (o gravador recusa se o número de passos divergir).

| Campo | Para quê |
|---|---|
| `# valor:` (comentário no topo) | O **momento de valor**: a frase da tela que prova o "Por que importa". O último passo termina nele. |
| `loja` | CNPJ real da loja gravada (sempre mascarado na tela). Padrão: Drogarias da Vovó. |
| `origem` | Rota aberta antes do primeiro gesto; a demonstração começa fora da tela final. |
| `leituras` | Regex dos POSTs que só leem. **Conferir no controller do backend antes de declarar**; nunca declarar escrita. |
| `simulacoes` | Respostas fictícias para uma escrita demonstrada (opcional); `eco: true` devolve o corpo enviado mesclado a `corpo`, para a tela ficar "salva" com o que foi digitado. |
| `mascara_extra` | JSON `{pares, notas}` ao lado do roteiro, para demonstrações com muitos nomes reais; `notas: true` zera números de nota isolados. Nunca commitar esse arquivo. |
| `preparar` | Ações antes da gravação (não aparecem no vídeo). |
| `passos[].acoes` | Lista de verbos (abaixo). |
| `passos[].pronto` | O estado final **carregado** do passo: `texto`, `seletor` ou `fn`. |
| `passos[].foco` | Seletor ou lista; a união recebe o zoom. |
| `passos[].pausa` | Milissegundos parados no fim do passo. |
| `passos[].zoom` | Zoom máximo (padrão 2). |

Verbos: `menu`, `clicar`, `clicar_css`, `clicar_se`, `digitar`, `digitar_css`, `direito`,
`direito_css`, `clicar_texto`, `rolar_ate`, `apontar`, `apontar_css`, `esperar_texto`,
`esperar_fn`, `esperar`, `tecla`.

POSTs de leitura que quase toda tela chama e precisam estar em `leituras`: `quote/distributors`
(`/canonical`), `integration/distributor-health`, `integration/sync-health/query`,
`order/transit/query`, `product/assortment/query`, `order/recent-activity/query`, `quote` (v1 e v2).
Bloqueados, quebram o carregamento e a espera estoura sem mensagem clara.

## O que o gravador garante (e reprova a tomada se falhar)

- Sessão própria do `agent-browser` com `--allowed-domains` e três init-scripts em todo documento:
  máscara (`mascara.js`), guarda de escrita (`gravador/guarda.js`) e palco com halo e anel
  (`gravador/palco.js`).
- `restos: []` da máscara no início, a cada passo e no fim.
- Nenhuma escrita bloqueada pela guarda nem vista na rede (`network requests --method`).
- Um clipe por passo com `record --cursor` e cliques `--human`; alvo visível escolhido e remira se
  ele se mover durante o trajeto do ponteiro.
- Clique visível: ponteiro chega em 650 ms, repousa 0,35 s com halo, e a montagem congela 1 s o
  quadro do clique.
- Esperas acima de 1,2 s cortadas (mantém 0,4 s nas pontas); ação lenta acima de 2 s mantém só os
  últimos 1,6 s.
- Zoom suave no foco depois do "pronto"; tela parada no início do passo por 0,8–1,6 s, conforme o
  tamanho da legenda; legenda numerada numa faixa abaixo da tela (Pillow + DM Sans).
- Vinhetas de `vinheta.json` (abertura 5 s, encerramento 4 s), trilha e logo sonoro; capa no
  quadro 0; duração até `NOV_LIMITE_S`.
- Mídia gerada e validada numa área temporária antes de substituir, de uma vez, os arquivos
  publicados.
- Falha informa "passo N, ação X" ou "passo N, pronto": começar o diagnóstico por aí.

Saídas: `entradas/video/<slug>.mp4`, `entradas/img/<slug>.png` (pôster = tela final),
`entradas/img/<slug>-capa.png` (prévia do link) e `entradas/img/<slug>-passo-N.png` (recorte do foco
de cada passo). A tomada fica em `/tmp/…` com `folha.jpg` (folha de contato).

## Conferir o vídeo

Sobre a folha de contato (`folha.jpg`) e 2–3 quadros em resolução cheia:

1. Legenda certa em cada passo e igual ao texto atual de "Como usar".
2. Primeiro gesto é o caminho real (menu ou controle global); a tela final não aparece antes.
3. Zoom legível onde o foco é pequeno; nenhuma imagem de passo com "carregando", esqueleto ou
   "Cotando…".
4. Máscara: "Farmácia Modelo", CNPJ zerado, "Grupo Modelo"/"Modelo", iniciais "GL"; nenhum
   representante ou pessoa real; telefones zerados.
5. Nada salvo: o ponteiro pode passar por Salvar/Aplicar, nunca clicar.
6. Todo clique visível (parada de 1 s e anel).
7. Capa no início, encerramento com o endereço do site legível, duração dentro do limite.
8. Momento de valor: o último passo mostra, com zoom e legível, o que diz o `# valor:`.

Máximo de duas regravações por novidade; sem convergência, parar e relatar a causa.

## Aprendizados de gravação

- `pronto` é o estado **carregado**, não a presença do controle: no carrinho, esperar sumir
  "Cotando os itens"; no Mix, a linha aparece antes das ofertas.
- Foco largo (tabela inteira, janela larga) anula o zoom; mirar a região que o passo explica.
- Preços vêm com espaço não separável: `esperar_texto` com "R$ 0,58" não bate; esperar o número.
- `click --human` não resolve seletor com `:has()`; `get box` e cliques aceitam XPath só com o
  prefixo `xpath=`. Preferir nome acessível (`clicar`) ou CSS simples.
- Em página pesada, `snapshot -i` e `--human` levam segundos; o gravador corta ação lenta, mas
  roteiro enxuto (menos ações por passo) rende vídeo melhor.
- Menu de contexto (botão direito) precisa de espera antes e depois do gesto.
- O menu lateral recolhe ao abrir o Mix; o clique no item acontece com ele aberto.
- A máscara troca todo CNPJ pelo mesmo zerado: lojas diferentes ficam iguais na tela.
- Máquina reiniciada derruba proxy, API e UI; o token falha antes de qualquer gravação.
- A interface muda de texto sem aviso (a busca do Mix virou "Nome, fabricante, EAN, molécula…"):
  nomear controles por um trecho estável (`'EAN, molécula'`), não pelo texto inteiro.
- Não usar `clicar_se` para gesto que a legenda promete: se o alvo sumiu (distribuidor que deixou de
  cotar), ele pula em silêncio e o passo seguinte estoura o tempo. Preferir alvo estrutural
  (`[role=dialog] button[aria-haspopup=menu]`) a nome de dado.
- Telas repetem controles ocultos (dois "Nova cotação externa"); o gravador escolhe o visível e
  remira se o alvo se mover. Ainda assim, esperar a lista carregar (`esperar_texto` de um
  cabeçalho) antes de clicar em página que muda de layout.
- A busca do Mix é tolerante a erro e casa cada palavra (23/09/2026): buscar por nome pode trazer
  vários produtos. Para um produto específico, buscar pelo código de barras, que continua exato.
- Mudança só de montagem (vinheta, cores) exige nova captura depois de um reboot.
- Não rodar nada pesado durante uma gravação: o codificador fica para trás.
- Carrinho e dados reais mudam: o carrinho da Itufarma esvaziou depois do pedido do comprador.
  Conferir o cenário na véspera; sem dados, manter o vídeo anterior e registrar a pendência.
- A máscara cobre representantes conhecidos e qualquer telefone; nome novo de representante ou
  pessoa entra em `ALVOS` de `mascara.js` antes de gravar (a mudança invalida tomadas anteriores).
- Cotações Externas: abrir a lista retoma importações "recebidas" ou "em análise"; conferir antes
  que "Lendo" está zerado.

## Novidade sem vídeo

Só texto, ou uma tela avulsa mascarada:

```bash
source <skill-dir>/scripts/aura-novidades-capturar
nov_login /rota && nov_shot ~/Projects/beta/novidades/entradas/img/<slug>.png && nov_fim
```

## Vinheta

`vinheta.json` define conceito, textos, cores, duração e som; modelo em `vinheta/`, simulador em
`https://ui.vinheta.localhost` (`portless ui.vinheta node novidades/vinheta/servidor.mjs`). O
gravador renderiza e guarda em cache (`video_artifacts.py`, `aura-novidades-vinheta`). Mudança passa
pelo simulador e pelo OK do Andre. Chave do ElevenLabs (plano Starter da Aitrus, licença comercial)
no Infisical (`Aitrus Apps` · `staging` · `/shared` · `ELEVENLABS_API_KEY`), usada só via
`infisical run`, nunca impressa.
