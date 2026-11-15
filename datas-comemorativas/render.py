#!/usr/bin/env python3
"""Gera os carrosséis das datas comemorativas do @maison.invest a partir de calendario.json.

Uso:
  python3 render.py                       # todas as datas dos próximos 12 meses a partir de hoje
  python3 render.py --de 2026-11-12 --ate 2027-11-11
  python3 render.py --so criancas,maes    # só algumas datas
  python3 render.py --chrome /usr/bin/google-chrome --so-html

Saída por data, no mesmo formato da branch posts do repositório (AAAA-MM-DD/DATA-slug):
  saida/AAAA-MM-DD/DATA-slug/01.jpg ... NN.jpg   carrossel (o que o workflow publica)
  saida/AAAA-MM-DD/DATA-slug/01.png ...          mesmas telas em PNG
  saida/AAAA-MM-DD/DATA-slug/card.png e .jpg     card para mandar ao cliente (não entra no post)
  saida/AAAA-MM-DD/DATA-slug/legenda.txt         legenda completa (com bloco XP)
  saida/AAAA-MM-DD/DATA-slug/mensagem.txt        mensagem individual para clientes (se houver)
  saida/AAAA-MM-DD/DATA-slug/meta.json           data, status (pendente/aprovado), avisos
"""
import argparse, base64, calendar, datetime as dt, json, os, re, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
PESOS = [300, 400, 500, 600, 700, 900]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]
SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
PROIBIDAS = ["garantid", "renda certa", "sem risco", "isento de risco", "recomendamos", "imperdível",
             "oportunidade única", "última chance", "grátis", "gratuit", "consultoria", "consultor",
             "independente", "gerimos", "cuidamos do seu dinheiro", "melhor do mercado", "gestão"]
LIMITES = {"capa.titulo": 40, "capa.frase": 90, "item.t": 32, "item.d": 100, "fecho.titulo": 46,
           "fecho.texto": 130, "slide.titulo": 46, "slide.rotulo": 32, "texto": 260, "fonte": 140}


