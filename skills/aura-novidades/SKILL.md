---
name: aura-novidades
description: "Publicar novidades da aitrus (o que chegou a produção no aura e no aura-ui) em novidades.aitrus.com.br, organizadas por mês, a partir do Context (aitrus/novidades): levantar o que entrou na branch prod (contexto do mês), escrever cada novidade em linguagem de farmácia (o que é, por que importa, como ajuda na rotina, como usar, bom saber), gravar o vídeo por passo com o gravador v2 (máscara, guarda de escrita, zoom, legenda, momento de valor), escrever o resumo do mês, conferir no celular e em 1366×768, publicar por pull request no Context (Cloudflare Pages) e registrar. Usar quando Andre pedir para publicar novidades, fechar o mês, atualizar o site de novidades, gerar ou regravar o vídeo de uma novidade, revisar marca ou tom das novidades, ou quando uma mudança com efeito visível ao gestor chegar a produção."
---

# Novidades da aitrus

Site estático `https://novidades.aitrus.com.br`, para o dono da farmácia e o gestor de compras,
organizado por mês. Conteúdo, build, vinheta e sons em `~/Projects/context/aitrus/novidades/`
(raiz configurável por `AURA_NOVIDADES_ROOT`; abaixo, `novidades/`), desde 21/10/2026. A marca vem
de `aitrus/marca/` (manual em `index.html`), lida pelo build, pela vinheta e pelo gravador; nada da
marca é copiado. Fonte do que vira novidade: o que chegou a produção, ou seja, a branch `prod` do
`aura` e do `aura-ui`; a gravação usa os dois rodando localmente. `<skill-dir>` é a pasta deste arquivo. Esta skill
**é** o processo; os scripts em `<skill-dir>/scripts/` são ferramentas.

## Primeira vez aqui? Ler nesta ordem

1. Este arquivo inteiro: regras, decisões vigentes e o ciclo.
2. `novidades/CONVENCOES.md`: o que vira novidade, molde, resumo do mês, estrutura do site, padrão
   do vídeo, com ponteiros para o manual de marca (`aitrus/marca/index.html`: `#voz`,
   `#nao-afirmar`, `#numeros`, `#imagem`, `#checklist`). Ler os dois antes de escrever.
3. `novidades/entradas/2026-09-23-cotacao-por-outro-ean.md` e `novidades/meses/2026-09.md`: uma
   novidade e um mês prontos, no padrão. Calibram tom e profundidade melhor que qualquer regra.
4. `novidades/contexto/2026-09.md`: como é um levantamento de mês.
5. Antes de gravar: `<skill-dir>/referencias/gravador.md`.

## Onde cada coisa mora (sem duplicar)

| Arquivo | Papel |
|---|---|
| `novidades/CONVENCOES.md` | **Regra** do que o leitor vê: texto, tom, marca, site, vídeo, som. |
| `novidades/modelos/` | **Moldes**: `novidade.md`, `mes.md`, `roteiro.yaml`. |
| `novidades/contexto/AAAA-MM.md` | **Levantamento** do mês: temas, tickets, casos reais com fonte, o que ficou de fora. Não é publicado. |
| `novidades/meses/AAAA-MM.md` | Resumo do mês publicado. |
| `novidades/entradas/*.md`, `entradas/roteiros/*.yaml` | Novidades e roteiros de vídeo. |
| `novidades/build.mjs` | Gera o site e **valida** o conteúdo (lista em `CONVENCOES.md`, "O que o build confere"). |
| `novidades/vinheta.json`, `vinheta/vinheta.html`, `som/LICENCA.md` | Parâmetros e desenho da vinheta (de `aitrus/marca/modelos/video-quadros.html`) e licença de cada som. |
| `novidades/areas.json` | Nome de cada área do produto, lido pelo site e pela vinheta. |
| `aitrus/marca/` | Manual, tokens, fontes e logo: fonte única da marca. |
| Este `SKILL.md` | **Execução**: ciclo, comandos, checklists, decisões vigentes. |
| `<skill-dir>/referencias/gravador.md` | Gravador: comandos, campos do roteiro, garantias, conferência do vídeo, aprendizados. |
| Ticket no Linear (`AITRUS-N`) | Liga ticket ↔ novidade (campo `ticket` da entrada). |

