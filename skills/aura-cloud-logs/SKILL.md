---
name: aura-cloud-logs
description: Investigar logs das aplicações Aura publicadas no Google Cloud, especialmente Aura Beta no Cloud Run. Usar para erros HTTP, falhas de runtime, correlação de requisições e verificação de logs após deploy, com gcloud e somente leitura.
---

# Aura Cloud Logs

Usar `gcloud` diretamente para localizar evidências do incidente. Ler [references/queries.md](references/queries.md) ao montar consultas ou corrigir falhas de acesso, filtros ou saída.

## Confirmar o destino

- Seguir o `AGENTS.md` do projeto. Confirmar identidade ativa e acesso real à API; conta listada não garante autenticação válida nem permissão de leitura.
- Referência observada em 17/09/2026: projeto `aitrus-aura-prod`, serviço `aura-beta`, região `us-central1`. Revalidar por listagem/descrição; não assumir que todo aplicativo Beta usa esse destino.
- `aitrus-shared-prod` aparece em KMS/configuração compartilhada; isso não o torna o projeto de runtime do Aura. `southamerica-east1` pode ser a região do Artifact Registry, não a do serviço.
- Informar `--project` e, nos comandos de Cloud Run que o exigem, `--region`. Não trocar a configuração global do gcloud para investigar.

## Investigar

1. Definir a janela do incidente em `America/Sao_Paulo` e consultar timestamps com timezone explícito. Começar com serviço, janela, limite e campos relevantes.
2. Para erro HTTP, consultar request logs pelo status/endpoint. Para a causa, consultar logs da aplicação: `textPayload`, `jsonPayload.message` ou outro campo observado. Não limitar toda investigação a `severity>=ERROR`.
3. Correlacionar pelo `trace` quando disponível; caso contrário, usar horário, revisão e identificadores do incidente, declarando a limitação. A revisão atual pode ser diferente daquela que atendeu a requisição.
4. Refinar consultas que atinjam o limite ou tenham saída truncada. Confirmar sucesso do comando antes de processar JSON; saída vazia não prova saúde do serviço.
5. Se a exceção não foi registrada, declarar a lacuna e indicar a próxima evidência necessária, como resposta HTTP ou handler correspondente à versão publicada. Não repetir indefinidamente a mesma busca.

Logs de build explicam construção/deploy; logs de runtime explicam execução. Frontend e componentes Eve podem estar em outros provedores: confirmar o componente antes de procurar tudo no Google Cloud. Para promoção autorizada, usar `aura-beta-promotion`.

## Limites e relato

- Consulta somente leitura; não alterar serviço, IAM, configuração, sinks ou retenção, nem descriptografar segredos como etapa de acesso a logs.
- Em autenticação expirada, orientar o login interativo suportado. Nunca pedir senha, token ou código na conversa; após a renovação, repetir a leitura que falhou.
- Projetar somente os campos necessários. Não imprimir tokens, cookies, URLs assinadas ou payloads pessoais; mascarar dados sensíveis no relato.
- Informar projeto/serviço, revisão observada, período em horário de São Paulo, evidência objetiva e limitações. Separar erro de acesso, ausência de registros, hipótese e causa confirmada.
