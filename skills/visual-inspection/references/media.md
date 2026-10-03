# Evidência com screenshots, snapshots e vídeo

Ler ao escolher a mídia de um critério ou preparar um handoff com prova temporal. A execução de QA permanece no worker `visual-inspection`.

| Critério | Evidência |
| --- | --- |
| Texto, alinhamento, cor, estado final | Screenshot obrigatório, aberto e inspecionado. |
| Carregamento, arraste, animação, foco transitório, toast, flicker | Vídeo contínuo do trecho, intervalo citado e quadros dos momentos relevantes. |
| Localizar controles e acompanhar DOM | Snapshot; ampliar além de `-i` quando precisar de texto estático. |
| Persistência no servidor | Evidência visual e confirmação pertinente de API/dados. |

## Captura

Carregar `agent-browser skills get core` da versão instalada. Usar sessão exclusiva e viewport 1366×768 salvo outra dimensão explicitamente requerida. Confirmar autenticação e URL sem segredos antes de gravar.

Na mesma sessão, preparar a página, iniciar `record start /caminho/fluxo.mp4 --fps 30 --cursor --contact-sheet` sem URL, executar o gesto, aguardar o resultado observável e chamar `record stop`. Finalizar a gravação antes de fechar a sessão, inclusive em saída antecipada. Não gravar todos os testes indiscriminadamente: o critério define a necessidade. Não aplicar cartões editoriais ou máscaras que alterem o comportamento sob teste.

Usar `snapshot -i -c -d 3 --delta` para acompanhamento; manter o mesmo escopo e pedir `--delta --full` quando precisar restabelecer a base. Observar novamente após navegação e substituição de elementos. Refs preservadas não dispensam conferir o estado atual.

Usar `screenshot --if-changed` em observações intermediárias. Sem mudança pode não haver caminho novo; não inventar artefato nem apresentar imagem anterior como captura atual. Para prova final, capturar PNG explicitamente. `snapshot --full` renova o texto; não confundir com `screenshot --full`, que não é usado no WSL deste workspace.

## Aceitação

- Verificar dimensões, duração positiva e decodificação do vídeo (`ffprobe` e `ffmpeg -v error -xerror -i arquivo.mp4 -f null -`). Um arquivo existente não basta.
- No laudo, citar o arquivo em `Evidências` e os intervalos nos critérios. Guardar MP4, folha de contato e quadros no diretório daquela execução.
- Abrir os screenshots e quadros extraídos. Para um evento rápido, extrair a sequência ao redor dele com frequência suficiente; a folha de contato não representa todos os frames.
- O agente principal confere as imagens citadas e as evidências dos critérios temporais. Se não for possível observar a sequência necessária, registrar a limitação e não aceitar PASS desse critério.
- Gravação incompleta, arquivo inválido, falta do estado inicial ou ausência de prova do resultado deixam o critério BLOCKED; preservar FAIL se o defeito já foi demonstrado.
- Capturas finais de layout devem estar livres de overlays que encubram o objeto avaliado. Cursor animado pode produzir diferenças de pixels sem mudança na aplicação.
