// Mascara dados de identificação na página ANTES da captura de tela.
// Uso (agent-browser, com a página já aberta e carregada):
//   agent-browser eval "$(cat ~/Projects/agent-scripts/skills/aura-novidades/scripts/mascara.js)"
// (ou via `nov_shot` de aura-novidades-capturar, que aplica e verifica antes de capturar)
// Retorna um resumo: quantas substituições foram feitas e o que ainda restou (deve ser vazio).
//
// Estratégia: substituir texto no DOM por valores fictícios estáveis, em vez de tarja/embaçado —
// a tela continua legível e não chama atenção para o que foi escondido. Cobre:
//   1. cadeias conhecidas (loja, grupo econômico, usuário) listadas em ALVOS;
//   2. qualquer CNPJ, formatado ou só dígitos, por expressão regular;
//   3. atributos visíveis (title, placeholder, aria-label, value de inputs).
(() => {
  // Substituições explícitas: loja/grupo/usuário do ambiente Beta local. Acrescente novos pares
  // quando capturar em outro contexto; a ordem importa (cadeias mais longas primeiro).
  const ALVOS = [
    ['Drogarias Da Vovo', 'Farmácia Modelo'],
    ['DROGARIAS DA VOVO', 'FARMÁCIA MODELO'],
    ['Drogaria da Vovó', 'Farmácia Modelo'],
    ['andre@aitrus.com.br', 'gestor@farmaciamodelo.com.br'],
    ['Andre Monteiro', 'Gestor da Loja'],
    ['Rafael', 'Gestor da Loja'],
    // representantes comerciais cadastrados no ambiente de testes (pessoas): nomes fictícios
    ['André Luís', 'Rep. Silva'],
    ['Cavalcante', 'Rep. Souza'],
    ['Roni Opella', 'Rep. Lima'],
    ['Lincoln', 'Rep. Costa'],
  ];
  // variações da loja de testes que não batem por cadeia exata (singular, maiúsculas, acento)
  const LOJA_REGEX = /drogarias?\s+da\s+vov[oó]/gi;
  const GRUPO_REGEX = /genivaldo\s+oliveira(?:\s*\(sabara\s+mg\))?/gi;
  // Outras redes usadas em demonstrações (Itufarma: caso real de EAN irmão, BETA-158).
  const OUTRAS = [
    [/itufarma\s+drogaria\s+ltda/gi, 'Farmácia Modelo Ltda'],
    [/itufarma/gi, 'Farmácia Modelo'],
    [/grupo\s+sereia/gi, 'Grupo Modelo'],
    [/retail\s+jedi/gi, 'Rede Modelo'],
  ];
  // Máscara extra por gravação (demonstração de rede): window.__MASCARA_EXTRA = { pares: [[de, para]],
  // notas: true }, injetado pelo gravador a partir de `mascara_extra` do roteiro. `pares` vira uma
  // única expressão (listas de milhares de lojas e grupos); `notas` troca número de nota isolado
  // (célula só com 5–9 dígitos) por "000000".
  const EXTRA = window.__MASCARA_EXTRA || { pares: [] };
  const escapar = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const EXTRA_MAPA = new Map(EXTRA.pares);
  const EXTRA_RX = EXTRA.pares.length
    ? new RegExp(
        `(?<![\\p{L}\\d])(?:${[...EXTRA_MAPA.keys()].sort((a, b) => b.length - a.length).map(escapar).join('|')})(?![\\p{L}\\d])`,
        'gu',
      )
    : null;
  const NOTA = /^\s*\d{5,9}\s*$/;
  // Iniciais do avatar do usuário de testes ("AM"), que não batem por cadeia dentro de texto maior.
  const INICIAIS = new Map([['AM', 'GL']]);
  const caixa = (original, troca) => (original === original.toUpperCase() ? troca.toUpperCase() : troca);
  const lojaMascara = (m) => (m === m.toUpperCase() ? 'FARMÁCIA MODELO' : 'Farmácia Modelo');
  const grupoMascara = (m) => (m === m.toUpperCase() ? 'GRUPO MODELO' : 'Grupo Modelo');
  const CNPJ_FORMATADO = /\b\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}\b/g;
  const CNPJ_DIGITOS = /\b\d{14}\b/g;
  const CNPJ_MASCARA = '00.000.000/0001-00';
  // telefones de representantes e usuários: (31) 98430-8595, 31 3333-4444
  const TELEFONE = /\(?\b\d{2}\)?\s?9?\d{4}-\d{4}\b/g;
  const TELEFONE_MASCARA = '(00) 00000-0000';

  let trocas = 0;
  const aplicar = (texto) => {
    let novo = texto;
    if (EXTRA_RX) novo = novo.replace(EXTRA_RX, (m) => EXTRA_MAPA.get(m) ?? m);
    if (EXTRA.notas && NOTA.test(novo)) novo = novo.replace(/\d{5,9}/, '000000');
    for (const [de, para] of ALVOS) novo = novo.split(de).join(para);
    novo = novo.replace(LOJA_REGEX, lojaMascara);
    novo = novo.replace(GRUPO_REGEX, grupoMascara);
    for (const [rx, troca] of OUTRAS) novo = novo.replace(rx, (m) => caixa(m, troca));
    if (INICIAIS.has(novo.trim())) novo = INICIAIS.get(novo.trim());
    novo = novo.replace(TELEFONE, (m) => (m === TELEFONE_MASCARA ? m : TELEFONE_MASCARA));
    novo = novo.replace(CNPJ_FORMATADO, CNPJ_MASCARA).replace(CNPJ_DIGITOS, CNPJ_MASCARA.replace(/\D/g, ''));
    if (novo !== texto) trocas += 1;
    return novo;
  };

  // Inputs controlados podem receber `.value = ...` sem mutação observável. Interceptar o setter
  // evita que um valor sensível chegue sequer a um quadro pintado antes do próximo polling.
  if (!window.__mascaraValueSetters) {
    for (const Tipo of [HTMLInputElement, HTMLTextAreaElement]) {
      const descriptor = Object.getOwnPropertyDescriptor(Tipo.prototype, 'value');
      if (!descriptor?.get || !descriptor?.set || !descriptor.configurable) continue;
      Object.defineProperty(Tipo.prototype, 'value', {
        ...descriptor,
        set(valor) {
          descriptor.set.call(this, typeof valor === 'string' ? aplicar(valor) : valor);
        },
      });
    }
    window.__mascaraValueSetters = true;
  }

  // Rótulo "Grupo" seguido do nome mascarado viraria "Grupo Grupo Modelo": o nome vira só "Modelo".
  const GRUPO_MASCARA = /^\s*(grupo modelo)\s*$/i;
  const textoAnterior = (no) => {
    for (let atual = no; atual && atual !== document.body; atual = atual.parentNode) {
      let irmao = atual.previousSibling;
      while (irmao && !irmao.textContent.trim()) irmao = irmao.previousSibling;
      if (irmao) return irmao.textContent;
    }
    return '';
  };
  const ajustarRotuloGrupo = (no) => {
    if (!GRUPO_MASCARA.test(no.nodeValue || '')) return;
    if (!/\bgrupo\s*:?\s*$/i.test(textoAnterior(no))) return;
    no.nodeValue = no.nodeValue.replace(/grupo modelo/i, (m) => (m === m.toUpperCase() ? 'MODELO' : 'Modelo'));
  };

  // 1. Nós de texto (inclui shadow roots abertos).
  const raizes = [document];
  const percorrer = (raiz) => {
    const walker = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
    const nos = [];
    while (walker.nextNode()) nos.push(walker.currentNode);
    for (const no of nos) {
      if (no.parentElement && ['SCRIPT', 'STYLE'].includes(no.parentElement.tagName)) continue;
      no.nodeValue = aplicar(no.nodeValue);
      ajustarRotuloGrupo(no);
    }
    for (const el of raiz.querySelectorAll('*')) if (el.shadowRoot) raizes.push(el.shadowRoot);
  };
  while (raizes.length) percorrer(raizes.shift());

  const mascararElemento = (el) => {
    if (!(el instanceof Element)) return;
    for (const attr of ['title', 'placeholder', 'aria-label']) {
      const v = el.getAttribute(attr);
      const novo = v ? aplicar(v) : v;
      if (v && novo !== v) el.setAttribute(attr, novo);
    }
    if ('value' in el && typeof el.value === 'string' && el.value) {
      const novo = aplicar(el.value);
      if (novo !== el.value) el.value = novo;
      const atributo = el.getAttribute('value');
      const novoAtributo = atributo ? aplicar(atributo) : atributo;
      if (atributo && novoAtributo !== atributo) el.setAttribute('value', novoAtributo);
    }
  };

  const mascararElementos = (raiz) => {
    if (raiz instanceof Element) mascararElemento(raiz);
    for (const el of raiz.querySelectorAll('[title],[placeholder],[aria-label],input,textarea')) {
      mascararElemento(el);
    }
  };

  // 2. Atributos visíveis e valores de inputs.
  mascararElementos(document);

  // 2b. Observador: conteúdo renderizado depois (painéis, menus, rotas SPA) também é mascarado.
  //     Ligado uma vez por página; idempotente porque a substituição não altera texto já mascarado.
  if (!window.__mascaraObservador) {
    const mascararNo = (no) => {
      if (no.nodeType === Node.TEXT_NODE) {
        if (!no.parentElement || ['SCRIPT', 'STYLE'].includes(no.parentElement.tagName)) return;
        const novo = aplicar(no.nodeValue);
        if (novo !== no.nodeValue) no.nodeValue = novo;
        ajustarRotuloGrupo(no);
        return;
      }
      if (no.nodeType !== Node.ELEMENT_NODE) return;
      mascararElemento(no);
      const w = document.createTreeWalker(no, NodeFilter.SHOW_TEXT);
      const nos = [];
      while (w.nextNode()) nos.push(w.currentNode);
      nos.forEach(mascararNo);
      mascararElementos(no);
    };
    window.__mascaraObservador = new MutationObserver((mutacoes) => {
      for (const m of mutacoes) {
        if (m.type === 'characterData') mascararNo(m.target);
        if (m.type === 'attributes') mascararElemento(m.target);
        for (const n of m.addedNodes) mascararNo(n);
      }
    });
    window.__mascaraObservador.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['title', 'placeholder', 'aria-label', 'value'],
    });
    // React e outros frameworks podem trocar a propriedade `value` sem mutar o atributo.
    window.__mascaraIntervalo = window.setInterval(() => mascararElementos(document), 100);
  }

  const verificar = () => {
    const partes = [document.body.innerText];
    for (const el of document.querySelectorAll('[title],[placeholder],[aria-label],input,textarea')) {
      for (const attr of ['title', 'placeholder', 'aria-label', 'value']) {
        const v = el.getAttribute(attr);
        if (v) partes.push(v);
      }
      if ('value' in el && typeof el.value === 'string' && el.value) partes.push(el.value);
    }
    const texto = partes.join('\n');
    const restos = [];
    for (const [de] of ALVOS) if (texto.includes(de)) restos.push(de);
    if (EXTRA_RX) {
      EXTRA_RX.lastIndex = 0;
      if (EXTRA_RX.test(texto)) restos.push('máscara extra');
      EXTRA_RX.lastIndex = 0;
    }
    if (LOJA_REGEX.test(texto)) restos.push('loja (variação)');
    LOJA_REGEX.lastIndex = 0;
    if (GRUPO_REGEX.test(texto)) restos.push('grupo (variação)');
    GRUPO_REGEX.lastIndex = 0;
    for (const [rx] of OUTRAS) {
      if (rx.test(texto)) restos.push('outra rede (variação)');
      rx.lastIndex = 0;
    }
    const cnpjs = [...texto.matchAll(CNPJ_FORMATADO), ...texto.matchAll(CNPJ_DIGITOS)]
      .map((m) => m[0])
      .filter((c) => c !== CNPJ_MASCARA && c !== CNPJ_MASCARA.replace(/\D/g, ''));
    const telefones = [...texto.matchAll(TELEFONE)].map((m) => m[0]).filter((t) => t !== TELEFONE_MASCARA);
    if (telefones.length) restos.push('telefone');
    if (cnpjs.length) restos.push(`CNPJ: ${[...new Set(cnpjs)].join(', ')}`);
    return JSON.stringify({ trocas, restos });
  };
  window.__mascaraAplicar = () => {
    raizes.push(document);
    while (raizes.length) percorrer(raizes.shift());
    mascararElementos(document);
  };
  window.__mascaraVerificar = verificar;
  return verificar();
})();