def pascoa(ano):
    """Domingo de Páscoa (algoritmo gregoriano anônimo)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(ano, mes, dia)


def ocorrencia(regra, ano):
    t = regra["tipo"]
    if t == "fixa":
        return dt.date(ano, regra["mes"], regra["dia"])
    if t in ("domingo", "nth"):  # n-ésimo dia da semana do mês (0 = segunda ... 6 = domingo)
        ds = 6 if t == "domingo" else regra["dia_semana"]
        dias = [d for d in calendar.Calendar().itermonthdates(ano, regra["mes"])
                if d.month == regra["mes"] and d.weekday() == ds]
        return dias[regra["n"] - 1]
    if t == "pascoa":
        return pascoa(ano) + dt.timedelta(days=regra.get("deslocamento", 0))
    raise ValueError(regra)


def datas_no_periodo(regra, de, ate):
    return [d for d in (ocorrencia(regra, a) for a in range(de.year, ate.year + 1)) if de <= d <= ate]


def troca_ano(obj, ano):
    if isinstance(obj, str):
        return obj.replace("{ano}", str(ano))
    if isinstance(obj, list):
        return [troca_ano(x, ano) for x in obj]
    if isinstance(obj, dict):
        return {k: troca_ano(v, ano) for k, v in obj.items()}
    return obj


def validar(e, legenda):
    erros = []
    def checa(rot, txt, lim):
        if txt and len(txt) > lim:
            erros.append(f"{rot} longo demais ({len(txt)} > {lim}): {txt[:50]}...")
    checa("capa.titulo", e["capa"]["titulo"], LIMITES["capa.titulo"])
    checa("capa.frase", e["capa"]["frase"], LIMITES["capa.frase"])
    checa("fecho.titulo", e["fecho"]["titulo"], LIMITES["fecho.titulo"])
    checa("fecho.texto", e["fecho"]["texto"], LIMITES["fecho.texto"])
    for s in e["slides"]:
        checa("slide.titulo", s["titulo"], LIMITES["slide.titulo"])
        checa("slide.rotulo", s["rotulo"], LIMITES["slide.rotulo"])
        checa("fonte", s.get("fonte", ""), LIMITES["fonte"])
        checa("texto", s.get("texto", ""), LIMITES["texto"])
        for it in s.get("itens", []):
            checa("item.t", it["t"], LIMITES["item.t"])
            checa("item.d", it["d"], LIMITES["item.d"])
        if s["tipo"] == "edu" and len(s["itens"]) != 3:
            erros.append(f"slide educativo com {len(s['itens'])} itens (esperado 3)")
    if e.get("cta"):
        checa("cta.convite", e["cta"]["convite"], 80)
        checa("cta.destino", e["cta"]["destino"], 44)
    tudo = json.dumps(e, ensure_ascii=False) + legenda
    if "—" in tudo or "–" in tudo:
        erros.append("travessão ou meia-risca no texto (regra da marca: sem travessão)")
    if " · " in tudo or "▪" in tudo:
        erros.append("ponto médio ou marcador ▪ no texto (parece texto de IA; usar frase ou parágrafo)")
    baixo = tudo.lower()
    achadas = [w for w in PROIBIDAS if w in baixo]
    if achadas:
        erros.append(f"palavra de risco: {achadas}")
    if len(legenda) > 2200:
        erros.append(f"legenda passa de 2.200 caracteres ({len(legenda)})")
    if legenda.count("#") > 30:
        erros.append("mais de 30 hashtags")
    if not 2 <= 2 + len(e["slides"]) <= 20:
        erros.append("carrossel precisa de 2 a 20 telas")
    return erros


def monta_legenda(e, bloco_xp):
    partes = [e["legenda"].strip()]
    if e.get("cta"):
        partes.append(e["cta"]["legenda"])
    if not e.get("sobrio"):
        partes.append("Liberdade nas escolhas. Fraternidade na relação. Expertise na solução.")
    if any(s["tipo"] == "edu" for s in e["slides"]):
        partes.append("Conteúdo educativo; não constitui recomendação de investimento.")
    partes += [bloco_xp.strip(), e["hashtags"].strip()]
    return "\n\n".join(partes)


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
    hoje = dt.date.today()
    ap.add_argument("--de", default=hoje.isoformat())
    ap.add_argument("--ate", default=(hoje + dt.timedelta(days=364)).isoformat())
    ap.add_argument("--so", default="")
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH"))
    ap.add_argument("--so-html", action="store_true")
    a = ap.parse_args()
    de, ate = dt.date.fromisoformat(a.de), dt.date.fromisoformat(a.ate)
    so = {s for s in a.so.split(",") if s}

    cal = json.load(open(os.path.join(AQUI, "calendario.json"), encoding="utf-8"))
    bloco_xp = open(os.path.join(AQUI, "bloco_xp.txt"), encoding="utf-8").read()
    logo = base64.b64encode(open(os.path.join(AQUI, "logo-invest-xp-negativo.svg"), "rb").read()).decode()
    tpl = (open(os.path.join(AQUI, "template", "data-carrossel.html"), encoding="utf-8").read()
           .replace("/*FONTES*/", fontes_css())
           .replace("/*LOGO*/", "data:image/svg+xml;base64," + logo))

    trabalhos, falhas = [], []
    for e0 in cal["datas"]:
        if so and e0["slug"] not in so:
            continue
        for d in datas_no_periodo(e0["regra"], de, ate):
            e = troca_ano(e0, d.year)
            legenda = monta_legenda(e, bloco_xp)
            erros = validar(e, legenda)
            if erros:
                falhas.append((e["slug"], d, erros)); continue
            pasta = os.path.join(AQUI, "saida", d.isoformat(), f"DATA-{e['slug']}")
            os.makedirs(pasta, exist_ok=True)
            avisos = []
            if "[" in bloco_xp:
                avisos.append("bloco_xp.txt ainda tem marcador [ ] (link da relação de assessores a confirmar)")
            avisos += [f"confirmar: {c}" for c in e.get("confirmar", [])]
            meta_path = os.path.join(pasta, "meta.json")
            anterior = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
            meta = {"slug": e["slug"], "nome": e["nome"], "data": d.isoformat(),
                    "publicar_em": f"{d.isoformat()}T{cal['horario_publicacao']}:00-03:00",
                    "pasta_posts": f"{d.isoformat()}/DATA-{e['slug']}",
                    "telas": 2 + len(e["slides"]),
                    "status": anterior.get("status", "pendente"),
                    "aprovado_por": anterior.get("aprovado_por"),
                    "avisos": avisos, "lista": e["lista"]}
            json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            open(os.path.join(pasta, "legenda.txt"), "w", encoding="utf-8").write(legenda)
            if e.get("mensagem_cliente"):
                open(os.path.join(pasta, "mensagem.txt"), "w", encoding="utf-8").write(e["mensagem_cliente"])
            dados = dict(e, quando={"iso": d.isoformat(), "dia": d.day, "mes": MESES[d.month - 1],
                                    "ano": d.year, "semana": SEMANA[d.weekday()]})
            html = tpl.replace("/*DADOS*/null", json.dumps(dados, ensure_ascii=False))
            preview = os.path.join(pasta, "preview.html")
            open(preview, "w", encoding="utf-8").write(html)
            trabalhos.append((pasta, preview))
            print(f"ok   {d}  {e['slug']:<11} {meta['telas']} telas  avisos: {len(avisos)}")

    for slug, d, erros in falhas:
        print(f"ERRO {d}  {slug}:\n  - " + "\n  - ".join(erros), file=sys.stderr)
    if a.so_html or not trabalhos:
        sys.exit(1 if falhas else 0)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        kw = {"executable_path": a.chrome} if a.chrome else {}
        b = p.chromium.launch(**kw)
        pg = b.new_page(viewport={"width": 1200, "height": 1500}, device_scale_factor=1)
        for pasta, preview in trabalhos:
            pg.goto("file://" + preview)
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(250)
            for f in os.listdir(pasta):
                if re.fullmatch(r"\d\d\.(jpg|png)", f):
                    os.remove(os.path.join(pasta, f))
            slides = pg.query_selector_all("section.slide:not(.card)")
            for n, el in enumerate(slides, 1):
                base = os.path.join(pasta, f"{n:02d}")
                el.screenshot(path=base + ".png")
                el.screenshot(path=base + ".jpg", type="jpeg", quality=92)
            card = pg.query_selector("section.card")
            card.screenshot(path=os.path.join(pasta, "card.png"))
            card.screenshot(path=os.path.join(pasta, "card.jpg"), type="jpeg", quality=92)
        b.close()
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
