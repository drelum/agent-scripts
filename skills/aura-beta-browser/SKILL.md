---
name: aura-beta-browser
description: Preparar alvos, autenticação e cenários de navegação no Aura Beta e Aura UI Beta com agent-browser. Usar para conferir fluxos locais, telas, filtros, dados e chamadas de API; seguir o executor de QA exigido pelo workspace e fornecer o contexto Aura ao worker de visual-inspection.
---

# Aura Beta Browser

Preparar e conferir a aplicação Beta local com `agent-browser`, incluindo acesso autenticado por token, CNPJ padrão e validações de UI e rede pelo executor autorizado no workspace.

## Contexto estável

- Raiz: `/home/drelu/Projects/beta`.
- Alvo padrão: `https://ui.beta.aura.localhost` e `https://api.beta.aura.localhost`.
- CNPJ padrão: `05101867000157`, salvo outro informado pelo Andre.
- Token: `/home/drelu/Projects/beta/scripts/beta-api-token.sh`, com suporte a `BETA_API_URL`.
- Viewport padrão: `1366x768`.

## Resolver o alvo

Antes de autenticar, definir o par `ui_url`/`api_url` nesta ordem:

1. URLs informadas no pedido.
2. Par ativo do checkout atual registrado em `portless list`, identificado pelo slug ou pelos comandos do `AGENTS.md` local.
3. Alvo padrão acima.

Se apenas uma URL alternativa estiver disponível, completar o par somente por uma correspondência inequívoca `ui.`/`api.` no Portless; em caso de ausência ou ambiguidade, parar como `BLOCKED`. Confirmar que ambas respondem e nunca trocar silenciosamente um alvo alternativo indisponível pela esteira padrão.

## Escolher o fluxo

- As instruções do workspace determinam quem executa QA. No workspace do Andre, testes visuais e browser QA usam `visual-inspection`; o agente principal prepara o alvo e o handoff por diagnósticos permitidos, sem executar o teste no navegador.
- Fornecer ao worker as instruções Aura relevantes desta skill: par UI/API, bootstrap protegido, loja/entidade e critérios. O worker executa navegação, interação, capturas e validação de rede na sua sessão isolada.
- Fora desse contexto, navegação direta só cabe quando permitida pelas instruções aplicáveis. Esta skill não autoriza substituir o worker em caso de bloqueio.
- Testar o formulário com usuário e senha somente quando o login em si fizer parte do critério. Nos demais casos, preferir o bootstrap por token.

## Preparar

1. Ler a skill `agent-browser` e carregar suas instruções essenciais antes de operar o navegador.
2. Resolver e confirmar `ui_url` e `api_url`. Reutilizar os servidores existentes; iniciar servidores com `portless` e `tmux` somente quando necessário e dentro do escopo pedido.
3. Criar uma sessão isolada por alvo, restringir a navegação aos hosts resolvidos e configurar viewport `1366x768`.
4. Obter o token em uma variável de processo, sem imprimi-lo:

```bash
token="$(BETA_API_URL="$api_url" /home/drelu/Projects/beta/scripts/beta-api-token.sh)"
```

5. Não incluir senha ou token em prompt, handoff, log, relatório, screenshot, histórico ou artefato. Quando a ferramenta exigir materialização, usar stdin ou arquivo temporário com permissão `0600`, apagar ao concluir e nunca exibir o conteúdo.

## Autenticar por token

O Aura UI aceita bootstrap autenticado em:

```text
/login?token=<token>&cnpj=<cnpj>&redirect_uri=<rota-relativa>
```

1. Montar a navegação em `ui_url` usando o token já protegido, sem registrar a URL expandida.
2. Usar somente `redirect_uri` relativa e rotas internas conhecidas.
3. Aguardar a validação no backend, a criação da sessão e o redirecionamento.
4. Confirmar que a URL final não contém `token` e que a rota esperada abriu autenticada.
5. Se o bootstrap falhar uma vez, obter snapshot e dados de rede sanitizados. Não repetir expondo o segredo nem trocar automaticamente para senha.

## Executar o teste no executor autorizado

1. Abrir diretamente a rota relevante por meio do bootstrap autenticado.
2. Obter snapshot antes de interagir.
3. Após mudança de DOM, debounce, modal ou filtro, aguardar o estado esperado e observar `snapshot --delta` com escopo consistente. Ampliar o snapshot para conteúdo estático quando necessário. Após navegação, obter novo estado; elementos substituídos invalidam refs. Usar `--delta --full` para renovar a base.
4. Exercitar somente o fluxo pedido, com uma tentativa e uma repetição razoável.
5. Validar resultado visível e, quando útil, a chamada de API correspondente. Para critérios temporais, pedir vídeo nativo com intervalos e quadros ao worker; seguir [evidência de mídia](../visual-inspection/references/media.md). Capturas condicionais são apenas acompanhamento; a prova final exige artefato atual inspecionado.
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
- URLs de UI e API utilizadas;
- CNPJ e entidade de negócio usados;
- resultado `PASS`, `FAIL` ou `BLOCKED`;
- estados visíveis confirmados;
- método, endpoint e status relevantes, já sanitizados;
- limitação ou falha reproduzível.

Nunca relatar o token, a senha, cookies, headers de autorização ou a URL de bootstrap expandida.
