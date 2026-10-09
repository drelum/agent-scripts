# Primeiro acesso — pessoa nova

Read when: preparar máquina, configurar autenticação ou resolver acesso negado.

## O que instalar

| Componente | Necessário para | Autenticação |
|---|---|---|
| Python 3.11+ com base de fusos IANA | Scripts locais, HTTPS e links | Nenhuma |
| Google Cloud CLI (`gcloud`) | Logs e Secret Manager | Login individual `@aitrus.com.br` |
| Cloud SQL Auth Proxy v2 | MySQL de produção | ADC individual + impersonação `agent-read` |
| PyMySQL | Driver MySQL, único pacote Python do laboratório | IAM, senha vazia |
| PostHog CLI com subcomando `api` | Eventos, erros, usuários, metadados de replay | Chave pessoal PostHog de leitura |
| Linear CLI ou conector | Consultar/publicar ticket, quando solicitado | Conta individual com acesso ao time |
| Browser + ferramenta de inspeção | Assistir replay, etapa posterior | Sessão própria, login PostHog se online |

Infisical, SDK Google, SDK ClickHouse, SDK PostHog, MySQL CLI, Docker e BMad não são requisitos deste laboratório. TLS e URLs ClickHouse são tratados pela biblioteca padrão Python. Linux/WSL é o piloto; macOS e Windows precisam de validação própria. No Windows, instalar `tzdata` se o Python não tiver a base IANA; usar `python` em vez de `python3` conforme a instalação.

Instale as CLIs pelos projetos oficiais; confira `--version` e se o PostHog tem `api --agent-help`. O proxy precisa ser v2; não existe garantia de instalação por `gcloud components` quando gcloud veio de apt/brew. Use o binário oficial nesse caso.

- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)
- [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/mysql/sql-proxy)
- [PostHog CLI](https://github.com/PostHog/posthog/blob/master/cli/README.md)
- [PyMySQL](https://pypi.org/project/PyMySQL/)

Resolver `<skill>` pela pasta do `SKILL.md`, no clone agent-scripts ou no symlink global. Criar um ambiente virtual no diretório de trabalho (ignorar `.venv/` no Git):

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r <skill>/requirements-mysql.txt
python <skill>/scripts/incident_lab.py doctor
```

O laboratório Sentinel usa um symlink para a mesma fonte canônica. PyMySQL está fixado em 1.2.3, lançado em 17/09/2026; versão verificada no PyPI em 08/10/2026. Revalidar antes de incorporar; não atualizar ambiente global de outra pessoa.

Se `python3 -m venv` falhar com `ensurepip is not available`, falta o pacote de ambiente virtual do Python. No Ubuntu/Debian, instalar `python3-venv` (ou a variante da versão, como `python3.12-venv`) pelo gerenciador do sistema, com administrador se necessário; depois recriar o ambiente virtual. Doctor reporta `venv_bootstrap_available=false` nesse caso. Não continuar o comando pip dentro de um venv incompleto nem instalar no Python global para contornar o erro.

## Conta Google: um login atualiza as duas credenciais

```bash
gcloud auth login seu.usuario@aitrus.com.br --update-adc
```

O login normal autentica `gcloud logging` e `gcloud secrets`; `--update-adc` também grava a credencial ADC usada pelo proxy. Assim, a pessoa não precisa de dois comandos. Confirmado no gcloud instalado e na [referência oficial](https://docs.cloud.google.com/sdk/gcloud/reference/auth/login) em 08/10/2026. Ele atualiza a ADC existente com essa conta; quando for preciso refazer a autorização no browser mesmo com credencial CLI ainda válida, acrescentar `--force`.

Alternativa, quando quiser atualizar somente ADC: `gcloud auth application-default login`, escolhendo a mesma conta Aitrus. Os dois conjuntos de credenciais continuam independentes; `gcloud auth login` sem `--update-adc` não renova a ADC. Faça o login interativamente na máquina onde os scripts rodam. Conta logada não prova permissão nem token ainda válido. Não passar token por argumento, não imprimir `print-access-token` no terminal e não compartilhar JSON de credencial.

O proxy do script remove `GOOGLE_APPLICATION_CREDENTIALS` apenas do seu subprocesso para evitar que uma chave de aplicação substitua sua ADC. Não altera a variável no terminal nem reutiliza proxy existente. Abre porta própria em `127.0.0.1`, encerra somente seu processo após a consulta, sem servidor permanente.

## Permissões: o administrador concede uma vez

| Fonte | Acesso necessário | Quem concede |
|---|---|---|
| Cloud Logging | `roles/logging.viewer` nos projetos consultados | Responsável pela infraestrutura |
| Secret Manager | `roles/secretmanager.secretAccessor` no segredo ClickHouse de leitura | Responsável pela infraestrutura |
| Proxy MySQL | `roles/iam.serviceAccountTokenCreator` na SA `agent-read`; SA com `cloudsql.client` e `cloudsql.instanceUser` | Responsável pela infraestrutura |
| MySQL | Usuário IAM `agent-read` com papel `role_read_only` e grants nos bancos pertinentes | DBA/infraestrutura |
| ClickHouse | `agent_read` com SELECT nos bancos pertinentes | DBA/infraestrutura |
| PostHog | Membro do projeto 331102; chave pessoal com leitura das ferramentas usadas | Administrador PostHog/pessoa usuária |

Não rodar Terraform, CREATE USER, GRANT ou habilitar APIs durante investigação. Os padrões estão em `plataforma/infraestrutura/acesso-a-dados/README.md` e `aitrus/tecnologia/decisoes/0003-acesso-a-dados-e-segredos.md` do Context; validar a implementação de cada grant, sem inferir que toda a documentação já foi aplicada.

## ClickHouse: sem Infisical

`config.example.json` contém apenas nomes públicos, endpoints e IDs. O padrão lê a senha de `clickhouse-agent-read-password` no projeto `aitrus-shared-prod` via `gcloud`, em memória, sem arquivo nem argumento de processo. Credencial de produção e host nunca devem ser combinados automaticamente a partir de arquivos desconhecidos.

Alternativa explícita: seu cofre de segredos injeta `INCIDENT_CLICKHOUSE_PASSWORD` no processo; Infisical pode fazer isso, mas não é obrigatório. Não colar valores no comando nem na conversa. Se o endpoint for diferente, use `--config <arquivo>` com usuário/host aprovados; não apontar senha de produção para endpoint de teste.

## PostHog

```bash
posthog-cli --host https://us.posthog.com login
posthog-cli api --agent-help
```

O login recebe a chave pessoal e a guarda no armazenamento do CLI. Não é o token de captura do frontend. Selecione projeto **331102**. Para automação, o cofre injeta `POSTHOG_CLI_API_KEY`; o script passa projeto/host da configuração e confirma `project-get` antes de buscar uma sessão. Não lê nem exporta o arquivo de credenciais do CLI.

Habilite apenas escopos de leitura pedidos pelas ferramentas: projeto, consultas, pessoas, Error Tracking e session recordings, conforme o painel atual. Um `403` em eventos/replay pode acontecer mesmo com `project-get` funcionando. Não ampliar para escrita para solucionar leitura; registrar qual ferramenta/escopo faltou.

## Verificação sem dados de cliente

```bash
python <skill>/scripts/incident_lab.py doctor --live
```

Esse comando renova tokens em memória, executa SELECT 1/identidade no ClickHouse e MySQL, verifica projeto PostHog e testa autorização para ler logs sem projetar mensagens. Uma fonte bloqueada não impede testar as demais. Código 2 indica alguma verificação bloqueada; não significa erro de produto. Login, ADC e fontes aparecem separados. Nenhum token é exibido.

Limitação atual das consultas MySQL: o limite do servidor usa tabela derivada, que exige nomes de coluna únicos. Projete campos explícitos com aliases distintos; evitar `SELECT *` em joins. Um SELECT válido com nomes repetidos pode falhar com erro 1060 neste laboratório. Isso não é diagnóstico de falha do produto; o suporte a essas consultas precisa ser resolvido antes da incorporação definitiva.

| Resultado | Próxima ação |
|---|---|
| Ferramenta ausente | Instalar a ferramenta pertinente; repetir doctor |
| Login/ADC ausente ou expirado | Refazer o login interativo correspondente |
| Acesso negado | Conferir conta/projeto; pedir o grant específico ao administrador |
| Proxy falhou | Conferir ADC, impersonação e egress 443/3307; seguir guia Cloud SQL |
| Consulta excede limite | Reduzir campos/período ou paginar por chave; não chamar amostra de total |
| Replay não encontrado | Registrar ausência/retention; usar eventos/logs disponíveis |
