# Snapshot e promoção Git

## Mapeamento fixo

| Modo | Subtree | Remoto | Destino permitido |
| --- | --- | --- | --- |
| backend | `aura-beta` | `upstream-aura` | `refs/heads/beta` |
| ui | `aura-ui-beta` | `upstream-aura-ui` | `refs/heads/beta` |

Operar pela raiz `/home/drelu/Projects/beta`. Os checkouts irmãos oficiais não são fontes da promoção.

## Preparar ou reutilizar snapshot

Preferir `./scripts/prepare-beta-promotion.sh <aura|aura-ui> [branch]` quando a árvore estiver limpa. O script nunca faz push. Se uma branch já preparada for reutilizada, não recriá-la só porque o worktree ficou sujo depois; verificar o snapshot existente.

Provas mínimas, ajustando nomes:

```bash
git rev-parse <snapshot>
git rev-parse <snapshot>^{tree}
git rev-parse HEAD:<subtree>
git diff --quiet <snapshot> HEAD:<subtree>
```

Os dois hashes de árvore devem ser iguais e o `git diff --quiet` deve sair com zero. Listar separadamente alterações e arquivos novos do worktree que não entrarão.

## Comparar destino

```bash
git fetch --prune <remote> refs/heads/beta:refs/remotes/<remote>/beta
remote_sha="$(git rev-parse refs/remotes/<remote>/beta)"
git rev-list --left-right --count refs/remotes/<remote>/beta...<snapshot>
git log --oneline <snapshot>..refs/remotes/<remote>/beta
git diff --shortstat refs/remotes/<remote>/beta <snapshot>
```

Usar comparação direta de árvores para o estado final; contagem de commits e diff com três pontos não provam equivalência. Se `git log <snapshot>..<remote>/beta` mostrar commits, explicar o conteúdo e parar até Andre decidir preservá-los ou substituí-los.

## Dry-run e autorização

```bash
git push --dry-run \
  --force-with-lease=refs/heads/beta:"$remote_sha" \
  <remote> \
  <snapshot>:refs/heads/beta
```

Depois do dry-run, apresentar o mesmo comando sem `--dry-run`, com o SHA literal do lease, e pedir novo `OK`. Não recomputar ou trocar refs silenciosamente depois da autorização. Se a ref remota mudar, invalidar a autorização, buscar novamente e repetir comparação e dry-run.

Após o push, confirmar que `git ls-remote <remote> refs/heads/beta` devolve exatamente o SHA do snapshot.
