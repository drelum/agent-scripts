// Laboratório da gravação: relógio relativo ao erro, para uso via `agent-browser eval`.
(() => {
  const meta = JSON.parse(document.getElementById('lab-meta').textContent);
  const windows = JSON.parse(document.getElementById('events').textContent);
  const selector = document.getElementById('window');
  const tag = document.getElementById('rel');
  const fmt = s => 'T' + (s >= 0 ? '+' : '−') + Math.abs(s).toFixed(1) + ' s';
  const hora = ms => new Date(ms).toLocaleTimeString('pt-BR', { timeZone: 'America/Sao_Paulo' });
  const espera = ms => new Promise(resolve => setTimeout(resolve, ms));
  let replayer = null, base = 0, current = null, avisoPedido = null;
  window.labReady = false;
  window.replayErrors = [];
  addEventListener('error', e => window.replayErrors.push(String(e.message)));

  for (const id of Object.keys(windows)) {
    const option = document.createElement('option');
    option.value = id;
    option.textContent = (id === meta.janela_erro ? 'Janela do erro · ' : 'Janela · ') + id.slice(-12);
    selector.append(option);
  }

  function mount(id) {
    if (replayer) replayer.destroy();
    document.getElementById('player').replaceChildren();
    window.player = new rrwebPlayer.Player({
      target: document.getElementById('player'),
      props: { events: windows[id], width: Math.min(1280, innerWidth - 24), height: Math.min(620, innerHeight - 120),
               autoPlay: false, skipInactive: false, showWarning: true, showController: true },
    });
    replayer = window.player.getReplayer();
    window.replayer = replayer;
    base = windows[id][0].timestamp;
    current = id;
    selector.value = id;
  }

  function estado() {
    const abs = base + replayer.getCurrentTime();
    const rel = (abs - meta.erro_ms) / 1000;
    const janela = meta.janelas[current];
    const lacuna = janela.lacunas.find(g => rel > g.de_s && rel < g.ate_s);
    let aviso = avisoPedido; // pedido fora do trecho gravado: a tela é de outro instante
    if (aviso === null) {
      if (rel > janela.fim_s) aviso = `após o fim da gravação desta janela (último evento ${fmt(janela.fim_s)})`;
      else if (rel < janela.inicio_s) aviso = `antes do início reconstruído desta janela (${fmt(janela.inicio_s)})`;
      else if (lacuna) aviso = `sem eventos gravados de ${fmt(lacuna.de_s)} a ${fmt(lacuna.ate_s)}; a tela mantém o estado de ${fmt(lacuna.de_s)}`;
    }
    return { janela: current, janela_do_erro: current === meta.janela_erro, rel_s: Number(rel.toFixed(3)),
             hora_sp: hora(abs), aviso };
  }

  function pintar() {
    const e = estado();
    tag.textContent = `erro ${meta.erro_hora_sp} · ${fmt(e.rel_s)}` + (e.aviso ? ' · ⚠ ' + e.aviso : '');
    tag.dataset.aviso = e.aviso ? 'sim' : '';
    requestAnimationFrame(pintar);
  }

  // Reproduz 2 s reais antes do alvo: com salto direto, animações CSS (gavetas, modais) ficam congeladas na
  // posição inicial e a tela não corresponde ao DOM; pause(offset) logo após montar nem posiciona.
  async function posicionar(relS) {
    const total = replayer.getMetaData().totalTime;
    const alvo = Math.min(Math.max(meta.erro_ms + relS * 1000 - base, 0), total);
    replayer.play(Math.max(0, alvo - meta.aquecimento_ms));
    const limite = Date.now() + meta.aquecimento_ms + 5000;
    while (replayer.getCurrentTime() < alvo && Date.now() < limite) await espera(10);
    replayer.pause();
    await espera(150);
  }

  window.lab = {
    info() {
      const { linha, ...resto } = meta;
      return { ...resto, janela_atual: current, uso: 'lab.ir(-5) · lab.tocar(-10, 2) · lab.linha(-30, 5) · lab.janela(id) · lab.estado()' };
    },
    async ir(relS) {
      if (!Number.isFinite(relS)) throw new Error('Informe segundos relativos ao erro, ex.: lab.ir(-5)');
      avisoPedido = null;
      await posicionar(relS);
      const atual = estado().rel_s;
      if (Math.abs(atual - relS) > 0.5) {
        avisoPedido = `pedido ${fmt(relS)} fora do trecho gravado desta janela; tela em ${fmt(atual)}`;
      }
      return { pedido_rel_s: relS, ...estado() };
    },
    async tocar(deS, ateS) {
      if (!(Number.isFinite(deS) && Number.isFinite(ateS) && ateS > deS && ateS - deS <= meta.tocar_max_s)) {
        throw new Error(`Intervalo inválido; até ${meta.tocar_max_s} s por chamada`);
      }
      await this.ir(deS);
      if (avisoPedido) throw new Error(`Início indisponível: ${avisoPedido}`);
      replayer.play(replayer.getCurrentTime());
      await espera((ateS - deS) * 1000);
      replayer.pause();
      return estado();
    },
    async janela(id) {
      if (!windows[id]) throw new Error('Janela fora deste laboratório; ver lab.info().sessao_janelas e reconstruir com --de/--ate');
      mount(id);
      avisoPedido = null;
      return this.ir(Math.min(0, meta.janelas[id].fim_s));
    },
    linha(deS = -Infinity, ateS = Infinity) {
      return (meta.linha[current] || []).filter(e => e.rel_s >= deS && e.rel_s <= ateS);
    },
    estado,
  };

  selector.onchange = () => window.lab.janela(selector.value);
  mount(meta.janela_erro);
  pintar();
  window.lab.ir(0).then(() => { window.labReady = true; });  // erro fora do gravado já abre com aviso
})();
