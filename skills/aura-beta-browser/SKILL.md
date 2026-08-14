---
name: aura-beta-browser
description: Executar testes visuais rápidos, navegação, interação e simulações autenticadas no Aura Beta e Aura UI Beta com agent-browser. Usar para conferir fluxos locais, telas, filtros, dados e chamadas de API durante desenvolvimento; usar visual-inspection quando o pedido exigir uma inspeção independente, source-blind ou evidência formal por worker externo.
---

# Aura Beta Browser

Testar diretamente a aplicação Beta local com `agent-browser`, incluindo acesso autenticado por token, CNPJ padrão e validações rápidas de UI e rede.

## Contexto estável

- Raiz: `/home/drelu/Projects/beta`.
- Frontend: `https://ui.beta.aura.localhost`.
- Backend: `https://api.beta.aura.localhost`.
- CNPJ padrão: `05101867000157`, salvo outro informado pelo Andre.
- Token: `/home/drelu/Projects/beta/scripts/beta-api-token.sh`.
- Viewport mínima: `1024x768`.

## Escolher o fluxo

- Usar esta skill para navegação e interação rápidas feitas pelo agente principal.
- Usar `visual-inspection` para QA independente por worker externo, inspeção source-blind, regressão visual formal ou entrega com evidências isoladas.
- Testar o formulário com usuário e senha somente quando o login em si fizer parte do critério. Nos demais casos, preferir o bootstrap por token.

## Preparar

1. Ler a skill `agent-browser` e carregar suas instruções essenciais antes de operar o navegador.
2. Confirmar que frontend e backend respondem. Reutilizar os servidores existentes; iniciar servidores com `portless` e `tmux` somente quando necessário e dentro do escopo pedido.
3. Criar uma sessão isolada, restringir a navegação aos hosts Beta e configurar viewport `1024x768`.
4. Obter o token em uma variável de processo, sem imprimi-lo:

```bash
token="$(/home/drelu/Projects/beta/scripts/beta-api-token.sh)"
```

5. Não incluir senha ou token em prompt, handoff, log, relatório, screenshot, histórico ou artefato. Quando a ferramenta exigir materialização, usar stdin ou arquivo temporário com permissão `0600`, apagar ao concluir e nunca exibir o conteúdo.

## Autenticar por token

O Aura UI aceita bootstrap autenticado em:

```text
/login?token=<token>&cnpj=<cnpj>&redirect_uri=<rota-relativa>
```

1. Montar a navegação usando o token já protegido, sem registrar a URL expandida.
2. Usar somente `redirect_uri` relativa e rotas internas conhecidas.
3. Aguardar a validação no backend, a criação da sessão e o redirecionamento.
4. Confirmar que a URL final não contém `token` e que a rota esperada abriu autenticada.
5. Se o bootstrap falhar uma vez, obter snapshot e dados de rede sanitizados. Não repetir expondo o segredo nem trocar automaticamente para senha.

## Executar o teste rápido

1. Abrir diretamente a rota relevante por meio do bootstrap autenticado.
2. Obter snapshot antes de interagir.
3. Após toda mudança de DOM, debounce, modal, filtro ou navegação, aguardar o estado esperado e obter snapshot novo. Nunca reutilizar referências antigas.
4. Exercitar somente o fluxo pedido, com uma tentativa e uma repetição razoável.
5. Validar resultado visível e, quando útil, a chamada de API correspondente.
6. Em diagnóstico de rede, conservar apenas método, URL, status e campos de negócio estritamente necessários. Remover headers de autorização, cookies, corpo de login e parâmetros secretos.
7. Encerrar a sessão e remover arquivos ou perfis temporários de autenticação.

## Mix de produtos

Para `/product-assortment`:

1. Autenticar usando o CNPJ pedido ou o padrão.
2. Confirmar a loja `Drogarias Da Vovo` e o CNPJ formatado `05.101.867/0001-57`.
3. Se nenhuma loja estiver selecionada, buscar o CNPJ sem pontuação no seletor, aguardar o debounce e o texto `Drogarias Da Vovo`, obter snapshot novo e escolher somente essa loja.
4. Confirmar linhas na tabela e `POST /api/v1/product/assortment/query` com HTTP `200`.
5. Quando o critério envolver distribuidor, abrir os filtros, selecionar apenas o distribuidor solicitado e verificar o resultado visual e o campo sanitizado correspondente na consulta. Para Santa Cruz, usar a opção canônica `SANTA CRUZ`; não inferir seleção por texto parecido.

## Relatar

Entregar um resumo curto:

- fluxo e rota testados;
- CNPJ e entidade de negócio usados;
- resultado `PASS`, `FAIL` ou `BLOCKED`;
- estados visíveis confirmados;
- método, endpoint e status relevantes, já sanitizados;
- limitação ou falha reproduzível.

Nunca relatar o token, a senha, cookies, headers de autorização ou a URL de bootstrap expandida.