| Ferramenta | Para quê | Etapa |
|---|---|---|
| `aura-novidades-pendentes` | commits e tickets desde a última entrada | 1 |
| `aura-novidades-gravar` | gravador v2: roteiro YAML → vídeo, capa, pôster e imagens por passo | 4 |
| `gravador/guarda.js`, `gravador/palco.js`, `mascara.js` | init-scripts da gravação: guarda de escrita, halo e máscara | 4 |
| `aura-novidades-terceiros` → `terceiros.json` | lista de distribuidoras e plataformas mascaradas, gerada de produção; rodar quando entrar distribuidora nova | 4 |
| `video_artifacts.py`, `aura-novidades-vinheta` | cache e render das vinhetas a partir de `vinheta.json` | 4 |
| `aura-novidades-capturar` | tela avulsa mascarada, só para novidade sem vídeo | 4 |
| `aura-novidades-conferir` | build + worker `visual-inspection` em 390×844 e 1366×768 | 7 |

## Regras que não se negociam

- Leitor: o dono da farmácia e o gestor de compras, lendo no celular. Sem jargão de sistema, versão
  ou ticket no texto.
- Toda afirmação é conferida no código **e** na tela atuais. Entrada, imagem ou roteiro antigo não é
  prova de nada. Número de caso real só com fonte registrada no `contexto/`.
- Nunca expor loja, CNPJ, grupo econômico, usuário, cliente, representante, distribuidora ou
  plataforma de integração reais em texto, tela, vídeo, capa ou imagem (manual, `#imagem`). Tela e
  vídeo só com a máscara aplicada (inclui `terceiros.json`) e `restos: []`.
- Nunca gravar no Aura durante a captura: a guarda de escrita barra e reprova a tomada. Salvar,
  Aplicar, bloquear, adicionar ao carrinho e enviar pedido recebem, no máximo, o ponteiro.
- Nunca finalizar ou enviar pedido, nem em teste. Carrinho real é só leitura.
- Tela cujo GET tem efeito colateral não é aberta para gravar sem decisão do Andre (Cotações
  Externas: autorizada na Vovó em 23/09/2026, conferindo antes que "Lendo" está zerado).
- Marca, vinheta, trilha e logo sonoro são um só padrão; mudança de marca vai para o manual
  (`aitrus/marca/`), por pull request, com OK do Andre.
- Publicar = merge na `main` do Context. Branch e pull request sem pedir; merge só com OK do Andre.

## Decisões vigentes

Valem até o Andre mudar; ao mudar, atualizar aqui (com a data) e, se for regra de conteúdo, em
`CONVENCOES.md`.

