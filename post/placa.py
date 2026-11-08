"""Monta os logos da capa na pasta de trabalho, um por companhia, na versão indicada no indice.csv.

Ordem de escolha para cada código com status "ok":
  1. logos/oficial/<código>.svg ou .png: arquivo oficial da empresa (versão para fundo escuro), usado como está;
  2. coluna capa = "branco": logos/branco/<código>.png (padrão, combina com o fundo azul escuro);
  3. coluna capa = "cor": logos/cor/<código>.png (quando o branco vira um bloco sem detalhe, como o Itaú);
  4. coluna capa = "placa": a placa original recortada, com o fundo da marca (quando a transparência ficou com ruído).
Status diferente de "ok" (desatualizado, verificar) fica de fora: a capa mostra o espaço e o render avisa.
Grava <código>.png ou .svg e tamanhos.json (largura e altura em pixels; svg sem tamanho).

Uso: python3 -I placa.py PASTA_DOS_LOGOS PASTA_DE_SAIDA
"""
import csv
import json
import os
import shutil
import sys

from PIL import Image, ImageChops


def placa(im):
    """Placa original com a margem recortada e o fundo da própria marca; sem recolorir."""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    cantos = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    fundo = max(set(cantos), key=cantos.count)
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
    rows = list(csv.DictReader(open(os.path.join(src, "indice.csv"), encoding="utf-8"), delimiter=";"))
    oficial = os.path.join(src, "oficial")
    tam, fora = {}, 0
    for r in rows:
        cod = r["codigo"]
        if r.get("status", "ok") != "ok":
            fora += 1
            continue
        feito = False
        for ext in (".svg", ".png"):
            f = os.path.join(oficial, cod + ext)
            if os.path.exists(f):
                shutil.copyfile(f, os.path.join(dst, cod + ext))
                tam[cod] = None if ext == ".svg" else list(Image.open(f).size)
                feito = True
                break
        if feito:
            continue
        versao = r.get("capa") or "branco"
        if versao == "placa":
            out = placa(Image.open(os.path.join(src, "original", cod + ".png")))
            out.save(os.path.join(dst, cod + ".png"))
            tam[cod] = list(out.size)
        else:
            f = os.path.join(src, versao, cod + ".png")
            if not os.path.exists(f):
                continue
            shutil.copyfile(f, os.path.join(dst, cod + ".png"))
            tam[cod] = list(Image.open(f).size)
    json.dump(tam, open(os.path.join(dst, "tamanhos.json"), "w"))
    print(f"{len(tam)} logos prontos para a capa, {fora} fora (desatualizados ou a verificar)")


if __name__ == "__main__":
    main()
