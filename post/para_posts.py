#!/usr/bin/env python3
"""Leva um carrossel renderizado para a branch posts, no formato que o workflow "Publicar no Instagram" lê.

Converte 01.png ... em JPEG (o Instagram só aceita JPEG pela API), copia a legenda.txt e grava em
POSTS/AAAA-MM-DD/TICKER-PERIODO/. Não faz commit nem push: isso fica para quem chama.

Uso: python3 -I para_posts.py PASTA_RENDERIZADA PASTA_DA_BRANCH_POSTS AAAA-MM-DD TICKER-PERIODO
"""
import glob
import os
import shutil
import sys

from PIL import Image


def main() -> None:
    src, posts, dia, chave = sys.argv[1:5]
    dst = os.path.join(posts, dia, chave)
    os.makedirs(dst, exist_ok=True)
    pngs = sorted(glob.glob(os.path.join(src, "[0-9][0-9].png")))
    if not pngs:
        raise SystemExit(f"nenhum PNG em {src}")
    for p in pngs:
        Image.open(p).convert("RGB").save(os.path.join(dst, os.path.basename(p)[:-4] + ".jpg"), "JPEG", quality=92, optimize=True)
    shutil.copyfile(os.path.join(src, "legenda.txt"), os.path.join(dst, "legenda.txt"))
    print(f"{dst}: {len(pngs)} imagens JPEG e a legenda")


if __name__ == "__main__":
    main()
