"""Confere, sem publicar nada, se o token do Instagram já pode publicar: segredos presentes, permissão
instagram_content_publish concedida (token do Facebook) e limite de publicação legível na conta.

Uso: python instagram/pronto.py   (sai com código 0 quando pode publicar; 1 com o motivo, quando não)
O token nunca é impresso.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from postar import _host  # noqa: E402


def _get(caminho: str, **q) -> tuple[int, dict]:
    tok = os.environ["IG_ACCESS_TOKEN"]
    v = os.environ.get("IG_API_VERSION") or "v27.0"
    url = f"{_host(tok)}/{v}/{caminho}?" + urllib.parse.urlencode({**q, "access_token": tok})
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:  # noqa: BLE001
            return e.code, {}


def main() -> None:
    tok, uid = os.environ.get("IG_ACCESS_TOKEN", "").strip(), os.environ.get("IG_USER_ID", "").strip()
    if not tok or not uid:
        sys.exit("não publica: faltam os segredos IG_ACCESS_TOKEN e/ou IG_USER_ID")
    if not tok.startswith("IG"):
        st, pe = _get("me/permissions")
        dadas = {x.get("permission") for x in pe.get("data", []) if x.get("status") == "granted"}
        if "instagram_content_publish" not in dadas:
            sys.exit("não publica: o token não tem a permissão instagram_content_publish "
                     f"(concedidas: {', '.join(sorted(dadas)) or 'nenhuma'})")
    st, lim = _get(f"{uid}/content_publishing_limit", fields="quota_usage,config")
    if st != 200:
        sys.exit(f"não publica: limite de publicação ilegível ({st}: {(lim.get('error') or {}).get('message', lim)})")
    print("pode publicar:", json.dumps(lim.get("data", lim), ensure_ascii=False))


if __name__ == "__main__":
    main()
