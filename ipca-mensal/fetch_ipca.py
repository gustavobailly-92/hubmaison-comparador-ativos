#!/usr/bin/env python3
"""Monta dados/ipca-AAAA-MM.json a partir das APIs oficiais.

Uso:
    python3 fetch_ipca.py                       # último mês disponível no SIDRA
    python3 fetch_ipca.py --mes 2026-10         # mês específico
    python3 fetch_ipca.py --projecoes dados/projecoes-2026-10.json

Fontes:
- IBGE/SIDRA tabela 7060 (IPCA desde jan/2020): variação mensal (63), acumulada no ano (69),
  acumulada em 12 meses (2265) e peso (66), por grupo (classificação 315), para Brasil,
  regiões metropolitanas (n7) e municípios (n6).
- IBGE/SIDRA tabela 1737 (série longa) para o mesmo mês em anos anteriores a 2020.
- Banco Central, API Olinda, Expectativas de Mercado Anuais (Focus), indicador IPCA.
- Projeções de casas e agências (Bloomberg, Reuters, XP) não têm API pública: vêm de um
  arquivo à parte (--projecoes), preenchido a partir das notícias do dia.
"""
import argparse, datetime as dt, json, pathlib, sys, urllib.request, urllib.parse

RAIZ = pathlib.Path(__file__).resolve().parent
SIDRA = "https://apisidra.ibge.gov.br/values"
OLINDA = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"

GRUPOS = [  # código c315, id, nome, curto
    ("7170", "alimentacao", "Alimentação e bebidas", "Alimentação"),
    ("7445", "habitacao", "Habitação", "Habitação"),
    ("7486", "residencia", "Artigos de residência", "Art. resid."),
    ("7558", "vestuario", "Vestuário", "Vestuário"),
    ("7625", "transportes", "Transportes", "Transportes"),
    ("7660", "saude", "Saúde e cuidados pessoais", "Saúde"),
    ("7712", "despesas", "Despesas pessoais", "Desp. pessoais"),
    ("7766", "educacao", "Educação", "Educação"),
    ("7786", "comunicacao", "Comunicação", "Comunicação"),
]
# Regiões: código SIDRA -> (nome curto, UF, peso regional aproximado em %, divulgado pelo IBGE)
REGIOES = {
    "3501": ("São Paulo", "SP", 32.3), "3101": ("Belo Horizonte", "MG", 9.7),
    "3301": ("Rio de Janeiro", "RJ", 9.4), "4301": ("Porto Alegre", "RS", 8.6),
    "4101": ("Curitiba", "PR", 8.1), "2901": ("Salvador", "BA", 6.0),
    "5208707": ("Goiânia", "GO", 4.2), "5300108": ("Brasília", "DF", 4.1),
    "1501": ("Belém", "PA", 3.9), "2601": ("Recife", "PE", 3.9),
    "2301": ("Fortaleza", "CE", 3.2), "3201": ("Vitória", "ES", 1.9),
    "2111300": ("São Luís", "MA", 1.6), "5002704": ("Campo Grande", "MS", 1.6),
    "2800308": ("Aracaju", "SE", 1.0), "1200401": ("Rio Branco", "AC", 0.5),
}


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        txt = r.read().decode("utf-8")
    if txt.startswith("/*"):
        txt = txt.strip("/*").strip("*/")
    return json.loads(txt)


def sidra(path):
    linhas = get(f"{SIDRA}/{path}")
    return [l for l in linhas[1:] if l["V"] not in ("...", "-", "X", "")]


def mes_iso(cod):  # "202610" -> "2026-10"
    return f"{cod[:4]}-{cod[4:]}"


def cod_mes(iso):
    return iso.replace("-", "")


def mes_anterior(iso, n=1):
    a, m = map(int, iso.split("-"))
    m -= n
    while m <= 0:
        m += 12; a -= 1
    return f"{a}-{m:02d}"


