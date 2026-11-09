# Modelos de pedido ao Astra

Tirados dos pedidos reais de PBM (07/11/2026) e cotação (08–09/11/2026). Copie, troque os `<espaços>` e corte o que não se aplica. Cada pedido vira um arquivo em `<pasta-astra>/<tema>-<etapa>.md` e roda com `scripts/astra.sh`.

Espaços usados:

- `<pasta-astra>`: pasta de rascunho da sessão, ex.: `<scratchpad>/astra`;
- `<tema>`, `<endereço>` (ex.: `/pbm-farmacia`), `<data>` (dd/mm/aaaa);
- `<termos e volumes>`: tabela da etapa de pauta (termo · volume · primeira página);
- `<decisões>`: o que o André e Claude já decidiram (não reabrir);
- `<permitido sobre a aitrus>` e `<não afirmar>`: conferidos em `index.html` e no manual (`sed -n 590,600p`).

Bloco de voz, igual nos quatro (colar no fim de cada pedido):

```markdown
# Regras de voz
- Frases curtas, segunda pessoa, vocabulário do balcão. Escreva direto: sem ressalvas em cascata.
- Sem estrangeirismos; o termo em inglês uma vez, entre parênteses.
- Sem superlativos, sem "tempo real", sem promessa de economia, de percentual ou de posição no Google.
- "Farmácia", nunca "loja". No loop, "ruptura" e "próxima distribuidora da lista"; nunca "reserva" nem "saldo".
- Não cite distribuidoras, clientes, laboratórios, marcas de medicamento, concorrentes nem ERPs <exceções registradas, se houver>.
- Nos exemplos, use molécula (ex.: losartana 50 mg), "laboratório 1" e "distribuidora 1", marcados como fictícios.
- Sem orientação clínica, fiscal ou jurídica: diga o que a norma ou a autoridade disse, com órgão, data e alcance.
```

## 1. Pesquisa (1a)

```markdown
Você é o estrategista de SEO, pesquisador e redator de conteúdo da aitrus. Trabalhe só com leitura (não edite arquivos) e com busca na web. Responda em português do Brasil, com acentuação correta.

# Objetivo
Nova página do site da aitrus (aitrus.com.br): **<tema>**, para ranquear no Google Brasil em <termos principais> e atrair donos, gerentes e compradores de farmácia e de redes. Intenção: <informativa: guia que cria reputação com a visão do dono da farmácia | comercial: página que une guia e solução e se amarra à aitrus>.
<Pedido do André, com data.>

# Dados de busca (DataForSEO, Google Brasil, desktop, <data>; volume = média do Google Ads de <período>)
<termos e volumes>
- Primeira página, "As pessoas também perguntam", Visão geral de IA: <resumo por termo>.
- Concorrentes vistos (pode ler para referência; **nunca cite nem linke no texto**): <lista>.
- Ressalva: sem volume medido não quer dizer sem busca.

# Contexto da aitrus (leia só estes trechos)
- `docs/guias-de-conteudo.md`, linhas <A–B> ("Padrões comuns").
- `docs/seo-pautas.md`: só a seção "<título da seção>" (`rg -n` e `sed -n` em volta).
- `index.html`, linhas <A–B>, sem tags: `sed -n 'A,Bp' index.html | sed 's/<[^>]*>//g'`.
- Manual de marca `/home/drelu/Projects/context/aitrus/marca/index.html`: só `sed -n 590,600p`, sem tags.
- Confirmado e publicado sobre a aitrus: <permitido sobre a aitrus>.
- Não afirmar: <não afirmar>. O que depender de liberação vem à parte, marcado "[DEPENDE DO OK DO ANDRÉ]".

# Esta etapa: só pesquisa (estratégia e texto ficam para uma segunda chamada)
Em tarefas longas, o contexto encheu e a compactação falhou ("The backend request failed"). Por isso:
- Entregue só os itens abaixo; nada de texto da página.
- Leia arquivos com `rg`/`sed -n` em trechos curtos; nunca imprima páginas inteiras. Não leia as páginas HTML dos guias.
- No máximo cerca de 25 consultas na web, sem repetir.
- Pistas para conferir: <links e fatos já achados, se houver>.

# O que eu preciso (uma entrega só, em Markdown, nesta ordem)
1. **Pesquisa factual com fontes** (link e data para cada fato; "a confirmar" quando não houver fonte primária): <perguntas do tema: definição, como funciona para a farmácia, dinheiro, regras com órgão e data, estoque e compra, dados de mercado só com fonte datada>.
2. **Boas práticas do Google Search Central** aplicáveis (link e data): conteúdo útil, título e trecho, títulos, links internos, dados estruturados que cabem (e os que não usar), recursos de IA na Busca<, página de produto × artigo, canibalização com a home>. Para cada uma, o que fazer nesta página em uma ou duas linhas.
3. **Primeira página**: 4 a 7 páginas (tipo, data, o que cobrem, o que falta ao dono da farmácia) e o padrão que o Google premia.
4. **Recomendações para a estratégia** (até 12–15 itens): intenção principal e secundárias, endereço (avalie <opções>), duas opções de título, H1 e descrição, sumário, elementos únicos, perguntas frequentes que acrescentem algo, ligações internas, o que evitar, perguntas para o André.

<Regras de voz>

Entregue o documento completo como resposta final.
```

