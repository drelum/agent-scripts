// Overlay de demonstração injetado na página do Aura durante a gravação (agent-browser eval --stdin).
// Não altera o Aura: cria uma camada fixa com pointer-events:none contendo
//   - halo em volta do controle sob o ponteiro nativo;
//   - cartão de passo no rodapé, no desenho dos painéis do Lumina.
// API: window.AuraDemo.passo({ numero, titulo, texto }), .esconderPasso(), .destruir()
(() => {
  const ID = 'aura-demo-overlay';
  window.AuraDemo?.destruir();

  const estilo = document.createElement('style');
  estilo.textContent = `
    #${ID}{position:fixed;inset:0;z-index:2147483600;pointer-events:none;font-family:"DM Sans",ui-sans-serif,system-ui,sans-serif;
      --roxo:#7c3aed;--roxo-ink:#5b21b6;--roxo-soft:#ede9fe;--roxo-softer:#f5f3ff;--ink:#1f2937;--ink-2:#4b5563;--ink-3:#6b7280;--borda:#e5e7eb;--card:#fff}
    #${ID} *{box-sizing:border-box}
    /* halo: anel translúcido em volta do controle-alvo */
    #${ID} .halo{position:absolute;border:2px solid var(--roxo);border-radius:8px;box-shadow:0 0 0 4px rgba(124,58,237,.18),0 0 0 9999px rgba(17,24,39,0);opacity:0;transition:left 180ms ease,top 180ms ease,width 180ms ease,height 180ms ease,opacity 180ms ease}
    #${ID} .halo[data-on="true"]{opacity:1}
    /* cartão de passo: painel Lumina no rodapé esquerdo */
    #${ID} .passo{position:absolute;left:248px;bottom:28px;width:min(520px,calc(100vw - 72px));display:grid;grid-template-columns:auto 1fr;gap:14px;align-items:start;padding:14px 18px 16px;background:var(--card);border:1px solid var(--borda);border-left:4px solid var(--roxo);border-radius:8px;box-shadow:0 12px 32px rgba(31,41,55,.18);opacity:0;transform:translateY(12px);transition:opacity 260ms ease,transform 260ms cubic-bezier(.2,.8,.2,1)}
    #${ID} .passo[data-on="true"]{opacity:1;transform:translateY(0)}
    #${ID} .passo .n{width:30px;height:30px;border-radius:50%;background:var(--roxo-soft);color:var(--roxo-ink);font-weight:700;font-size:14px;display:grid;place-items:center;margin-top:2px}
    #${ID} .passo .rot{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--roxo);margin:0 0 3px}
    #${ID} .passo h2{margin:0 0 4px;font-size:19px;font-weight:600;letter-spacing:-.01em;line-height:1.2;color:var(--ink)}
    #${ID} .passo p{margin:0;font-size:14px;line-height:1.45;color:var(--ink-2)}
    #${ID} .marca{position:absolute;right:28px;bottom:28px;display:flex;align-items:center;gap:8px;padding:6px 12px;border:1px solid rgba(124,58,237,.45);border-radius:6px;background:var(--roxo-softer);color:var(--roxo-ink);font-size:12.5px;font-weight:600;opacity:0;transition:opacity 260ms ease}
    #${ID} .marca[data-on="true"]{opacity:1}
  `;
  document.head.appendChild(estilo);

  const raiz = document.createElement('div');
  raiz.id = ID;
  raiz.setAttribute('aria-hidden', 'true');
  raiz.innerHTML = `
    <div class="halo"></div>
    <section class="passo"><div class="n"></div><div><p class="rot"></p><h2></h2><p class="txt"></p></div></section>
    <div class="marca">Versão Beta · Aura</div>`;
  document.body.appendChild(raiz);

  const halo = raiz.querySelector('.halo');
  const passo = raiz.querySelector('.passo');
  const marca = raiz.querySelector('.marca');
  const ALVOS = 'button,a,input,select,textarea,[role="button"],[role="switch"],[role="tab"],[role="menuitem"],[role="menuitemcheckbox"],[role="menuitemradio"],[role="option"],[role="checkbox"],[role="radio"]';

  const mover = (x, y) => {
    const alvo = document.elementFromPoint(x, y)?.closest(ALVOS);
    if (alvo) {
      const r = alvo.getBoundingClientRect();
      halo.style.left = `${r.left - 4}px`;
      halo.style.top = `${r.top - 4}px`;
      halo.style.width = `${r.width + 8}px`;
      halo.style.height = `${r.height + 8}px`;
      halo.dataset.on = 'true';
    } else {
      halo.dataset.on = 'false';
    }
  };
  const onMove = (e) => mover(e.clientX, e.clientY);
  const onDown = () => { halo.dataset.on = 'false'; };
  document.addEventListener('pointermove', onMove, true);
  document.addEventListener('pointerdown', onDown, true);

  marca.dataset.on = 'true';

  window.AuraDemo = {
    passo({ numero, rotulo, titulo, texto }) {
      passo.querySelector('.n').textContent = numero ?? '';
      passo.querySelector('.rot').textContent = rotulo ?? `Passo ${numero ?? ''}`;
      passo.querySelector('h2').textContent = titulo ?? '';
      passo.querySelector('.txt').textContent = texto ?? '';
      passo.dataset.on = 'true';
    },
    esconderPasso() { passo.dataset.on = 'false'; },
    mover,
    destruir() { document.removeEventListener('pointermove', onMove, true); document.removeEventListener('pointerdown', onDown, true); raiz.remove(); estilo.remove(); delete window.AuraDemo; },
  };
  return 'overlay pronto';
})();
