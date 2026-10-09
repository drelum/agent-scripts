// Trecho contínuo evita capturar drawers na posição inicial de uma animação.
(async () => {
  const target = __TARGET_MS__;
  const windowId = __WINDOW_ID__;
  const deadline = Date.now() + 10000;
  while (!window.replayReady && Date.now() < deadline) {
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!window.replayReady) throw new Error('Player local não ficou pronto');
  if (windowId !== null) {
    const selector = document.getElementById('window');
    if (!selector || ![...selector.options].some(option => option.value === windowId)) {
      throw new Error('Janela solicitada não existe no player');
    }
    selector.value = windowId;
    selector.dispatchEvent(new Event('change'));
    if (!window.replayReady) throw new Error('Janela selecionada não ficou pronta');
  }
  const replayer = window.player.getReplayer();
  const duration = replayer.getMetaData().totalTime;
  if (target > duration) throw new Error('Tempo fora da janela selecionada');
  const start = Math.max(0, target - 2000);
  replayer.setConfig({ speed: 1 });
  replayer.play(start);
  await new Promise(resolve => setTimeout(resolve, target - start));
  replayer.pause();
  const doc = replayer.iframe.contentDocument;
  const view = doc.defaultView;
  function visible(element) {
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height || rect.right <= 0 || rect.bottom <= 0 ||
        rect.left >= view.innerWidth || rect.top >= view.innerHeight) return false;
    for (let node = element; node; node = node.parentElement) {
      const style = view.getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
    }
    return true; // Não prova ausência de oclusão por outro elemento.
  }
  const buttons = [...doc.querySelectorAll('button')].filter(visible);
  return {
    requested_ms: target,
    actual_ms: replayer.getCurrentTime(),
    page_viewport: { width: innerWidth, height: innerHeight },
    window_id: document.getElementById('window')?.value,
    visible_dialogs: [...doc.querySelectorAll('[role=dialog]')].filter(visible).length,
    checkout_buttons: buttons.filter(b => b.textContent.includes('Finalizar pedido'))
      .map(b => ({ disabled: b.disabled, aria_disabled: b.getAttribute('aria-disabled') })),
    blocking_message_visible: [...doc.querySelectorAll('p,span,div')]
      .some(e => !e.children.length && visible(e) && e.textContent.includes('O pedido segue bloqueado')),
    replay_errors: (window.replayErrors || []).length,
    replay_warnings: (window.replayWarnings || []).length,
    limitations: ['Janela selecionada; interseção/opacidade não provam ausência de oclusão.',
      'Conferir imagem; imagens externas podem não carregar. Não altera o DOM gravado.']
  };
})()
