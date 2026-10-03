// Init-script da gravação de novidades: halo discreto em volta do controle sob o ponteiro.
// Sem selo, sem cartão sobre a interface: a legenda de cada passo entra na montagem, numa faixa
// fora da tela do Aura. Camada inerte (pointer-events:none), ausente da árvore de acessibilidade.
(() => {
  if (window.__palco) return;
  window.__palco = true;
  const ALVOS = 'button,a,input,select,textarea,[role="button"],[role="tab"],[role="menuitem"],[role="option"],[role="checkbox"],[role="combobox"]';
  const montar = () => {
    const estilo = document.createElement('style');
    estilo.textContent = `#aura-palco{position:fixed;inset:0;z-index:2147483600;pointer-events:none}
#aura-palco .halo{position:absolute;border:2px solid #7c3aed;border-radius:8px;box-shadow:0 0 0 4px rgba(124,58,237,.18);opacity:0;transition:left 160ms ease,top 160ms ease,width 160ms ease,height 160ms ease,opacity 160ms ease}
#aura-palco .halo[data-on="true"]{opacity:1}
#aura-palco .clique{position:absolute;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;border:3px solid #7c3aed;background:rgba(124,58,237,.18);animation:aura-clique 750ms ease-out forwards}
@keyframes aura-clique{from{transform:scale(.8);opacity:1}40%{transform:scale(1.1);opacity:1}to{transform:scale(1.6);opacity:0}}`;
    document.head.appendChild(estilo);
    const raiz = document.createElement('div');
    raiz.id = 'aura-palco';
    raiz.setAttribute('aria-hidden', 'true');
    raiz.innerHTML = '<div class="halo"></div>';
    document.body.appendChild(raiz);
    const halo = raiz.firstElementChild;
    document.addEventListener(
      'pointermove',
      (e) => {
        const alvo = document.elementFromPoint(e.clientX, e.clientY)?.closest(ALVOS);
        if (!alvo) {
          halo.dataset.on = 'false';
          return;
        }
        const r = alvo.getBoundingClientRect();
        Object.assign(halo.style, { left: `${r.left - 4}px`, top: `${r.top - 4}px`, width: `${r.width + 8}px`, height: `${r.height + 8}px` });
        halo.dataset.on = 'true';
      },
      true,
    );
    // anel no ponto do clique: marca o gesto no vídeo mesmo quando a tela muda logo em seguida
    document.addEventListener(
      'pointerdown',
      (e) => {
        halo.dataset.on = 'false';
        const anel = document.createElement('div');
        anel.className = 'clique';
        Object.assign(anel.style, { left: `${e.clientX}px`, top: `${e.clientY}px` });
        raiz.appendChild(anel);
        setTimeout(() => anel.remove(), 800);
      },
      true,
    );
  };
  if (document.body) montar();
  else document.addEventListener('DOMContentLoaded', montar, { once: true });
})();