| Tema | Decisão |
|---|---|
| Gatilho (24/09/2026) | Só o que muda o uso ou o valor para a farmácia vira novidade; infraestrutura, desempenho, refatoração e correção que só devolve o esperado não viram. Ajustes pequenos do mesmo assunto viram uma novidade por tema (tela ou tarefa do leitor). |
| Agregação (24/09/2026) | Por **mês**: levantamento em `contexto/AAAA-MM.md`, resumo publicado em `meses/AAAA-MM.md` (chamada, panorama de 120–220 palavras, 3–5 destaques). Dentro do mês, as novidades ficam por dia. Sem edição semanal. |
| Página principal (24/09/2026) | Desenho **E**: trilho vertical de meses, compacto. Mês mais recente aberto (chamada, 1º parágrafo, títulos dos destaques, link para o mês); anteriores em duas linhas; clique leva à página do mês (panorama, destaques, dia a dia). Chamada e 1º parágrafo sem rolar em 1366×768 e no celular. |
| Profundidade (24/09/2026) | Cada novidade explica o que é, por que importa e como ajuda na rotina, antes do "Como usar". Até 300 palavras. |
| Tom | Profissional e direto, não formal. Título com verbo e ganho; exemplo real em R$ ou unidades quando ajudar; no máximo uma ressalva por ideia. Página da novidade no presente; resumo do mês é notícia. |
| Marca (21/10/2026) | 100% o manual de marca (`aitrus/marca/index.html`), logo 1.1. Nome público "aitrus", sempre minúsculo; "Aura" nunca no que vai ao ar (o build recusa). Site, vinheta, capa e gravador leem tokens, fontes e logo de `aitrus/marca/`. Violeta só dentro da tela capturada do produto. |
| Vídeo | Obrigatório quando há gesto na tela; opcional para regra, cálculo ou texto. Termina no **momento de valor**. |
| Duração | Até 45 s. Abertura 4,5 s: logo animado do manual (2 s) + quadro com o título (2,5 s); encerramento 3 s, parado (manual, `modelos/video-quadros.html`). Cada passo abre com a tela parada 0,8–1,6 s; esperas encurtadas. |
| Clique (23/09/2026) | Todo clique visível: repouso de 0,35 s com halo, quadro congelado 1 s, anel no ponto. ~1,4 s por clique: roteiro enxuto. |
| Capa | Quadro 0 do MP4 = capa = quadro "Miniatura" do manual com o título (último quadro da abertura), também a prévia do link da novidade. Pôster do player = tela final. Legenda do passo: "texto na tela" do manual, mínimo 33 px em 900 de altura. |
| Terceiros (21/10/2026) | Distribuidoras e plataformas de integração viram "Distribuidora A, B…" e "Plataforma A…" (manual, `#imagem`); lista em `terceiros.json`, gerada de produção. |
| Medição | PostHog, projeto `aura`, via `b.aitrus.com.br`, só em `novidades.aitrus.com.br`: sem cookies, gravação ou autocaptura; `$pageview`, `novidade_video_play`, `novidade_video_fim` (`app: novidades`). |
| Aprovação | O Andre aprova o primeiro vídeo de cada tela nova (rota nunca gravada) e todo desenho novo do site; o resto segue pelos checklists. |
| Dados | Loja padrão: Drogarias da Vovó (`05101867000157`). Outra loja só quando o caso real exige, sempre mascarada. O roteiro só usa o que existe na loja hoje. |
| Peso (21/10/2026) | Vídeos e imagens no Git do Context; rever com o Andre quando o pack do Context passar de ~300 MB. |
| Publicação (21/10/2026) | **Pendente de OK do Andre.** Planejado: Cloudflare Pages ligado ao Context (merge na `main` que toca `aitrus/novidades/` ou `aitrus/marca/` publica; prévia por branch). Até lá, o site no ar é a versão antiga, na Vercel (`aura-novidades`), e nada novo é publicado. |
| Formatos | Só o MP4 1440×900 do site; 9:16 para redes fica para decisão futura. |

## Quando rodar

- **Mudança com efeito visível ao gestor chegou a produção**: no mesmo dia, etapas 1 a 9 para a
  novidade (ou atualizar a novidade do tema, se já existir) e atualizar o resumo do mês corrente.
- **Andre pede "publicar novidades" ou "atualizar o site"**: etapa 1 desde a última entrada, depois
  o ciclo.
- **Virada do mês**: fechar o resumo do mês anterior (etapa 6) com o panorama no passado e os
  destaques definitivos.
- **Regravar um vídeo**: etapas 4, 5, 7, 8 (a entrada não muda; se "Como usar" mudar, a legenda
  muda junto).

## O ciclo

### 0. Antes de começar

- `aura` e `aura-ui` locais no ar, a partir da `origin/prod`, e token funcionando (ver
  `referencias/gravador.md`, "Pré-requisitos").
- No Context: branch nova a partir da `origin/main` (worktree, se a checkout principal estiver em
  uso) e `git status` em `aitrus/novidades/` antes de mexer.

### 1. Levantar o mês

```bash
<skill-dir>/scripts/aura-novidades-pendentes                                   # desde a última entrada
<skill-dir>/scripts/aura-novidades-pendentes AAAA-MM-01                        # o mês inteiro
```

Criar ou atualizar `contexto/AAAA-MM.md` (modelo: `contexto/2026-09.md`):

1. Ler o que entrou na `prod` no mês e os tickets do Linear. Separar o que muda o uso ou o valor para a farmácia
   do que fica de fora (infraestrutura, desempenho, correção que só devolve o esperado, trabalho em
   andamento); listar o que ficou de fora e o motivo.
