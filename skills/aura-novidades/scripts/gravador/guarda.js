// Init-script da gravação de novidades: nenhuma escrita chega à API do Aura.
// Roda antes de qualquer script da página (agent-browser --init-script), em todo documento.
// Configuração injetada pelo gravador em window.__GUARDA_CFG:
//   hosts       hosts da API vigiados (os demais já são barrados por --allowed-domains);
//   leituras    regex de caminhos que usam POST só para ler (ex.: /api/v1/quote);
//   simulacoes  [{ metodo, url, status, corpo, eco }] respostas fictícias para escritas demonstradas;
//               eco: true devolve `corpo` mesclado ao JSON enviado (a tela recebe o que "salvou").
// Tudo o que não for GET/HEAD, leitura declarada ou simulação é recusado e registrado em
// window.__guarda.bloqueadas (só método e caminho, nunca query string ou corpo).
(() => {
  if (window.__guarda) return;
  const cfg = window.__GUARDA_CFG || { hosts: [], leituras: [], simulacoes: [] };
  const leituras = cfg.leituras.map((s) => new RegExp(s));
  const simulacoes = cfg.simulacoes.map((s) => ({ ...s, rx: new RegExp(s.url) }));
  const registro = { bloqueadas: [], simuladas: [] };
  window.__guarda = registro;

  const decidir = (metodo, url) => {
    const m = String(metodo || 'GET').toUpperCase();
    let alvo;
    try {
      alvo = new URL(url, location.href);
    } catch {
      return { tipo: 'livre' };
    }
    if (!cfg.hosts.includes(alvo.host)) return { tipo: 'livre' };
    const rotulo = `${m} ${alvo.pathname}`;
    if (m === 'GET' || m === 'HEAD' || m === 'OPTIONS') return { tipo: 'livre' };
    const sim = simulacoes.find((s) => s.metodo.toUpperCase() === m && s.rx.test(alvo.pathname));
    if (sim) return { tipo: 'simular', sim, rotulo };
    if (leituras.some((rx) => rx.test(alvo.pathname))) return { tipo: 'livre' };
    return { tipo: 'bloquear', rotulo };
  };

  const fetchOriginal = window.fetch.bind(window);
  window.fetch = (entrada, init = {}) => {
    const url = typeof entrada === 'string' ? entrada : entrada instanceof URL ? entrada.href : entrada.url;
    const metodo = init.method || (entrada instanceof Request ? entrada.method : 'GET');
    const d = decidir(metodo, url);
    if (d.tipo === 'livre') return fetchOriginal(entrada, init);
    if (d.tipo === 'simular') {
      registro.simuladas.push(d.rotulo);
      let enviado = {};
      if (d.sim.eco) {
        try {
          enviado = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
        } catch {
          enviado = {};
        }
      }
      const corpo = JSON.stringify({ ...(d.sim.corpo ?? {}), ...enviado });
      return Promise.resolve(new Response(corpo, { status: d.sim.status ?? 200, headers: { 'Content-Type': 'application/json' } }));
    }
    registro.bloqueadas.push(d.rotulo);
    return Promise.reject(new TypeError('gravação de novidade: escrita bloqueada'));
  };

  const abrir = XMLHttpRequest.prototype.open;
  const enviar = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (metodo, url, ...resto) {
    this.__guardaAlvo = [metodo, String(url)];
    return abrir.call(this, metodo, url, ...resto);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    const [metodo, url] = this.__guardaAlvo || ['GET', ''];
    const d = decidir(metodo, url);
    if (d.tipo !== 'livre') {
      registro.bloqueadas.push(d.rotulo);
      this.abort();
      return undefined;
    }
    return enviar.apply(this, args);
  };
})();
