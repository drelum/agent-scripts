---
name: aura-beta-promotion
description: Preparar, autorizar, promover e validar snapshots do monorepo Beta nas branches oficiais beta do Aura e Aura UI. Usar quando Andre pedir promoção, publicação ou deploy oficial Beta; não usar para trabalho diário em drelum/beta, sincronização das branches main originais ou deploy de main/prod.
---

# Aura Beta Promotion

Promover somente a partir de `/home/drelu/Projects/beta`, seguindo primeiro o `AGENTS.md` da raiz. Tratar `drelum/beta:main` como repositório diário; `aitrus-tech/aura:beta` e `aitrus-tech/aura-ui:beta` são destinos excepcionais.

## Escolher o modo

- `backend`: `aura-beta/` -> `upstream-aura/beta`. Ler [references/git-promotion.md](references/git-promotion.md) e [references/backend.md](references/backend.md).
- `ui`: `aura-ui-beta/` -> `upstream-aura-ui/beta`. Ler [references/git-promotion.md](references/git-promotion.md) e [references/ui.md](references/ui.md).
- `both`: concluir push, build, runtime e smoke do backend antes de preparar o push da UI. Uma autorização não cobre os dois pushes.

## Contrato de segurança

- Fazer inspeções, gates e dry-run sem inferir autorização para push.
- Imediatamente antes de cada push real, mostrar remoto, ref local, destino, SHA remoto usado no lease e comando exato; pedir e aguardar novo `OK` do Andre.
- Nunca promover o commit da raiz do monorepo. Usar apenas snapshot subtree do projeto correspondente.
- Nunca escrever em `main`, `prod`, tags ou outras refs dos repositórios oficiais.
- Preservar alterações não relacionadas. Se houver trabalho não commitado, declarar exatamente que ele fica fora do snapshot; se deveria entrar, parar antes da promoção.
- Não imprimir configuração descriptografada, tokens, headers, cookies ou valores de segredos.
- Respeitar dispensa explícita de Auto Review, visual-inspection ou browser QA e registrar essa limitação sem substituí-la silenciosamente por outro gate.

## Fluxo

1. Confirmar raiz, branch, status, remotos e instruções atuais. Executar preflight de autenticação das CLIs necessárias antes de gates demorados.
2. Congelar o estado commitado. Preparar ou reutilizar uma branch de promoção e provar igualdade entre a árvore do snapshot e `HEAD:<subtree>`.
3. Buscar novamente `beta`, comparar história e árvore. Commits remotos exclusivos exigem parada e decisão explícita.
4. Executar os gates do modo escolhido. Separar falhas do escopo de dívida baseline; não chamar um gate global de verde quando não foi.
5. Revalidar ao vivo o trigger e os destinos do provedor. Não inferir configuração por execução passada.
6. Fazer dry-run com `--force-with-lease=refs/heads/beta:<sha-remoto-verificado>` mesmo em fast-forward.
7. Pedir autorização final. Após o `OK`, executar somente o comando apresentado.
8. Localizar o build pelo SHA promovido e acompanhar até estado terminal. Não usar apenas “último build”.
9. Validar runtime e uma funcionalidade realmente alterada. Health, raiz HTTP 200 ou build verde isolados não bastam.
10. Relatar SHA, build, revisão/versão, tráfego/alias, smoke, horário de São Paulo e limitações. Confirmar que trabalho local excluído permaneceu intacto.

## Paradas obrigatórias

Parar antes do push quando houver destino ambíguo, árvore divergente, ref remota mudando depois do fetch, commit remoto exclusivo sem decisão, gate bloqueador, trigger inesperado ou ausência de autorização final. Depois do push, acompanhar falha do provedor até uma causa verificável; não repetir push automaticamente.
