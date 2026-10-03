# Promoção do backend Aura Beta

## Preflight

- Confirmar `gh auth status`, identidade ativa do `gcloud`, projeto acessível, KMS, Cloud Build e Cloud Run antes de iniciar gates demorados.
- Conferir por leitura o trigger atual: repositório `aitrus-tech/aura`, branch `^beta$`, `_APP_NAME=aura-beta`, `_ENV=prod` e estado habilitado.
- Não confundir regiões: o Artifact Registry pode estar em `southamerica-east1`; o serviço `aura-beta` do Cloud Run está em `us-central1`. Reconsultar o trigger e o serviço, pois infraestrutura pode mudar.

## Gates anteriores ao push

1. Executar a suíte normal exigida pelo projeto.
2. Descriptografar `environment/prod/application.yml.enc` somente em ambiente protegido e temporário, usando o KMS configurado pelo pipeline. Rodar a suíte completa com esse conteúdo efetivamente no classpath e sem expor valores.
3. Verificar no artefato de produção toda propriedade nova consumida por código ou testes. Corrigir e recriptografar a configuração; não enfraquecer código para mascarar chave ausente.
4. Reproduzir o build nativo em Docker antes da promoção. Para mudanças sensíveis a GraalVM — reflexão, resources, serialização, Apache POI/XMLBeans ou geração de arquivos — executar também smoke nativo do caminho exato.
5. Se a funcionalidade complexa deixou de ser necessária, reavaliar o requisito antes de acumular hints ou dependências específicas de runtime.

O `cloudbuild.yaml` substitui o YAML local pelo descriptografado. Um gate verde somente com `src/main/resources/application.yml` não representa o deploy.

## Depois do push

Localizar o Cloud Build pelo SHA promovido. Acompanhar até estado terminal:

- `Configure environment`;
- `Build image`;
- `Push image`;
- `Deploy Cloud Run`.

Em sucesso, conferir revisão `Ready`, imagem/digest do commit, 100% do tráfego esperado e logs `ERROR` da nova revisão. Não consultar apenas `/` ou `/actuator/health`: esses endpoints podem não representar disponibilidade.

Para consultar e interpretar logs do runtime, usar a skill `aura-cloud-logs`; ela cobre destino, janela, correlação e falhas de acesso. Ausência de logs `ERROR` na amostra não substitui o smoke funcional.

## Smoke

Usar autenticação Beta sem imprimir token e exercitar uma chamada de negócio relacionada à mudança. Para cotações externas, preferir rotas somente leitura, como perfil, distribuidores, representantes, lista ou detalhe, evitando criar dados apenas para provar disponibilidade. Quando uma rota foi removida, definir o contrato esperado; “não entregou o arquivo” e “retornou 404” são afirmações diferentes.