2. Agrupar por **tema do leitor** (tela ou tarefa), não por ticket. Cada tema vira uma novidade.
3. Por tema: tickets, commits, dia em que ficou disponível, a dor que resolve e casos reais com
   número e **fonte** (mensagem do cliente, consulta, tela).
4. Sugerir 3–5 destaques em ordem de impacto para o dono da farmácia.

Para cada tema que vai virar novidade: ler o diff e o código do front e do back. Mapear rota, nomes
reais dos controles, chamadas de API (quais POSTs só leem, quais gravam, se algum GET tem efeito
colateral), dados necessários e a loja onde eles existem hoje. Decidir se leva vídeo.

### 2. Escrever a novidade

Copiar `modelos/novidade.md` para `entradas/AAAA-MM-DD-slug.md` (a data é o dia em que ficou
disponível em produção). O que cada seção entrega está na tabela do molde em `CONVENCOES.md`.

Como redigir:

1. Partir da dor do leitor (o que ele não conseguia fazer ou arriscava errar) e do ganho; nunca do
   diff ou do nome do componente.
2. "O que é" diz **o quê**; "Por que importa" responde "e daí?" em dinheiro, tempo, erro evitado ou
   algo que não se via; "Como ajuda na rotina" diz **quando e para quê**; "Como usar" diz **como**.
   Uma não repete a outra.
3. "Como usar": cada passo é a legenda de um trecho do vídeo — demonstrável, na ordem do gesto, até
   ~120 caracteres. Passo que a tela não mostra vai para "Bom saber".
4. Nomes de tela, botão, aba e campo exatamente como no Aura, em negrito, conferidos no código.
5. Número real só do `contexto/`, com fonte; sem caso real, descrever a situação sem inventar.
6. Página da novidade no presente: sem "agora", "passou a", "antes".

Checklist da novidade (tudo sim antes de gravar):

- [ ] Muda o uso ou o valor para a farmácia (Parte 0)? Não é ajuste que cabe numa novidade existente?
- [ ] Título com verbo e ganho, ≤ 80; resumo ≠ título, ≤ 200.
- [ ] `menu` é o caminho real, conferido na tela.
- [ ] O que é (2–4 frases), Por que importa (2–4), Como ajuda na rotina (2–3 itens "**Ao …**"),
      Como usar (2–5 passos), Bom saber (≤ 2 frases, opcional); ≤ 300 palavras.
- [ ] Cada afirmação conferida no código e na tela; número real com fonte no `contexto/`.
- [ ] Voz e vocabulário do manual (`#voz`) e a tabela do `CONVENCOES.md` (distribuidora, código de
      barras, suas lojas); sem ticket, versão, "hipotético", nome de cliente, distribuidora ou
      plataforma; número de exemplo marcado; sem símbolo que a DM Sans não tem (⠿, emoji) nos passos.
- [ ] `pnpm build` sem erro nem aviso.

### 3. Roteiro do vídeo

Copiar `modelos/roteiro.yaml` para `entradas/roteiros/<slug>.yaml`. Antes de qualquer passo,
preencher `# valor:` com a frase da tela que prova o "Por que importa". Se não houver momento de
valor visível, a novidade vai sem vídeo (etapa 4, "Novidade sem vídeo").

Checklist do roteiro:

- [ ] Um passo por item de "Como usar", na mesma ordem.
- [ ] `origem` fora da tela final; primeiro gesto é o caminho real (menu ou controle global).
- [ ] Último passo termina no momento de valor, com `foco` justo, `zoom` e `pausa` longa.
- [ ] Cada POST em `leituras` conferido no controller como leitura; nenhuma escrita declarada.
- [ ] Cenário existe hoje na loja escolhida (conferir na véspera quando depender de carrinho).
- [ ] Sem gesto que não mostra nada; `pronto` é o estado carregado.

Campos, verbos e armadilhas: `referencias/gravador.md`.

### 4. Gravar

```bash
<skill-dir>/scripts/aura-novidades-gravar <slug>
```

Uma captura por vez, sem nada pesado rodando. Reprovação informa "passo N, ação X" ou "passo N,
pronto"; diagnosticar pelo `referencias/gravador.md`. Ligar `imagem`, `legenda` e `video` na
entrada. Novidade sem vídeo: tela avulsa com `aura-novidades-capturar` (mesma referência).