def focus_mensal(ref, limite):
    """Mediana, mínimo e máximo do Focus para o IPCA do mês, no último dia de coleta antes da divulgação.
    É o que sai sozinho todo mês; Reuters e Bloomberg não têm API pública e só entram via --projecoes."""
    a, m = ref.split("-")
    filtro = urllib.parse.quote(f"Indicador eq 'IPCA' and DataReferencia eq '{m}/{a}' and baseCalculo eq 0", safe="")
    url = (f"https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativaMercadoMensais"
           f"?%24filter={filtro}&%24orderby={urllib.parse.quote('Data desc', safe='')}&%24top=40&%24format=json"
           f"&%24select=Data,Mediana,Minimo,Maximo,numeroRespondentes")
    linhas = [r for r in get(url)["value"] if r["Data"] < limite]
    if not linhas:
        return None
    r = linhas[0]
    return {"mediana": round(r["Mediana"], 2), "fonte_mediana": "Boletim Focus",
            "intervalo_min": round(r["Minimo"], 2), "intervalo_max": round(r["Maximo"], 2),
            "fonte_intervalo": "Boletim Focus", "intervalo_confirmado": True,
            "coleta": r["Data"], "respondentes": r["numeroRespondentes"], "casas": []}


def montar(mes=None, projecoes=None, divulgacao=None):
    grupos_c = ",".join(["7169"] + [g[0] for g in GRUPOS])

    # mês de referência
    ult = sidra("t/7060/n1/all/v/63/p/last%201/c315/7169")
    ref = mes or mes_iso(ult[0]["D3C"])
    ant = mes_anterior(ref)
    p2 = f"{cod_mes(ant)},{cod_mes(ref)}"

    # índice geral
    ix = {}
    for l in sidra(f"t/7060/n1/all/v/63,69,2265/p/{p2}/c315/7169"):
        ix[(l["D2C"], mes_iso(l["D3C"]))] = float(l["V"])
    if ("63", ref) not in ix:
        sys.exit(f"SIDRA ainda não tem {ref}")

    # 12 meses
    p12 = ",".join(cod_mes(mes_anterior(ref, k)) for k in range(11, -1, -1))
    hist = sorted(({"mes": mes_iso(l["D3C"]), "variacao": float(l["V"])}
                   for l in sidra(f"t/7060/n1/all/v/63/p/{p12}/c315/7169")), key=lambda h: h["mes"])

    # grupos Brasil
    gv = {}
    for l in sidra(f"t/7060/n1/all/v/63,66/p/{p2}/c315/{grupos_c}"):
        gv[(l["D2C"], mes_iso(l["D3C"]), l["D4C"])] = float(l["V"])
    grupos = [{"id": i, "nome": n, "curto": c, "peso": round(gv[("66", ref, cod)], 4),
               "anterior": gv[("63", ant, cod)], "atual": gv[("63", ref, cod)]} for cod, i, n, c in GRUPOS]

    # regiões e matriz
    rv = {}
    for l in sidra(f"t/7060/n7/all/n6/all/v/63,2265/p/{p2}/c315/{grupos_c}"):
        rv[(l["D1C"], l["D2C"], mes_iso(l["D3C"]), l["D4C"])] = float(l["V"])
    regioes, matriz = [], []
    for cod, (nome, uf, peso) in REGIOES.items():
        regioes.append({"nome": nome, "uf": uf, "peso": peso,
                        "anterior": rv[(cod, "63", ant, "7169")], "atual": rv[(cod, "63", ref, "7169")],
                        "acumulado_12m": rv[(cod, "2265", ref, "7169")]})
        matriz.append({"nome": nome, "uf": uf,
                       "valores": {i: rv[(cod, "63", ref, c)] for c, i, _, _ in GRUPOS}})

    # mesmo mês, 10 anos anteriores (série longa 1737)
    a, m = map(int, ref.split("-"))
    pp = ",".join(f"{y}{m:02d}" for y in range(a - 10, a))
    mesmo = sorted(({"ano": int(l["D3C"][:4]), "variacao": float(l["V"])}
                    for l in sidra(f"t/1737/n1/all/v/63/p/{pp}")), key=lambda h: h["ano"])

    # histórico anual: IPCA acumulado em dezembro de cada um dos 20 anos anteriores (série longa 1737)
    pa = ",".join(f"{y}12" for y in range(a - 20, a))
    anual = sorted(({"ano": int(l["D3C"][:4]), "variacao": float(l["V"])}
                    for l in sidra(f"t/1737/n1/all/v/69/p/{pa}")), key=lambda h: h["ano"])

    # CDI x IPCA + 6%: 20 anos até o mês de referência, mensal (BCB SGS 4391 e IBGE 1737)
    ini = mes_anterior(ref, 239)
    ai, mi = map(int, ini.split("-"))
    cdi = get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.4391/dados?formato=json"
              f"&dataInicial=01/{mi:02d}/{ai}&dataFinal=28/{m:02d}/{a}")
    cdi = {f"{x['data'][6:]}-{x['data'][3:5]}": float(x["valor"]) for x in cdi}
    meses = [mes_anterior(ref, k) for k in range(239, -1, -1)]
    ipm = {}
    for bloco in range(0, 240, 120):
        pp2 = ",".join(cod_mes(x) for x in meses[bloco:bloco + 120])
        for l in sidra(f"t/1737/n1/all/v/63/p/{pp2}"):
            ipm[mes_iso(l["D3C"])] = float(l["V"])
    fc = fi = f6 = 1.0
    serie = []
    for x in meses:
        if x not in cdi or x not in ipm:
            continue  # CDI do mês corrente pode não ter saído ainda
        fc *= 1 + cdi[x] / 100
        fi *= 1 + ipm[x] / 100
        f6 *= (1 + ipm[x] / 100) * 1.06 ** (1 / 12)
        serie.append({"mes": x, "cdi": round((fc - 1) * 100, 2), "ipca6": round((f6 - 1) * 100, 2), "ipca": round((fi - 1) * 100, 2)})
    cdi_ipca6 = {"metodo": "acumulado mensal; IPCA + 6% = (1 + IPCA do mês) x 1,06^(1/12)", "serie": serie}

    # Focus: último boletim com dado até a divulgação
    q = urllib.parse.quote
    filtro = q("Indicador eq 'IPCA' and baseCalculo eq 0", safe="")
    url = (f"{OLINDA}?%24filter={filtro}&%24orderby={q('Data desc', safe='')}&%24top=200"
           f"&%24format=json&%24select=Data,DataReferencia,Mediana")
    fx = get(url)["value"]
    limite = divulgacao or dt.date.today().isoformat()
    datas = sorted({r["Data"] for r in fx if r["Data"] <= limite}, reverse=True)
    d0 = datas[0]
    d1 = next((d for d in datas if (dt.date.fromisoformat(d0) - dt.date.fromisoformat(d)).days >= 7), None)
    med = lambda d, ano: next((round(r["Mediana"], 2) for r in fx if r["Data"] == d and str(r["DataReferencia"]) == str(ano)), None)
    pub = dt.date.fromisoformat(d0) + dt.timedelta(days=(7 - dt.date.fromisoformat(d0).weekday()) % 7 or 7)
    focus = {"boletim": d0, "boletim_publicado": pub.isoformat(), "ipca_ano_corrente": med(d0, a),
             "ipca_ano_corrente_anterior": med(d1, a) if d1 else None,
             "anos": [{"ano": y, "ipca": med(d0, y)} for y in range(a, a + 4) if med(d0, y) is not None]}

    dados = {
        "_sobre": "Gerado por fetch_ipca.py. Fontes: IBGE/SIDRA 7060 e 1737; BCB Focus (API Olinda).",
        "referencia": ref,
        "divulgacao": divulgacao or dt.date.today().isoformat(),
        "marca": "invest-xp",
        "indice": {"variacao": ix[("63", ref)], "acumulado_ano": ix[("69", ref)],
                   "acumulado_12m": ix[("2265", ref)], "acumulado_12m_anterior": ix[("2265", ant)]},
        "historico_12m": hist,
        "mesmo_mes_anos_anteriores": mesmo,
        "historico_anual": anual,
        "cdi_ipca6": cdi_ipca6,
        "grupos": grupos,
        "regioes": regioes,
        "matriz": matriz,
        "focus": focus,
        "meta": {"centro": 3.0, "teto": 4.5, "_sobre": "meta contínua do CMN; conferir se mudar"},
        "projecoes": None,
        "textos": {},
    }
    if projecoes:
        dados["projecoes"] = json.loads(pathlib.Path(projecoes).read_text(encoding="utf-8"))
    else:
        dados["projecoes"] = focus_mensal(ref, limite)
    return dados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes")
    ap.add_argument("--projecoes")
    ap.add_argument("--divulgacao", help="AAAA-MM-DD; padrão: hoje")
    a = ap.parse_args()
    d = montar(a.mes, a.projecoes, a.divulgacao)
    out = RAIZ / "dados" / f"ipca-{d['referencia']}.json"
    out.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
