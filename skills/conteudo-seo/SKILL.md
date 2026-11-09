---
name: conteudo-seo
description: "Criar ou revisar uma página de conteúdo do site da aitrus (~/Projects/website) — guia, página comercial ou revisão — sempre com o Astra (Codex gpt-6-astra) e dados do DataForSEO: pauta, pesquisa, texto, conferência, implementação, revisão, inspeção visual, gate, publicação e registro. Usar para novo guia, nova página de solução ou revisão de página do site."
---

# Conteúdo SEO do site da aitrus

Processo dos guias de 06–09/11/2026 (curva ABC, CMED, intercambiáveis, ruptura, PBM) e da página de cotação. Repositório: `~/Projects/website`. Claude é o editor: decide com o André, confere e implementa. O Astra pesquisa, escreve e revisa, só com leitura. O André escolhe a pauta, libera afirmações novas sobre a aitrus e dá o OK de publicação.

Antes de começar, no website: `AGENTS.md`; `docs/guias-de-conteudo.md` ("Como cada guia é feito", "Padrões comuns" e o registro do guia mais parecido: 6 PBM para guia, 7 cotação para página comercial); `docs/seo-pautas.md` ("Cuidados de leitura" e a seção do tema). Esta skill resume; os docs mandam se divergirem.

## Quando usar

- Guia novo (busca informativa: reputação com a visão do dono da farmácia).
- Página comercial (busca de quem quer a ferramenta: guia + solução amarrados à aitrus).
- Revisão de página existente (pular para as etapas 4, 6, 7 e 8).

## Etapas

### 1. Pauta com dados
- **Entra:** tema ou pedido do André.
- **Faz:** ler `docs/seo-pautas.md`; skill `dataforseo-seo`: volume (com e sem acento, plural), autocompletar, SERP `live/advanced` desktop com "As pessoas também perguntam" e Visão geral de IA, concorrentes pelo `breadcrumb`. Ler a primeira página antes de concluir a intenção (consumidor, estudante e hematologia contaminam).
- **Sai:** tabela termo · volume · primeira página; intenção; endereço candidato; formato (guia ou comercial). Respostas brutas no scratchpad.
- Temas só de farmácia ranqueiam mais rápido que genéricos (08–09/11: "tabela cmed" 5º, "ruptura de estoque farmácia" 10º, "medicamentos intercambiáveis" 11º um dia após indexar; "ruptura de estoque", "curva abc" e "sistema para farmácia" fora das 30). Preferir o recorte da farmácia no termo e no título.

### 2. Astra 1a: pesquisa
- **Entra:** pedido modelo 1 (`references/modelos-de-pedido.md`) com a tabela da etapa 1, o pedido do André e o que é permitido sobre a aitrus.
- **Sai:** fatos com link e data ("a confirmar" sem fonte primária); 4 a 7 páginas da concorrência (tipo, data, o que falta ao dono); boas práticas do Google Search Central; até 15 recomendações e perguntas para o André.
- Claude leva ao André as decisões abertas (endereço, nomes liberados, vetos) antes da 1b.

### 3. Astra 1b: estratégia e texto completo
- **Entra:** pedido modelo 2, apontando para a saída da 1a, com as decisões já tomadas.
- **Sai:** estratégia (título ≤ 60, descrição ≤ 155, H1, sumário com `id`), texto com blocos `[TABELA]`/`[QUADRO]`/`[DIAGRAMA]`, 5 a 7 dúvidas, textos de ligação de outras páginas, parágrafos "[DEPENDE DO OK DO ANDRÉ]" e lista de conferência.

### 4. Claude confere (antes de implementar)
- **Afirmações sobre a aitrus:** cada uma contra `index.html` (trechos com `rg -n`) e o manual (`sed -n 590,600p /home/drelu/Projects/context/aitrus/marca/index.html | sed 's/<[^>]*>/ /g'`, "o que não afirmar"). Fora do publicado → pergunta ao André (ex.: custo médio, análise de PBM no Aura).
- **Contas:** refazer todas, inclusive arredondamento e "antes de tributos e taxas".
- **Links:** abrir cada externo (`curl -sL -o /dev/null -w '%{http_code} %{url_effective}\n' <url>`): 200, sem laço de redirecionamento (a página da CAIXA do Farmácia Popular entrava em laço). Só fontes oficiais; conferir na fonte o trecho citado.
- **Normas:** órgão, número, artigo, data e alcance (orientação estadual não vira regra nacional).
- **Tom:** tirar frases de relatório ("a pesquisa não confirmou…"); escrever como orientação ao dono.
- **Sai:** lista "mudanças de Claude, já decididas", que vai no pedido da etapa 6.

