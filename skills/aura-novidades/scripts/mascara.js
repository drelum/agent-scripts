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
    ['Genivaldo Oliveira (sabara Mg)', 'Grupo Modelo'],
    ['Genivaldo Oliveira (Sabara MG)', 'Grupo Modelo'],
    ['Genivaldo Oliveira', 'Grupo Modelo'],
    ['Drogarias Da Vovo', 'Farmácia Modelo'],
    ['DROGARIAS DA VOVO', 'FARMÁCIA MODELO'],
    ['Drogaria da Vovó', 'Farmácia Modelo'],
    ['andre@aitrus.com.br', 'gestor@farmaciamodelo.com.br'],
    ['Andre Monteiro', 'Gestor da Loja'],
  ];
  const CNPJ_FORMATADO = /\b\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}\b/g;
  const CNPJ_DIGITOS = /\b\d{14}\b/g;
  const CNPJ_MASCARA = '00.000.000/0001-00';

  let trocas = 0;
  const aplicar = (texto) => {
    let novo = texto;
    for (const [de, para] of ALVOS) novo = novo.split(de).join(para);
    novo = novo.replace(CNPJ_FORMATADO, CNPJ_MASCARA).replace(CNPJ_DIGITOS, CNPJ_MASCARA.replace(/\D/g, ''));
    if (novo !== texto) trocas += 1;
    return novo;
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
    }
    for (const el of raiz.querySelectorAll('*')) if (el.shadowRoot) raizes.push(el.shadowRoot);
  };
  while (raizes.length) percorrer(raizes.shift());

  // 2. Atributos visíveis e valores de inputs.
  for (const el of document.querySelectorAll('[title],[placeholder],[aria-label],input,textarea')) {
    for (const attr of ['title', 'placeholder', 'aria-label']) {
      const v = el.getAttribute(attr);
      if (v) el.setAttribute(attr, aplicar(v));
    }
    if ('value' in el && typeof el.value === 'string' && el.value) el.value = aplicar(el.value);
  }

  // 3. Verificação: nada sensível pode restar no texto visível.
  const texto = document.body.innerText;
  const restos = [];
  for (const [de] of ALVOS) if (texto.includes(de)) restos.push(de);
  const cnpjs = [...texto.matchAll(CNPJ_FORMATADO), ...texto.matchAll(CNPJ_DIGITOS)]
    .map((m) => m[0])
    .filter((c) => c !== CNPJ_MASCARA && c !== CNPJ_MASCARA.replace(/\D/g, ''));
  if (cnpjs.length) restos.push(`CNPJ: ${[...new Set(cnpjs)].join(', ')}`);
  return JSON.stringify({ trocas, restos });
})();
