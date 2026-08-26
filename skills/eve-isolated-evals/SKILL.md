---
name: eve-isolated-evals
description: Executar baterias Eve Eval isoladas, locais com workflow store novo ou produtivas com identidade efêmera e deployment fixado. Usar para bateria limpa, estado antigo, stale runs, eval remoto em Production ou isolamento entre avaliações.
---

# Eve Eval isolado

Execute o comando na raiz do projeto Eve:

```bash
~/Projects/agent-scripts/bin/eve-eval-isolated [argumentos do eve eval]
```

O executável chama o `eve` instalado em `node_modules/.bin`, portanto passe somente os argumentos
que viriam depois de `eve eval`. Ele requer Linux/WSL com `flock` (`util-linux`).

Ele deve:

- recusar outra bateria isolada ou runtime local `eve dev`/`eve eval` ativo no mesmo projeto;
- mover `.eve/.workflow-data` anterior para `.eve/eval-isolated-runs/<execução>/`;
- preservar `.eve/m` como cache compartilhado;
- executar a bateria sobre um workflow store novo;
- arquivar o store produzido mesmo após falha ou sinal, preservando o código de saída;
- registrar metadados com horários de São Paulo sem apagar evidências anteriores.

Não contorne o wrapper apagando `.eve/.workflow-data`. Se houver concorrência, pare e informe o
processo detectado.

## Production remota

Use o executor canônico, após o projeto injetar a chave privada pelo Secret Manager:

```bash
~/Projects/agent-scripts/bin/eve-eval-remote-production \
  --audience urn:aitrus:service:<agente> -- \
  <comando do projeto com exatamente um --url https://<alias-production>>
```

O agente deve consumir `@aitrus/eve-kit/evals` no servidor e aceitar apenas a chave pública. O
executor emite o bearer ES256 em memória, fixa o deployment apontado pelo alias antes da bateria,
repete a inspeção ao final e invalida o resultado se o alias mudar. Não use o OIDC de Development
da CLI para atravessar ambientes e não grave token ou chave privada nos artefatos.

O projeto continua responsável pelos casos, oráculos, limites de concorrência e artefatos de
qualidade. O executor global registra o pin em `.eve/remote-production-evals/`.

Antes de alterar este fluxo, confira a documentação da versão instalada em `node_modules/eve/docs`
e a [documentação oficial do Eve](https://eve.dev/docs/getting-started). Se o Eve oferecer isolamento
nativo equivalente, prefira a primitiva oficial e atualize o executável e esta skill juntos.
