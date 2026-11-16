#!/usr/bin/env python3
"""Gera os slides do post semanal do Focus.

Uso: python3 render.py dados/focus-AAAA-MM-DD.json [--chrome /caminho/do/chrome]
Saída: saida/AAAA-MM-DD/0N-slide.png e .jpg, preview.html
"""
import argparse, base64, json, os, re, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
PESOS = [300, 400, 500, 600, 700, 800, 900]


def validar(d):
    erros = []
    if len(d.get("indicadores", [])) != 4:
        erros.append("esperava 4 indicadores")
    for i in d.get("indicadores", []):
        for a in map(str, d["anos"]):
            x = i["anos"].get(a)
            if not x:
                erros.append(f"{i['chave']} sem {a}"); continue
            if len(x["serie"]) < 8:
                erros.append(f"{i['chave']} {a}: série curta ({len(x['serie'])} semanas)")
            if x["serie"][-1]["mediana"] != x["mediana"]:
                erros.append(f"{i['chave']} {a}: última semana da série diferente da mediana")
            faixa = {"ipca": (-5, 30), "selic": (0, 40), "pib": (-10, 10), "cambio": (2, 15)}[i["chave"]]
            if not faixa[0] < x["mediana"] < faixa[1]:
                erros.append(f"{i['chave']} {a}: mediana fora da faixa plausível ({x['mediana']})")
    for i in d.get("indicadores", []):
        if len(i.get("horizonte", [])) < 4:
            erros.append(f"{i['chave']}: horizonte com menos de 4 anos")
    for k, v in d.get("textos", {}).items():
        if len(re.sub(r"<[^>]+>", "", v)) > 110:
            erros.append(f"texto {k} longo demais ({len(v)} caracteres)")
    if erros:
        raise SystemExit("JSON recusado:\n- " + "\n- ".join(erros))


NOME_LEG = {"ipca": "IPCA", "selic": "Selic no fim do ano", "pib": "PIB", "cambio": "Dólar no fim do ano"}
PROIBIDAS = ["garantid", "renda certa", "sem risco", "recomendamos", "imperdível", "oportunidade única"]


def sem_tags(t):
    return re.sub(r"<[^>]+>", "", t)


def legenda(d):
    def v(ch, x):
        return (f"R$ {x:.2f}" if ch == "cambio" else f"{x:.2f}%").replace(".", ",")
    def dl(ch, a):
        if a["sentido"] == "estavel":
            return "estável"
        mag = f"{abs(a['variacao_semana']):.2f}".replace(".", ",")
        return ("subiu " if a["variacao_semana"] > 0 else "caiu ") + (f"R$ {mag}" if ch == "cambio" else f"{mag}%")
    a0, a1 = map(str, d["anos"])
    linhas = [f"{NOME_LEG[i['chave']]}: {v(i['chave'], i['anos'][a0]['mediana'])} em {a0} ({dl(i['chave'], i['anos'][a0])}) "
              f"e {v(i['chave'], i['anos'][a1]['mediana'])} em {a1} ({dl(i['chave'], i['anos'][a1])})"
              for i in d["indicadores"]]
    resp = max(i["anos"][a0]["respondentes"] for i in d["indicadores"])
    data_br = "/".join(reversed(d["boletim"]["data_divulgacao"].split("-")))
    bloco_xp = open(os.path.join(AQUI, "bloco_xp.txt")).read().strip()
    t = d["textos"]
    texto = f"""Focus da semana, {data_br}

Toda segunda o Banco Central publica o Relatório Focus, com a mediana das projeções de cerca de {resp // 10 * 10} instituições do mercado. {t['capa_rotulo']}: {v(d['destaque']['chave'], next(i for i in d['indicadores'] if i['chave'] == d['destaque']['chave'])['anos'][a0]['mediana'])}. {sem_tags(t['capa_frase'])} {t['capa_apoio']}

{chr(10).join(linhas)}

{t['horizonte_sub']}

No quarto slide, cada faixa vai da menor à maior projeção para o ano, medida pela distância até a mediana: quanto mais curta, mais o mercado concorda.

Salve para comparar na próxima segunda. Quer conversar sobre o seu patrimônio? Link na bio.

Liberdade nas escolhas. Fraternidade na relação. Expertise na solução.

Fonte: Banco Central, Relatório Focus de {data_br} (medianas). As projeções são de instituições de mercado e não são projeções da Maison nem recomendação de investimento.{chr(10) + bloco_xp if bloco_xp else ""}

#BoletimFocus #Selic #IPCA #Economia #MaisonInvest"""
    baixo = texto.lower()
    achadas = [w for w in PROIBIDAS if w in baixo]
    if achadas:
        raise SystemExit(f"Legenda com palavra de risco: {achadas}")
    if "\u2014" in texto or "\u2013" in texto:
        raise SystemExit("Legenda com travessão")
    if len(texto) > 2200:
        raise SystemExit(f"Legenda passa do limite do Instagram ({len(texto)} caracteres)")
    return texto


