"""Gera as versões transparentes dos logos da biblioteca: cor original e branca (para o fundo azul escuro).

Lê post/logos/original/<código>.png (placa opaca da coleção), estima a cor de fundo pela borda e tira esse fundo por
"cor para alfa": o que é da cor do fundo some, as bordas suaves viram transparência parcial e as cores da marca ficam
como eram sobre o fundo. A versão branca usa a mesma máscara, com tudo em branco e o alfa reforçado (traço cinza claro
fica sólido). Corta a sobra e grava:

    post/logos/cor/<código>.png      cor original, fundo transparente
    post/logos/branco/<código>.png   branco, fundo transparente
    post/logos/tamanhos.json         largura e altura úteis de cada logo
    post/logos/indice.csv            colunas fundo (uniforme ou não) e capa (versão usada na capa) atualizadas

A capa usa a versão branca; quando a branca vira um bloco sem detalhe (forma cheia com texto em outra cor, como o
quadrado do Itaú), a coluna capa indica "cor".

Fundo não uniforme (degradê, foto) não tem como ser tirado por cor: o logo fica marcado "verificar" no índice.
Uso: python3 -I post/versoes.py post/logos
"""
import csv
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

MORTA = 0.06        # fundo branco: diferença abaixo disso é ruído de compressão e fica transparente
MORTA_COR = 0.25    # placa colorida: o JPEG deixa mais ruído em volta das letras
REFORCO = 0.45      # versão branca: alfa a partir disso vira sólido
UNIFORME = 12.0     # desvio padrão máximo da borda (0 a 255) para considerar o fundo liso


def perde_detalhe(frente: np.ndarray, alfa: np.ndarray) -> bool:
    """Versão branca vira bloco: forma cheia com detalhe interno em outra cor (ex.: Itaú, texto amarelo no quadrado azul)."""
    solido = alfa > 0.6
    rot, n = ndimage.label(alfa > 0.5)
    if n == 0:
        return False
    total = (rot > 0).sum()
    for i, sl in enumerate(ndimage.find_objects(rot), 1):
        comp = rot[sl] == i
        area = comp.sum()
        if area < 0.05 * total:
            continue
        cheio = area / comp.size
        px = frente[sl][comp & solido[sl]]
        if len(px) < 50:
            continue
        dom = np.median(px, axis=0)
        mistura = (np.abs(px - dom).max(axis=1) > 0.25).mean()
        if cheio > 0.7 and mistura > 0.08:
            return True
    return False


def cor_para_alfa(im: Image.Image):
    a = np.asarray(im.convert("RGBA")).astype(np.float64) / 255.0
    rgb = a[..., :3]
    borda = np.concatenate([rgb[:3].reshape(-1, 3), rgb[-3:].reshape(-1, 3), rgb[:, :3].reshape(-1, 3), rgb[:, -3:].reshape(-1, 3)])
    fundo = np.median(borda, axis=0)
    desvio = float(borda.std(axis=0).max() * 255)
    acima = (rgb - fundo) / np.maximum(1.0 - fundo, 1e-6)
    abaixo = (fundo - rgb) / np.maximum(fundo, 1e-6)
    alfa = np.where(rgb >= fundo, acima, abaixo).max(axis=2)
    if fundo.min() > 0.9:
        alfa = np.clip((alfa - MORTA) / (1.0 - MORTA), 0.0, 1.0)
    else:
        # placa colorida: o JPEG borra a cor (croma) em volta das letras, mas quase não mexe no brilho. O alfa vem do
        # brilho; diferença só de cor precisa ser grande para contar. Mediana 3x3 tira os pontos soltos.
        lum = rgb @ np.array([0.299, 0.587, 0.114])
        lf = float(fundo @ np.array([0.299, 0.587, 0.114]))
        alfa_l = np.abs(lum - lf) / max(lf, 1.0 - lf, 1e-6)
        alfa = np.maximum(np.clip((alfa_l - 0.12) / 0.88, 0, 1), np.clip((alfa - 0.45) / 0.55, 0, 1))
        alfa = ndimage.median_filter(alfa, size=3)
        # pontos soltos: manchas pequenas e fracas longe do desenho (letras e símbolos são maiores ou mais sólidos)
        rot, n = ndimage.label(alfa > 0.1)
        if n:
            area = ndimage.sum(np.ones_like(alfa), rot, index=np.arange(1, n + 1))
            pico = ndimage.maximum(alfa, rot, index=np.arange(1, n + 1))
            tira = np.zeros(n + 1, bool)
            tira[1:] = (area < 0.0004 * alfa.size) & (pico < 0.75) | (area < 0.00008 * alfa.size)
            alfa[tira[rot]] = 0.0
    alfa = alfa * a[..., 3]
    com = alfa[..., None] > 1e-3
    frente = np.where(com, fundo + (rgb - fundo) / np.maximum(alfa[..., None], 1e-3), 0.0)
    frente = np.clip(frente, 0.0, 1.0)
    return frente, alfa, desvio


