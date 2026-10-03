# Promoção do Aura UI Beta

## Arquitetura efetiva

- Aura UI usa Cloudflare Workers/Wrangler, não Pages.
- O push do snapshot para `aitrus-tech/aura-ui:beta` dispara o pipeline automático `aura-ui-staging`. Não é necessário deploy manual nem alterar a configuração da Cloudflare para uma promoção normal.
- Configuração conferida em 08/09/2026: Worker `aura-ui-staging`, branch de produção desse Worker = `beta`, builds de outras branches desabilitados; build `pnpm build:staging`, deploy `pnpm dlx wrangler@4.118.0 deploy --env staging`. Revalidar a configuração efetiva; a versão da CLI registrada é evidência, não um pin obrigatório para novos fluxos.
- Existe também o pipeline `aura-ui`, com branch produtiva `prod` e previews das demais branches. Sua falha isolada não bloqueia a Beta quando `aura-ui-staging` publica corretamente o mesmo SHA. Não alterar esse pipeline como parte da promoção Beta sem pedido específico.
- O alias de preview `beta-aura-ui` pertence ao pipeline geral; não confundi-lo com o endereço do Worker `aura-ui-staging`. Obter o endereço efetivo nas configurações de domínios/visita do Worker correto.
- `wrangler versions upload --env staging` apenas envia versão; não presumir que isso atualiza tráfego.

## Preflight e gates

- Confirmar `gh auth status`, `wrangler whoami`, existência do Worker e check-run anterior apenas como evidência histórica.
- Conferir o trigger de `aura-ui-staging`, não apenas o geral `aura-ui`. Se a API de Builds retornar 403 com OAuth da CLI, consultar o painel autenticado pelas skills de browser, sem extrair credenciais. Não concluir que o deploy está bloqueado só porque essa consulta falhou.
- Verificar `wrangler.jsonc`, scripts do `package.json` e `.env.staging`. O bundle Beta deve usar `VITE_AURA_API_BASEURL=https://aura.apis-beta.aitrus.ai`.
- Tudo em `VITE_*` é público. Nunca colocar token, senha ou segredo no frontend ou nos logs.
- Rodar build `staging`, Biome, typecheck, testes com no máximo três workers e Knip. Classificar dívida baseline separadamente; não ocultá-la nem atribuí-la ao escopo sem evidência.
- Se backend e UI forem promovidos juntos, iniciar a UI somente depois de o backend novo passar runtime e smoke.

## Depois do push

Consultar o check-run `Workers Builds: aura-ui-staging` pelo SHA promovido até `completed`. Extrair do resultado e do Worker:

- Build ID;
- Version ID;
- deployment ativo e distribuição de tráfego;
- URL efetiva de `aura-ui-staging`.

Sucesso de outro check-run não substitui essa verificação; falha do pipeline geral deve ser reportada separadamente. Não repetir push nem efetuar deploy manual para contorná-la.

## Smoke

No mínimo:

1. Confirmar que uma rota SPA relacionada à mudança retorna o HTML novo.
2. Extrair o asset principal e o chunk da rota; confrontar o conteúdo servido pelo endereço Beta com a versão/deployment associado ao SHA promovido. Se houver URL versionada, comparar também os artefatos.
3. Confirmar no bundle o hostname da API Beta e evidência específica da mudança, sem tratar simples presença de string como prova completa de interação.
4. Verificar CORS do backend para o alias Beta quando aplicável.
5. Quando browser QA estiver autorizado, usar `aura-beta-browser` com URLs remotas explícitas; quando inspeção independente for exigida, usar `visual-inspection`. Não executar uma delas como fallback silencioso após dispensa do Andre.