def alt_textos(d):
    a0 = str(d["anos"][0])
    t = d["textos"]
    def v(ch, x):
        return (f"R$ {x:.2f}" if ch == "cambio" else f"{x:.2f}%").replace(".", ",")
    por = {i["chave"]: i for i in d["indicadores"]}
    ch = d["destaque"]["chave"]
    alts = [
        f"Capa do Focus da semana. {t['capa_rotulo']}: {v(ch, por[ch]['anos'][a0]['mediana'])}. {sem_tags(t['capa_frase'])} {t['capa_contexto']}.",
        f"{t['painel_titulo']}. {t['painel_sub']} " + " ".join(
            f"{NOME_LEG[i['chave']]}: {v(i['chave'], i['anos'][a0]['mediana'])}, ante {v(i['chave'], i['anos'][a0]['serie'][0]['mediana'])} seis meses atrás."
            for i in d["indicadores"]),
        f"{t['horizonte_titulo']}. {t['horizonte_sub']} " + " ".join(
            f"{NOME_LEG[i['chave']]}: " + ", ".join(f"{h['ano']} {v(i['chave'], h['mediana'])}" for h in i["horizonte"]) + "."
            for i in d["indicadores"]),
        f"{t['consenso_titulo']}. {t['consenso_sub']} " + " ".join(
            f"{NOME_LEG[i['chave']]}: mediana {v(i['chave'], i['anos'][a0]['mediana'])}, projeções de {v(i['chave'], i['anos'][a0]['minimo'])} a {v(i['chave'], i['anos'][a0]['maximo'])}."
            for i in d["indicadores"]),
        f"{t['fechamento_titulo']}. Salve para comparar na próxima segunda. Quer conversar sobre o seu patrimônio? Link na bio.",
    ]
    if any(not x.strip() for x in alts):
        raise SystemExit("alt vazio")
    return alts


def fontes_css():
    css = []
    for p in PESOS:
        f = os.path.join(AQUI, "fonts", f"montserrat-latin-{p}-normal.woff2")
        b64 = base64.b64encode(open(f, "rb").read()).decode()
        css.append(f'@font-face{{font-family:"Montserrat";font-weight:{p};font-style:normal;'
                   f'src:url(data:font/woff2;base64,{b64}) format("woff2")}}')
    return "\n".join(css)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH"))
    ap.add_argument("--so-html", action="store_true")
    args = ap.parse_args()

    d = json.load(open(args.json))
    validar(d)
    saida = os.path.join(AQUI, "saida", d["boletim"]["data_divulgacao"])
    os.makedirs(saida, exist_ok=True)

    logo = base64.b64encode(open(os.path.join(AQUI, "logo-invest-xp-negativo.svg"), "rb").read()).decode()
    html = open(os.path.join(AQUI, "template", "focus-carrossel.html")).read()
    html = (html.replace("/*FONTES*/", fontes_css())
                .replace("/*DADOS*/null", json.dumps(d, ensure_ascii=False))
                .replace("/*LOGO*/", "data:image/svg+xml;base64," + logo))
    for nome in ("cart", "industry"):
        svg = open(os.path.join(AQUI, "icones", f"{nome}.svg")).read()
        svg = re.sub(r'\s(width|height)="24"', "", svg)
        html = html.replace(f"/*IC_{nome}*/", svg)
    open(os.path.join(saida, "legenda.txt"), "w").write(legenda(d))
    json.dump(alt_textos(d), open(os.path.join(saida, "alt.json"), "w"), ensure_ascii=False, indent=1)
    preview = os.path.join(saida, "preview.html")
    open(preview, "w").write(html)
    if args.so_html:
        print(preview); return

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        kw = {"executable_path": args.chrome} if args.chrome else {}
        b = p.chromium.launch(**kw)
        pg = b.new_page(viewport={"width": 1200, "height": 1500}, device_scale_factor=1)
        pg.goto("file://" + preview)
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(300)
        slides = pg.query_selector_all("section.slide")
        for n, el in enumerate(slides, 1):
            png = os.path.join(saida, f"{n:02d}-slide.png")
            el.screenshot(path=png)
            el.screenshot(path=png[:-4] + ".jpg", type="jpeg", quality=92)
            print(png)
        b.close()


if __name__ == "__main__":
    main()
