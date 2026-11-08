"""Publica no Instagram um carrossel já aprovado, pela API oficial (Instagram API com login do Instagram).

Roda no workflow "Publicar no Instagram" (postar-instagram.yml), disparado só depois do ok do Gustavo. Lê a pasta do
carrossel na branch posts (em checkout em ./posts): 01.jpg ... (até 20) e legenda.txt. As imagens vão por URL pública
(raw.githubusercontent.com da própria branch). Grava publicado.json na pasta com o id e o link do post.

Segredos do repositório: IG_USER_ID e IG_ACCESS_TOKEN (token de longa duração, 60 dias). Variável opcional:
IG_API_VERSION (padrão v27.0). O token nunca é impresso.

Uso: python instagram/postar.py AAAA-MM-DD/TICKER-PERIODO
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = "https://graph.instagram.com"


def chamar(metodo: str, caminho: str, params: dict) -> dict:
    token = os.environ["IG_ACCESS_TOKEN"]
    versao = os.environ.get("IG_API_VERSION") or "v27.0"
    url = f"{HOST}/{versao}/{caminho}"
    corpo = urllib.parse.urlencode({**params, "access_token": token}).encode()
    if metodo == "GET":
        req = urllib.request.Request(f"{url}?{corpo.decode()}")
    else:
        req = urllib.request.Request(url, data=corpo, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode()).get("error", {})
        except Exception:  # noqa: BLE001
            err = {}
        msg = err.get("message", str(e))
        if err.get("code") == 190:
            msg += " | o token expirou ou foi revogado: gere outro e atualize o segredo IG_ACCESS_TOKEN"
        raise SystemExit(f"Instagram recusou {caminho.split('/')[-1]}: {msg}") from None


def esperar(container: str) -> None:
    for _ in range(30):   # até 5 minutos, de 10 em 10 segundos
        st = chamar("GET", container, {"fields": "status_code"}).get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise SystemExit(f"o Instagram não processou a mídia {container}: {st}")
        time.sleep(10)
    raise SystemExit(f"a mídia {container} não ficou pronta em 5 minutos")


def main() -> None:
    pasta = sys.argv[1].strip().strip("/")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}/[A-Z0-9]{4,6}-[1-4]T\d{2}", pasta):
        raise SystemExit(f"pasta inválida: {pasta!r} (esperado AAAA-MM-DD/TICKER-3T26)")
    local = os.path.join("posts", pasta)
    if os.path.exists(os.path.join(local, "publicado.json")):
        raise SystemExit(f"{pasta} já foi publicado (publicado.json existe); nada a fazer")
    imgs = sorted(glob.glob(os.path.join(local, "[0-9][0-9].jpg")))
    if not 2 <= len(imgs) <= 20:
        raise SystemExit(f"{pasta}: carrossel precisa de 2 a 20 imagens JPEG, achei {len(imgs)}")
    legenda = open(os.path.join(local, "legenda.txt"), encoding="utf-8").read().strip()
    if len(legenda) > 2200 or legenda.count("#") > 30:
        raise SystemExit(f"legenda fora do limite do Instagram: {len(legenda)} caracteres, {legenda.count('#')} hashtags")
    uid = os.environ["IG_USER_ID"]
    base = f"https://raw.githubusercontent.com/{os.environ['REPO']}/posts/{pasta}/"
    filhos = []
    for im in imgs:
        r = chamar("POST", f"{uid}/media", {"image_url": base + os.path.basename(im), "is_carousel_item": "true"})
        filhos.append(r["id"])
    for c in filhos:
        esperar(c)
    car = chamar("POST", f"{uid}/media", {"media_type": "CAROUSEL", "children": ",".join(filhos), "caption": legenda})["id"]
    esperar(car)
    mid = chamar("POST", f"{uid}/media_publish", {"creation_id": car})["id"]
    link = chamar("GET", mid, {"fields": "permalink"}).get("permalink")
    json.dump({"media_id": mid, "permalink": link, "imagens": len(imgs), "publicado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
              open(os.path.join(local, "publicado.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"publicado: {pasta} -> {link}")


if __name__ == "__main__":
    main()
