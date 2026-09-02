---
name: aura-novidades
description: "Publicar novidades do Aura Beta em novidades.aitrus.com.br: levantar o que mudou, capturar telas mascaradas no Aura Beta local, escrever entradas em linguagem de farmácia (problema, o que muda, onde encontrar), sintetizar a chamada do dia, publicar na Vercel e conferir. Usar quando Andre pedir para publicar novidades, atualizar o site de novidades, ou ao fechar um ticket Beta com efeito visível ao gestor."
---

# Aura Novidades

Site estático `https://novidades.aitrus.com.br`; conteúdo e build em `~/Projects/beta/novidades/`
(raiz configurável por `AURA_BETA_ROOT`). Tom, vocabulário e arquitetura em `novidades/CONVENCOES.md`;
passo a passo em `novidades/PROCEDIMENTO.md`. Resolver `<skill-dir>` como a pasta deste `SKILL.md`.

Hierarquia do site: **dia → novidades do dia → novidade**. Duas fontes de verdade, uma por coisa:
`entradas/*.md` (a novidade) e `dias/*.md` (a chamada do dia). Não existem apresentações.

## Regras que não se negociam

- Leitor: o dono da farmácia e o gestor de compras. Sem jargão de interface ou de sistema, sem
  número de versão, sem ticket no texto, sem linha do tempo interna. Vocabulário da tabela de
  tradução em `CONVENCOES.md`.
- Título é o ganho em uma frase. Corpo com exatamente `## O problema`, `## O que muda`,
  `## Onde encontrar`. **"Onde encontrar" sempre diz o caminho no menu e o gesto**, de forma concisa.
- Nunca expor loja, CNPJ, grupo econômico ou usuário do ambiente de testes. Toda captura passa pela
  máscara no DOM antes do clique e só é aceita com `restos: []`.
- Recapturar sempre; nunca reaproveitar imagem antiga. Embaçado por regiões é último recurso.
- Não gravar nada no Aura Beta durante a captura: cancelar modais e wizards antes de sair.
- A tela habitual do leitor é **1024×768**. Qualquer mudança de layout ou de texto longo é conferida
  nessa resolução antes de publicar (`aura-novidades-conferir`). Padrão visual: as páginas seguem as
  telas do Aura (cabeçalho de página, painel de contexto, tabela densa), não um blog. Ver
  "Padrão visual" em `CONVENCOES.md`.
- Commit e push só com OK explícito do Andre.

## Fluxo

### 1. Levantar

```bash
<skill-dir>/scripts/aura-novidades-pendentes            # commits e tickets desde a última entrada
```

Cruzar com `beta-tickets.md` e, se preciso, `git show <hash>`. Selecionar só o que o leitor percebe
na tela ou no resultado da compra. Agrupar ajustes do mesmo tema no mesmo dia numa entrada.

### 2. Capturar

Pré-requisito: API e UI Beta locais no ar (ver `AGENTS.md` da raiz do monorepo) e as convenções da
skill `aura-beta-browser` para navegação.

```bash
source <skill-dir>/scripts/aura-novidades-capturar
nov_login /product-assortment                       # sessão isolada, token, viewport 1440×900
# interações com agent-browser: snapshot -i -c, click, fill; botão direito = mouse move/down right/up right
nov_shot ~/Projects/beta/novidades/entradas/img/<slug>.png   # mascara + verifica + captura
nov_fim
```

- Estados assíncronos: esperar e re-snapshotar antes de `nov_shot`; refs mudam a cada snapshot.
- `nov_shot` falha se restar dado sensível: acrescentar o par em `ALVOS` de `<skill-dir>/scripts/mascara.js`.
- Abrir o PNG e conferir: "Farmácia Modelo", "00.000.000/0001-00", "Grupo Modelo", "Gestor da Loja".
- Sem token, senha ou URL de bootstrap em log, prompt ou relatório.

### 3. Escrever a novidade

`novidades/entradas/AAAA-MM-DD-slug.md`:

```markdown
---
titulo: Frase que diz o ganho
data: AAAA-MM-DD
area: mix | cotacao | carrinho | catalogo | acordos | externas | empacotamentos
perfil: todos | grupo | loja
menu: Compras › Mix de Produtos › Ferramentas › Políticas de fabricantes
resumo: Para quem serve e o que ganha, até 200 caracteres.
imagem: img/slug.png
legenda: Para onde olhar na tela.
ticket: BETA-N
---
## O problema
Situação real da loja, com um exemplo em reais, unidades ou dias.

## O que muda
- **O que você faz ou vê** — três a cinco itens.

## Onde encontrar
**Menu › Submenu › tela**, mais o gesto (botão direito, clique no valor, nome do botão).
```

### 4. Sintetizar o dia

Dia com mais de uma novidade exige `novidades/dias/AAAA-MM-DD.md`:

```markdown
---
chamada: Uma frase de ganho que resume o dia, até 140 caracteres. Nunca uma lista de títulos.
---
Parágrafo opcional apresentando o conjunto.
```

O build avisa quando falta; não publicar com chamada automática.

### 5. Conferir em 1024×768

```bash
<skill-dir>/scripts/aura-novidades-conferir             # build + capturas locais da home, do dia e de uma novidade
```

Abrir os PNGs. Reprovar se: menos de quatro dias visíveis na home, texto cortado ou vazando,
tela ilegível, ou página que pareça um blog em vez de uma tela do Aura.

### 6. Publicar

```bash
<skill-dir>/scripts/aura-novidades-publicar             # build, deploy de produção, conferência das URLs
<skill-dir>/scripts/aura-novidades-publicar --preview   # preview protegido por login da Vercel
```

O script recusa publicar se um texto citar loja, CNPJ ou grupo de teste. Abrir a página do dia e
conferir texto e tela.

### 7. Registrar

- Informar as URLs publicadas: a do dia (`/AAAA-MM-DD`) é a que se manda ao cliente.
- Se a novidade fecha um ticket, atualizar `beta-tickets.md` na mesma sessão.
- Pedir OK para commit no monorepo: `docs(novidades): …` ou `feat(novidades): …`.

## Referências

- Infra: Vercel projeto `aura-novidades` (time `aitrus1`), DNS `A novidades 76.76.21.21` no Cloudflare;
  token de DNS no Infisical `Aitrus Apps` / `staging` / `/shared` / `CLOUDFLARE_DNS_TOKEN`.
- Padrão visual: logo aitrus, DM Sans, tokens do Lumina, já embutidos em `novidades/build.mjs`.
- Imagem antiga sem tela viva: `python3 <skill-dir>/scripts/mascara-png.py <png>` (último recurso).
