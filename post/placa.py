"""Prepara os logos da biblioteca para a capa: recorta a margem e mantém o fundo da própria placa da marca (branco ou a
cor da marca), sem recolorir nem redesenhar. Logos marcados como desatualizados no indice.csv ficam de fora (a capa
mostra o espaço e o render avisa). Grava tamanhos.json com largura e altura de cada placa.

Uso: python3 -I placa.py PASTA_DOS_LOGOS PASTA_DE_SAIDA
"""
import csv
import json
import os
import sys

from PIL import Image, ImageChops


def placa(im):
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    cantos = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    fundo = max(set(cantos), key=cantos.count)
    if fundo[3] < 16:  # fundo transparente: placa branca
        base = Image.new("RGBA", im.size, (255, 255, 255, 255))
        base.alpha_composite(im)
        im, fundo = base, (255, 255, 255, 255)
    dif = ImageChops.difference(im.convert("RGB"), Image.new("RGB", im.size, fundo[:3]))
    bb = dif.convert("L").point(lambda v: 255 if v > 28 else 0).getbbox()
    if not bb:
        return im
    cw, ch = bb[2] - bb[0], bb[3] - bb[1]
    pad = max(10, round(max(cw, ch) * 0.16))
    out = Image.new("RGBA", (cw + 2 * pad, ch + 2 * pad), fundo)
    out.alpha_composite(im.crop(bb), (pad, pad))
    return out


def main() -> None:
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    fora = set()
    ind = os.path.join(src, "indice.csv")
    if os.path.exists(ind):
        for r in csv.DictReader(open(ind, encoding="utf-8"), delimiter=";"):
            if r.get("status", "ok") != "ok":
                fora.add(r["codigo"])
    tam = {}
    for f in sorted(os.listdir(src)):
        cod, ext = os.path.splitext(f)
        if ext.lower() == ".svg" and cod not in fora:  # svg oficial: vai como está
            open(os.path.join(dst, f), "wb").write(open(os.path.join(src, f), "rb").read())
            tam[cod] = None
        elif ext.lower() == ".png" and cod not in fora and cod not in tam:
            out = placa(Image.open(os.path.join(src, f)))
            out.save(os.path.join(dst, f))
            tam[cod] = list(out.size)
    json.dump(tam, open(os.path.join(dst, "tamanhos.json"), "w"))
    print(f"{len(tam)} logos prontos, {len(fora)} fora da capa (desatualizados ou a verificar)")


if __name__ == "__main__":
    main()