## 2. Estratégia e texto (1b)

```markdown
Você é o estrategista de SEO e redator de conteúdo da aitrus. Trabalhe só com leitura (não edite arquivos). Responda em português do Brasil, com acentuação correta.

# Objetivo
Nova página do site da aitrus: **<tema>**. Público: donos, gerentes e compradores de farmácia e de redes. <Intenção em uma frase.>
Esta é a segunda etapa. A sua pesquisa está em `<pasta-astra>/<tema>-1a-pesquisa.saida.md`. Use-a como base; só volte à web para conferir um ponto específico (no máximo 6 a 8 consultas).

# Economia de contexto (obrigatório)
Em tarefas longas, o contexto encheu e a compactação falhou. Leia em trechos curtos com `rg`/`sed -n`, nunca páginas inteiras. Nesta ordem e só o necessário:
1. A sua pesquisa, inteira.
2. `docs/guias-de-conteudo.md`, linhas <A–B> ("Padrões comuns").
3. `<página-modelo>.html`, sem tags: abertura e figura (linhas <A–B>), seção da aitrus e nota final (<A–B>), começo das dúvidas (<A–B>).
4. `index.html`, sem tags: linhas <A–B>.
5. Manual de marca: `sed -n 590,600p`, sem tags.

# Decisões já tomadas (<quem>, <data>)
- **Endereço** `<endereço>`. Termo principal no começo do título, no H1, na abertura e no primeiro parágrafo do corpo.
- **Layout dos guias:** abertura escura com trilha "Início › <tema>", H1, apoio de até 35 palavras e duas frases, autoria "Por Equipe aitrus · Publicado em <data>", botões e figura (uma ideia, até cerca de 30 palavras); corpo branco com sumário lateral; formulário antes das dúvidas ("O teste da aitrus será liberado após o cadastro."); nota "Fontes conferidas em <data>." no fim.
- **Primeiro H2 "O que é <tema>?"**: 35 a 50 palavras, começa pelo assunto, sem a aitrus (candidato a resposta em destaque e Visão geral de IA). A tarefa do H1 vem logo depois.
- **Dados estruturados:** <guia: `Article` + `BreadcrumbList` | página comercial: só `BreadcrumbList`>. `FAQPage` sai no build de `#duvidas`.
- **Exemplo:** <molécula, embalagens, farmácias, regra>; marcado "ilustração · valores de exemplo"; refaça cada conta.
- **Nomes e links:** só fontes oficiais, com `rel="noopener"`: <lista>. Fatos de regulamentos ou centrais de ajuda de empresas entram sem nome e sem link ("em programas consultados em <data>").
- **Sobre a aitrus:** só <permitido sobre a aitrus>. Não afirmar: <não afirmar>. Parágrafos que dependem de liberação vêm à parte, marcados "[DEPENDE DO OK DO ANDRÉ]".
- <Outras decisões: palavras vetadas, termos que entram uma vez, botões, menu do topo.>

# O que eu preciso (uma entrega só, em Markdown, nesta ordem)
1. **Estratégia curta** (até 15 linhas): intenção; título (até 60 caracteres), descrição (até 155), H1, og:title e og:description; sumário com H2/H3 e `id`; por que supera a primeira página.
2. **Texto completo da página**, no formato dos guias: metadados, trilha, abertura, botões, menu do topo com âncoras, figura; todas as seções com H2/H3 e texto visível; blocos `[TABELA: …]`, `[QUADRO: …]` e `[DIAGRAMA: …]` com dados completos, legenda e rótulos de coluna; 5 a 7 perguntas frequentes (40 a 90 palavras) que acrescentem algo ao corpo; nota final; textos curtos de ligação a partir de <páginas e seções>, com texto âncora e onde entram. Tamanho: o necessário, sem enchimento (<faixa de palavras>).
3. **Parágrafos "[DEPENDE DO OK DO ANDRÉ]"**, se houver.
4. **Lista de conferência:** cada afirmação factual com a fonte; cada afirmação sobre a aitrus com o trecho do repositório; cada conta refeita.