### 5. Conferir o vídeo

Abrir a folha de contato da tomada e 2–3 quadros em resolução cheia e passar o checklist de
`referencias/gravador.md`, "Conferir o vídeo" (legenda, caminho real, zoom, máscara, nada salvo,
cliques visíveis, capa e encerramento, momento de valor). Primeiro vídeo de tela nova: mostrar ao
Andre antes de seguir. No máximo duas regravações; sem convergência, parar e relatar a causa.

### 6. Escrever ou atualizar o resumo do mês

Copiar `modelos/mes.md` para `meses/AAAA-MM.md` na primeira novidade do mês; atualizar a cada
novidade nova; fechar na virada do mês. Fonte: `contexto/AAAA-MM.md` e as novidades do mês.

Checklist do mês:

- [ ] Chamada: uma frase de ganho, ≤ 140, nunca lista de títulos.
- [ ] 1º parágrafo do panorama se sustenta sozinho (é o que aparece na página principal).
- [ ] Panorama 120–220 palavras, temas ligados à rotina, nomes de tela em negrito; o 3º parágrafo
      fala de quem tem mais de uma loja, quando couber.
- [ ] 3–5 destaques, em ordem de impacto, cada um `- **Título curto**: por que importa`, título
      curto até ~45 caracteres.
- [ ] Nenhum número sem fonte, ticket, nome técnico ou promessa de prazo; o panorama não repete os
      destaques, dá o sentido do conjunto.
- [ ] Mês aberto fala só do que já chegou.

### 7. Conferir o site

```bash
cd ~/Projects/context/aitrus/novidades && pnpm build
# servir em tmux (sessão com o nome da pasta do Context): portless ui.novidades.context npx --yes serve dist
<skill-dir>/scripts/aura-novidades-conferir https://ui.novidades.context.localhost
```

Informar o `tmux attach -t <sessão>` e a URL. O worker `visual-inspection` confere a página principal,
o mês mais recente, a novidade mais recente e uma com vídeo em 390×844 e 1366×768: linha do tempo
compacta, chamada e 1º parágrafo sem rolar, sem rolagem horizontal, texto sem corte, vídeo tocando,
imagens de passo ampliáveis, links antigos redirecionando. O principal abre as evidências. Escopo
grande: dividir em inspeções menores. Mudança no `build.mjs`: rodar também `autoreview` antes.

### 8. Commit e publicação

Commitar na branch do Context (`feat(novidades): …`), com `entradas/`, `meses/`, `contexto/`,
`img/`, `video/`, `roteiros/`, e abrir o pull request. Quando o Pages existir (ver "Publicação" nas
decisões): conferir a prévia `https://<branch>.aitrus-novidades.pages.dev` (barras viram hífens) e,
com OK do Andre, fazer o merge na `main`, que publica em ~1 min. Depois, conferir no ar que a home, o mês e cada novidade nova
respondem 200 em `https://novidades.aitrus.com.br`. Mudanças da skill vão para
`~/Projects/agent-scripts`, em branch e commit separados.

### 9. Registrar

- O link para o cliente é a página principal (o mês) ou, para uma novidade só, a página dela.
- Linear: o ticket recebe o link da novidade publicada.
- `contexto/AAAA-MM.md`: marcar o tema como publicado, com o slug.
- Critério novo, decisão nova ou armadilha nova: registrar aqui (decisões) ou em
  `referencias/gravador.md` (aprendizados).
- Em lote: relatar por novidade o que mudou no texto, a loja usada, a duração do vídeo, as leituras
  declaradas e as pendências.

## Pendências conhecidas (24/09/2026)

- Vídeos de `2026-08-24-loop-de-backup` e `2026-08-31-estoque-do-grupo-no-carrinho` na versão
  anterior do gravador: os carrinhos das lojas estavam vazios.
- Avaliar com o Andre juntar as duas novidades de embalagem e as duas de Gestão do Catálogo num
  tema cada (Parte 0).
- Setembro tem temas levantados em `contexto/2026-09.md` ainda sem novidade (carrinho, Mix com
  expansão e busca tolerante, cotações externas em volume, ofertas e campanhas, análise de vendas,
  dados atrasados, cadastro da equipe).
