#!/usr/bin/env python3
"""Embaça regiões fixas de identificação em capturas do Aura já existentes.

Uso: python3 ~/Projects/agent-scripts/skills/aura-novidades/scripts/mascara-png.py <entrada.png> [<saida.png>] [--regiao x0,y0,x1,y1 ...]

Regiões padrão (layout do Aura com sidebar aberta): seletor de loja no canto superior direito e
bloco do usuário no canto inferior esquerdo, escaladas pela largura da imagem (base 1366 px).
Use --regiao para textos em outras posições (ex.: "Grupo …" numa página específica).
Prefira mascarar no DOM antes da captura (mascara.js ao lado); este script é o último recurso.
"""
import sys
from PIL import Image, ImageFilter

BASE_LARGURA = 1366
REGIOES_PADRAO = [
    (1128, 3, 1362, 47),   # seletor de loja (nome + CNPJ), topo direito
    (10, 708, 216, 766),   # usuário (nome + e-mail), rodapé da sidebar
]


def embacar(img, caixa, raio=9):
    x0, y0, x1, y1 = [max(0, v) for v in caixa]
    x1, y1 = min(x1, img.width), min(y1, img.height)
    if x1 <= x0 or y1 <= y0:
        return
    parte = img.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(raio))
    img.paste(parte, (x0, y0))


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    entrada = argv[1]
    saida = argv[2] if len(argv) > 2 and not argv[2].startswith('--') else entrada
    extras = []
    if '--regiao' in argv:
        for i, a in enumerate(argv):
            if a == '--regiao':
                extras.append(tuple(int(v) for v in argv[i + 1].split(',')))
    img = Image.open(entrada).convert('RGB')
    escala = img.width / BASE_LARGURA
    altura_base = 768
    for x0, y0, x1, y1 in REGIOES_PADRAO:
        # topo escala pela largura; rodapé ancora na altura real da imagem
        if y0 > altura_base / 2:
            dy = img.height - altura_base * escala
            caixa = (x0 * escala, y0 * escala + dy, x1 * escala, y1 * escala + dy)
        else:
            caixa = (x0 * escala, y0 * escala, x1 * escala, y1 * escala)
        embacar(img, tuple(int(v) for v in caixa))
    for caixa in extras:
        embacar(img, caixa)
    img.save(saida, optimize=True)
    print(f'{saida}: {2 + len(extras)} regiões embaçadas')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