### 5. Implementação
Copiar estrutura e componentes do modelo mais parecido (`pbm-farmacia.html` guia; `cotacao-para-farmacia.html` comercial) e `src/guia.css`. Gráfico em SVG estático; diagrama em HTML quando o texto precisa ficar legível no celular.

Checklist de registro:
- [ ] `vite.config.ts`: entrada `"<slug>": "<slug>.html"`.
- [ ] `public/sitemap.xml`: `<url><loc>https://aitrus.com.br/<slug></loc></url>`.
- [ ] `public/_redirects`, 2 linhas: `/<slug>.html /<slug> 301` e `/<slug>/ /<slug> 301`.
- [ ] Índice do rodapé igual em **todas** as páginas: guia no grupo "Guias", comercial em "Produto".
- [ ] Ligações internas a partir das páginas relacionadas (textos de ligação da 1b).
- [ ] `<p class="abertura-apoio">` com até 35 palavras e duas frases; `<p class="guia-autoria">` sem "Fontes"; "Fontes conferidas em …" na nota `.guia-revisao` no fim.
- [ ] "O que é…?" com 35 a 50 palavras, começando pelo assunto, sem a aitrus; a tarefa do H1 logo depois; uma seção só sobre a aitrus.
- [ ] Dúvidas dentro de `#duvidas`: o `FAQPage` é gerado no build (não escrever à mão).
- [ ] JSON-LD: guia `Article` + `BreadcrumbList`, `og:type` `article`; página comercial só `BreadcrumbList`, `og:type` `website`, **nada de `Article`**.
- [ ] `R$&nbsp;<valor>`; `&nbsp;` também em "distribuidora&nbsp;1", "laboratório&nbsp;1", "farmácia&nbsp;2".
- [ ] Tabelas `compacta` (2–3 colunas) ou `empilhada` com `data-rotulo` (4+); cabeçalhos de linha; sem link dentro de `th`.
- [ ] Externos com `rel="noopener"`; exemplos com "ilustração · valores de exemplo".

`src/paginas.test.ts` barra: canônico fora do sitemap, falta de redirecionamento permanente, primeiro foco sem "Pular para o conteúdo", medição fora de `main.ts`/`pagina.ts`/`quem-somos.ts`, rodapé divergente ou com link quebrado, abertura acima de 35 palavras, "Fontes" na autoria.

### 6. Astra 2: revisão da página implementada
- **Entra:** pedido modelo 3, com a lista da etapa 4 marcada "não reabrir" e o diff das ligações.
- **Sai:** problemas do mais grave ao menos grave (trecho, correção pronta, motivo) e veredito. Claude aplica, recusa com motivo ou leva ao André.
- **Opcional, Astra 3 (segunda opinião):** pedido modelo 4, como consultor externo, **sem** passar a revisão anterior nem as conclusões de Claude. Separar o que o André aceita, recusa e adia; registrar (cotação: título trocado, seções enxutas, captura real da tela adiada).

### 7. Inspeção visual
Servidor do projeto em tmux: sessão `website`, `portless ui.website npm run dev`; informar `tmux attach -t website` e a URL. Skill `visual-inspection` (worker com agent-browser) ou agent-browser direto: `set viewport 1366 768` e `set device "iPhone 16 Pro"`. Conferir abertura, sumário (fixo no computador, `<details>` no celular), tabelas, figura, quebras de `R$`, formulário e rodapé.

### 8. Gate, commit, publicação e registro
- Gate uma vez, no estado final: `FULL_SUITE=1 VITEST_MAX_WORKERS=3 npm run gate` (tipos + `vp check`, testes, Knip, build). Sem `--quiet`, sem desligar regra.
- Commit local na `main` do website (permitido pelo `AGENTS.md` do site), Conventional Commits em português: `feat: página de <tema>`, `docs: …`.
- **Push só com OK explícito do André, a cada vez:** `git push origin main` e `git push origin main:prod` (a Cloudflare builda a `prod`). Depois: `curl -sI https://aitrus.com.br/<slug>` (200).
- Search Console: inspeção da URL e "Solicitar indexação" no Chrome do Windows, perfil `aitrus` (skill `windows-chrome-browser`).
- Registrar no website: `docs/guias-de-conteudo.md` (seção nova: origem, busca, formato, processo, diferencial, decisões do André, nomes e links, ligações) e `docs/seo-pautas.md` (tema publicado, indexação pedida, data). Commit `docs:`; o push segue a mesma regra.