def recorte(alfa: np.ndarray):
    ys, xs = np.where(alfa > 0.04)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def salvar(rgb, alfa, bb, caminho):
    x0, y0, x1, y1 = bb
    arr = np.dstack([rgb[y0:y1, x0:x1], alfa[y0:y1, x0:x1]])
    pad = max(2, round(max(x1 - x0, y1 - y0) * 0.02))
    im = Image.fromarray((arr * 255).round().astype("uint8"), "RGBA")
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    out.paste(im, (pad, pad))
    out.save(caminho, optimize=True)
    return [out.width, out.height]


def main() -> None:
    base = sys.argv[1]
    orig, cor, branco = (os.path.join(base, p) for p in ("original", "cor", "branco"))
    os.makedirs(cor, exist_ok=True)
    os.makedirs(branco, exist_ok=True)
    tam, fundo_info, capa = {}, {}, {}
    for f in sorted(os.listdir(orig)):
        cod, ext = os.path.splitext(f)
        if ext.lower() != ".png":
            continue
        frente, alfa, desvio = cor_para_alfa(Image.open(os.path.join(orig, f)))
        bb = recorte(alfa)
        if bb is None:
            fundo_info[cod] = "vazio"
            continue
        tam[cod] = salvar(frente, alfa, bb, os.path.join(cor, f))
        salvar(np.ones_like(frente), np.clip(alfa / REFORCO, 0.0, 1.0), bb, os.path.join(branco, f))
        cobre = float((alfa > 0.5).mean())  # fundo que não saiu cobre a placa quase toda
        fundo_info[cod] = "uniforme" if desvio <= UNIFORME and cobre < 0.5 else f"não uniforme ({desvio:.0f}, cobre {cobre:.0%})"
        capa[cod] = "cor" if perde_detalhe(frente, alfa) else "branco"
    json.dump(tam, open(os.path.join(base, "tamanhos.json"), "w"), indent=0)

    ind = os.path.join(base, "indice.csv")
    rows = list(csv.DictReader(open(ind, encoding="utf-8"), delimiter=";"))
    campos = list(rows[0].keys()) if rows else []
    for novo in ("fundo", "capa"):
        if novo not in campos:
            campos.insert(campos.index("status"), novo)
    for r in rows:
        r["fundo"] = fundo_info.get(r["codigo"], "sem arquivo")
        if r.get("capa") != "placa":  # "placa" é escolha manual (ruído de compressão): não sobrescrever
            r["capa"] = capa.get(r["codigo"], "")
        if r["status"].startswith("verificar: fundo não uniforme") and r["fundo"] == "uniforme":
            r["status"] = "ok"
        if r["fundo"] != "uniforme" and r["status"] == "ok":
            r["status"] = "verificar: fundo não uniforme, a transparência pode ter falhado"
    w = csv.DictWriter(open(ind, "w", encoding="utf-8", newline=""), fieldnames=campos, delimiter=";")
    w.writeheader()
    w.writerows(rows)
    nu = sum(1 for v in fundo_info.values() if v != "uniforme")
    print(f"{len(tam)} logos em cor e branco; {nu} com fundo não uniforme ou vazio")


if __name__ == "__main__":
    main()
