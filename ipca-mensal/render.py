#!/usr/bin/env python3
"""Gera o carrossel do IPCA de um mês: HTML autocontido + PNGs 1080x1350.

Uso:
    python3 render.py dados/ipca-2026-08.json            # saída em saida/2026-08/
    python3 render.py dados/ipca-2026-08.json --chrome /caminho/do/chrome

Requisitos: pip install playwright (o navegador pode ser o Chrome instalado,
via --chrome, ou o baixado por `playwright install chromium`).
"""
import argparse, base64, json, pathlib, sys

RAIZ = pathlib.Path(__file__).resolve().parent
PESOS = [400, 500, 700, 800, 900]


def data_uri(caminho: pathlib.Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(caminho.read_bytes()).decode()


def montar_html(dados: dict) -> str:
    html = (RAIZ / "template" / "ipca-carrossel.html").read_text(encoding="utf-8")
    for p in PESOS:
        html = html.replace(f"__FONT_{p}__", data_uri(RAIZ / "fonts" / f"montserrat-latin-{p}-normal.woff2", "font/woff2"))
    logo = {"invest-xp": "logo-invest-xp-negativo.svg"}.get(dados.get("marca", "invest-xp"))
    if not logo:
        sys.exit(f"marca sem logo configurado: {dados.get('marca')}")
    html = html.replace("__LOGO__", data_uri(RAIZ / logo, "image/svg+xml"))
    html = html.replace("__DADOS__", json.dumps(dados, ensure_ascii=False))
    return html


def validar(d: dict):
    erros = []
    for chave in ("referencia", "divulgacao", "indice", "historico_12m", "mesmo_mes_anos_anteriores", "grupos", "regioes", "focus"):
        if chave not in d:
            erros.append(f"falta '{chave}'")
    if not erros:
        if len(d["historico_12m"]) != 12:
            erros.append("historico_12m precisa de 12 meses")
        if d["historico_12m"][-1]["mes"] != d["referencia"]:
            erros.append("último mês do histórico difere da referência")
        if abs(d["historico_12m"][-1]["variacao"] - d["indice"]["variacao"]) > 1e-9:
            erros.append("variação do mês difere entre 'indice' e 'historico_12m'")
        acum = 1.0
        for h in d["historico_12m"]:
            acum *= 1 + h["variacao"] / 100
        if abs((acum - 1) * 100 - d["indice"]["acumulado_12m"]) > 0.02:
            erros.append(f"acumulado 12m não fecha: calculado {(acum-1)*100:.2f}")
        if len(d["grupos"]) != 9:
            erros.append("esperados 9 grupos")
    if erros:
        sys.exit("Dados inválidos:\n- " + "\n- ".join(erros))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dados")
    ap.add_argument("--chrome", default=None, help="executável do Chrome/Chromium (opcional)")
    ap.add_argument("--saida", default=None)
    a = ap.parse_args()

    dados = json.loads(pathlib.Path(a.dados).read_text(encoding="utf-8"))
    validar(dados)
    destino = pathlib.Path(a.saida or RAIZ / "saida" / dados["referencia"])
    destino.mkdir(parents=True, exist_ok=True)
    for velho in list(destino.glob("*.png")) + list(destino.glob("*.jpg")):
        velho.unlink()  # o número de slides pode mudar de um mês para outro
    html_path = destino / "carrossel.html"
    html_path.write_text(montar_html(dados), encoding="utf-8")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        kw = {"executable_path": a.chrome} if a.chrome else {}
        nav = pw.chromium.launch(**kw)
        pag = nav.new_page(viewport={"width": 1160, "height": 1500}, device_scale_factor=1)
        pag.goto(html_path.as_uri())
        pag.evaluate("document.fonts.ready")
        pag.wait_for_timeout(300)
        slides = pag.query_selector_all("section.slide")
        for s in slides:
            nome = s.get_attribute("data-nome")
            s.screenshot(path=str(destino / f"{nome}.png"))
            # a API do Instagram (Graph API) só aceita JPEG em image_url
            s.screenshot(path=str(destino / f"{nome}.jpg"), type="jpeg", quality=95)
        nav.close()
    print(f"{len(slides)} slides em {destino}")


if __name__ == "__main__":
    main()