<Regras de voz>

Entregue o documento completo como resposta final.
```

## 3. Revisão da página implementada (2)

```markdown
Você é o revisor de SEO e conteúdo da aitrus. Trabalhe só com leitura (não edite arquivos). Responda em português do Brasil.

# O que revisar
A página `<arquivo>.html` (raiz do repositório), implementada a partir do seu texto em `<pasta-astra>/<tema>-1b-estrategia-texto.saida.md`. Leia sem as tags: `sed 's/<[^>]*>/ /g' <arquivo>.html | tr -s ' \n'`; o `<head>` (linhas 1–50) com as tags.
Também mudaram: links novos para a página em <páginas> (`git diff -- '*.html' | grep '^[-+]' | grep -v rodape`) e o item no rodapé de todas as páginas.

# Mudanças de Claude sobre o seu texto, já decididas (não reabrir)
- <mudança> — <motivo ou fonte conferida, com trecho e data>.

# O que eu preciso (curto: até 40 linhas)
1. Problemas reais, do mais grave ao menos grave, cada um com o trecho atual, a correção pronta para colar e o motivo. Confira:
   - **Fatos:** cada afirmação confere com a sua pesquisa? Algo ficou generalizado depois da mudança de tom?
   - **Contas** do exemplo.
   - **SEO:** título (até 60), descrição (até 155), H1, abertura (até 35 palavras), definição (35 a 50), hierarquia de títulos, `id` únicos, âncoras do menu e do sumário, links internos e externos, dados estruturados.
   - **Afirmações sobre a aitrus**, contra `index.html` e o manual (`sed -n 590,600p`, sem tags).
   - **Marca:** as regras de voz abaixo.
   - **Perguntas frequentes** que repetem uma seção do corpo.
   - **Celular:** tabelas `compacta` (2–3 colunas) ou `empilhada` com `data-rotulo` (4+), cabeçalhos de linha, links dentro de `th`, `R$&nbsp;`.
2. **Veredito:** pronta para publicar ou o que falta.

Não repita o que já está certo. Economize contexto: trechos curtos, sem busca na web salvo para conferir um fato duvidoso (no máximo 3 a 6 consultas). Seu shell não tem rede: não use curl.

<Regras de voz>
```

## 4. Segunda opinião independente (3, opcional)

Não passe a revisão anterior, as conclusões de Claude nem as mudanças já feitas: só o objetivo, os termos, as regras e onde ler.

```markdown
Você é um consultor de SEO e conteúdo B2B, chamado para dar uma segunda opinião independente e crítica. Trabalhe só com leitura (não edite arquivos). Responda em português do Brasil.

# Contexto
A aitrus (aitrus.com.br) é uma plataforma de compras para farmácias: mix, cotação com distribuidoras e OL, pedido e acompanhamento do faturamento. Publicamos em <data> a página https://aitrus.com.br<endereço>, arquivo `<arquivo>.html` na raiz do repositório.
Objetivo: ranquear no Google Brasil para <termos> e atrair cadastros.
Dados de busca e concorrência em `docs/seo-pautas.md`, seção "<título>", até o próximo "## ". Resumo: <3 a 4 itens>.

Regras da marca que limitam o texto (não proponha quebrá-las):
- **Nomes:** não citar distribuidoras, laboratórios, concorrentes nem ERPs.
- **Promessas:** nada de economia, percentual, "tempo real" ou "grátis"; não falar de preço da aitrus.
- **Vocabulário:** "farmácia", nunca "loja"; <vetos do André, ex.: sem planilha>.
- **Escopo:** afirmar só o que o produto faz e está publicado (`index.html` e manual, `sed -n 590,600p` sem tags).

# O que eu quero de você
Uma leitura independente, sem tentar confirmar o que já foi feito. Leia a página sem tags: `sed 's/<[^>]*>/ /g' <arquivo>.html | tr -s ' \n'`, e o `<head>`. Se quiser, consulte os resultados do Google e as páginas dos concorrentes (no máximo 10 consultas na web; o shell não tem rede).

Responda, em até 60 linhas:
1. **Veredito:** atende à intenção? Tem chance real de ficar entre os 5 primeiros em <termos>? Por quê?
2. **Os 5 problemas ou lacunas mais importantes**, em ordem de impacto (ranqueamento e conversão): trecho atual, o que mudar, motivo. Inclua o que falta e o que sobra.
3. **Título, descrição e H1:** mantém ou troca? Se trocar, uma opção para cada, com a contagem de caracteres.
4. **Fora da página:** o que mais pesaria para ranquear, em até 5 itens.
5. **O que não mexer.**

Economize contexto: trechos curtos, nada de imprimir páginas inteiras do repositório.
```