## Como chamar o Astra

```bash
A=~/.claude/skills/conteudo-seo/scripts/astra.sh
"$A" <pasta-astra>/<tema>-1a-pesquisa.md <pasta-astra>/<tema>-1a-pesquisa.saida.md   # esforço high
```
- `-C <repo>` ou `ASTRA_REPO` para outra raiz (padrão `/home/drelu/Projects/website`). Esforço `high` (terceiro argumento).
- Modo fixo: `gpt-6-astra`, só leitura, sem aprovação, busca na web ao vivo, sessão efêmera.
- Rodar com `run_in_background` (2 a 15 min); nunca `sleep`. Log em `<saida sem .md>.log`.
- Pasta: `<scratchpad>/astra/`, nomes `<tema>-1a-pesquisa`, `-1b-estrategia-texto`, `-2-revisao`, `-3-segunda-opiniao`.
- **Divisão 1a/1b obrigatória em guia longo.** No PBM, duas entregas se perderam: o contexto encheu e a compactação falhou com "The backend request failed". A saída virou uma saudação genérica.
  - Limites que funcionaram: 1a com até cerca de 25 consultas na web e sem ler HTML dos guias; 1b com 6 a 8 consultas; revisão com 3 a 6.
  - Leitura sempre com `rg`/`sed -n` em faixas de linha dadas no pedido.
  - O script avisa quando o erro aparece no log. Nesse caso, ler a saída antes de usar e, se ela falhou, dividir ou cortar leitura (não reenviar igual).
- **O shell do Astra não tem rede** (curl falha no DNS). Passar a página local sem tags (`sed 's/<[^>]*>/ /g' x.html | tr -s ' \n'`); Claude confere links e a versão publicada.
- **Estrutura do pedido** que funcionou: papel; objetivo (público, termos, intenção, pedido do André com data); contexto com caminhos e faixas de linha; dados de busca em tabela; decisões já tomadas (não reabrir); economia de contexto com limites; entrega numerada, "uma entrega só, em Markdown, nesta ordem"; regras de voz; "Entregue o documento completo como resposta final."
- Saídas de 30–50 KB: ler em trechos.

## Regras de marca e de conteúdo que se repetem

- "Farmácia", nunca "loja". No loop: "ruptura" e "próxima distribuidora da lista"; nunca "reserva" nem "saldo".
- Sem "tempo real" (cotações chegam por rodada). Sem promessa de economia nem percentual de ganho; número de exemplo fictício marcado pode (5% de tolerância na cotação).
- Sem citar concorrentes, distribuidoras, laboratórios, ERPs, redes ou clientes, salvo exceção registrada em `docs/guias-de-conteudo.md` (ex.: empresas de PBM no passo de adesão, liberadas em 07/11/2026). Links externos só para fontes oficiais.
- Sem planilha: a palavra não aparece; a comparação é mostrada como a aitrus faz (pedido do André, 08/11/2026).
- Exemplos fictícios marcados ("ilustração · valores de exemplo"), com molécula (losartana 50 mg), "laboratório 1", "distribuidora 1"; número real só com fonte, período e data.
- Sem orientação clínica, fiscal ou jurídica: o que a norma ou a autoridade diz, com órgão, data e alcance.
- Sobre a aitrus, só o publicado (`index.html` e manual). Preço e gratuidade não aparecem; formulário diz só "O teste da aitrus será liberado após o cadastro." A aitrus não faz precificação.
- Autoria "Equipe aitrus" com link para `/quem-somos`; nome de pessoa só com o OK dela.
- Dúvidas que acrescentam algo; não repetir seção do corpo.

## Delegar a outra sessão

Skill `orquestrar-sessoes`. Uma etapa por sessão (ex.: pauta no DataForSEO, implementação de texto já conferido, inspeção visual) ou o guia inteiro até o commit local. Na `tarefa.md`: "siga a skill `conteudo-seo`"; tema, termos e decisões do André; afirmações liberadas e vetadas; onde estão os pedidos e saídas do Astra; limites (sem push, sem publicar, sem Search Console, sem outras sessões); entrega em `relatorio.md`. O gerente sempre revisa: afirmações, contas e links por amostragem, contra as decisões já tomadas. Decisão nova sobe ao André antes de publicar.
