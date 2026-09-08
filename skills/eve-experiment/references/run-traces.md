# Traces completos de runs

Read when: investigar resultado, ferramentas ou diferenças entre uma execução local e Production.

## Evidência e leitura segura

1. Fixe `sessionId`/run, turno ou conversão, URL, projeto, equipe, ambiente e deployment. Não deduza
   o provider somente de `targetKind`. Preserve SHA-256 da origem para comparar o mesmo arquivo.
2. Consulte `vercel --help` e os helps de `agent-runs list|inspect|trace` da CLI instalada. Na CLI
   59.5.0, `inspect <runId> --json` e `trace <runId> --json --max-field-length 0` ajudam a localizar
   a trajetória; selecione a equipe e janela de tempo corretas. `vercel logs` mostra runtime,
   não substitui a trajetória estruturada. Remover truncamento de campos não garante todos os eventos.
3. Prefira o cliente nativo `eve/client` para ler a sessão existente: stream desde o início, com
   `follow: false`. Confira a assinatura na documentação instalada. O HTTP equivalente é GET
   `/eve/v1/session/<sessionId>/stream?startIndex=0&includeTailIndex=1`, autenticado no ambiente
   correto. O tail informado delimita um snapshot, não prova que o turno terminou.
4. Se essa superfície não estiver acessível com a identidade autorizada, use o SDK oficial do
   Workflow do provider para ler o mesmo run, conforme o procedimento versionado abaixo. Não envie
   mensagens nem use resume, cancel, clear, reset ou replay de execução para investigar.
5. Confira o turno alvo até `turn.completed`/falha e seu resultado de domínio. `session.waiting`
   significa sessão disponível para novo turno; workflow `running` ou stream `done: false` pode ser
   normal após a conversão finalizar. Não encerre no primeiro waiting de uma sessão com vários turnos.
6. Correlacione `actions.requested` e `action.result` pelo `callId`; deltas e `action.partial` não
   são resultados finais. Compare o artefato publicado com o resultado da ferramenta antes de
   atribuir mudança ao consumidor. Use SHA-256 quando houver referência a bytes externos.
7. Use `sourceSheet`, `physicalSourceRow`, `tableIndex` e `tableRow` quando disponíveis. `sourceRow`
   é lógico; uma linha não pertence a um evento individual sem vínculo explícito na evidência.

Não use endpoints do consumidor sem conferir seus efeitos: mesmo um GET de importação pode retomar
trabalho em segundo plano. Não exponha tokens, URLs assinadas, dados pessoais ou traces brutos em
logs públicos. Guarde evidência confidencial somente no diretório autorizado e ignorado pelo Git.

Com um `client` autenticado no destino, a leitura nativa é:

```ts
const session = client.sessions.attach(sessionId);
for await (const event of session.stream({ startIndex: 0, follow: false })) {
  // Analise o evento no contexto do turno alvo; não imprima dados sensíveis.
}
// Alternativa nativa para eventos + cursor consistente:
const snapshot = await session.snapshot();
```

Escolha stream ou snapshot, sem executar ambos para a mesma investigação. O snapshot pode conter
um turno ainda em andamento: término da leitura não significa término do processamento.

## Leitura pelo Workflow: procedimento verificado em eve 0.52.1

Prefira exports públicos do SDK quando disponíveis. Nesta versão, foram usados os módulos já
embutidos no pacote instalado, sem adicionar dependências nem copiar código do framework:

```js
import { createWorld } from './node_modules/eve/dist/src/compiled/@workflow/world-vercel/index.js';
import { getRun, setWorld } from './node_modules/eve/dist/src/compiled/@workflow/core/runtime.js';

// token obtido em memória da autenticação autorizada da CLI, nunca literal ou impresso.
const world = createWorld({
  token,
  projectConfig: { projectId, teamId, environment: 'production' },
});
setWorld(world);
const streamIds = await world.streams.list(runId);
const info = await world.streams.getInfo(runId, streamId);
const readable = getRun(runId).getReadable({ startIndex: 0 });
```

Fragmento ilustrativo: ids, token e streamId devem ser resolvidos previamente para o run alvo.
Os caminhos `compiled` são internos e específicos da versão: revalide exports e assinaturas antes
de reutilizar. Não trate esse acesso como API estável do kit nem crie uma camada de persistência.
Autenticação da CLI deve ser lida apenas em memória; não use OIDC de Development em Production.

- O stream padrão observado foi `strm_<runId>_user`. Não passe `namespace: 'user'`: nessa versão
  isso acrescenta um sufixo codificado e seleciona outro stream, que pode nunca receber dados.
- `streams.getChunks` entrega bytes enquadrados/criptografados. Use `getRun().getReadable()` para
  decodificação pelo SDK; não implemente decriptação ou tente JSON.parse nesses chunks brutos.
- Decodifique o readable com um único `TextDecoder`, em modo streaming, e acumule NDJSON entre
  chunks. Não suponha que um chunk seja um evento completo. Faça flush no encerramento e detecte
  linha residual incompleta. Prefira o cliente Eve quando ele já resolver essa leitura.
- Delimite a leitura pelo turno alvo ou snapshot confirmado. `tailIndex` do storage é índice de
  chunks: não assuma igualdade com quantidade de eventos NDJSON sem verificar a representação.
  Configure prazo no leitor local; ao expirar, feche somente o leitor e reporte evidência incompleta.
  Nunca cancele o run remoto para encerrar a consulta.

## Completude e versão efetiva

No diagnóstico que motivou esta nota, a CLI mostrou seis ferramentas, mas o stream nativo continha
7.199 eventos e 13 resultados de ferramenta, incluindo a finalização. A ausência no agregado não
provava ausência na execução. O resultado original já continha o campo incorreto antes do consumidor.

Compare `session.started` (build, versão Eve) e `step.started` (modelo efetivo) com deployment e
manifesto do experimento. Metadados de build podem estar desatualizados num prebuilt: divergência
de SHA exige investigação, não escolha silenciosa de uma fonte. Não afirme equivalência de código
somente pelo wrapper; compare também instruções efetivamente carregadas e artefatos relevantes.

Referência oficial: [Sessions, Runs & Streaming](https://eve.dev/docs/concepts/sessions-runs-and-streaming),
também disponível em `node_modules/eve/docs/concepts/sessions-runs-and-streaming.md`.
