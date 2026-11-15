#!/usr/bin/env python3
"""Escreve a legenda do carrossel do IPCA a partir do JSON do mês e valida o texto.

Uso: python3 legenda.py dados/ipca-AAAA-MM.json > saida/AAAA-MM/legenda.txt

Sai com erro (e o post não é publicado) se a legenda tiver travessão, palavra de risco ou
passar dos limites do Instagram.
"""
import json, sys

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]
PROIBIDAS = ["garantid", "renda certa", "sem risco", "recomendamos", "grátis", "imperdível"]


def pct(v, casas=2, sinal=False):
    s = f"{abs(v):.{casas}f}".replace(".", ",")
    if float(s.replace(",", ".")) == 0:
        return s + "%"
    return ("-" if v < 0 else ("+" if sinal else "")) + s + "%"


def br(iso):
    a, m, d = iso.split("-")
    return f"{d}/{m}/{a}"


def nomes(lista):
    return " e ".join(lista) if len(lista) <= 2 else ", ".join(lista[:-1]) + " e " + lista[-1]


def legenda(d):
    a, m = map(int, d["referencia"].split("-"))
    mes, prox = MESES[m - 1], MESES[m % 12]
    ix, P, f = d["indice"], d.get("projecoes") or {}, d["focus"]
    v = ix["variacao"]
    L = []

    # abertura
    abertura = f"IPCA de {mes}: {pct(v)}"
    med = P.get("mediana")
    if med is not None:
        lo, hi = P.get("intervalo_min"), P.get("intervalo_max")
        if lo is not None and v < lo:
            abertura += ", abaixo até da menor projeção do mercado"
        elif hi is not None and v > hi:
            abertura += ", acima até da maior projeção do mercado"
        elif v < med:
            abertura += ", abaixo do esperado"
        elif v > med:
            abertura += ", acima do esperado"
        else:
            abertura += ", em linha com o esperado"
    L += [abertura + ".", "", "O que mexeu no índice:"]

    if med is not None:
        t = f"• A mediana do mercado ({P['fonte_mediana']}) era {pct(med)}"
        if P.get("intervalo_min") is not None:
            fonte = "" if P.get("fonte_intervalo") == P.get("fonte_mediana") else f" ({P['fonte_intervalo']})"
            t += f", e as estimativas iam de {pct(P['intervalo_min'])} a {pct(P['intervalo_max'])}{fonte}"
        L.append(t + ".")

    g = [dict(x, c=x["peso"] * x["atual"] / 100) for x in d["grupos"]]
    pos = sorted([x for x in g if x["c"] > 0], key=lambda x: -x["c"])
    neg = sorted([x for x in g if x["c"] < 0], key=lambda x: x["c"])
    seg = [x for x in neg if abs(x["c"]) >= 0.05][:2]
    if seg:
        L.append(f"• {nomes([f'{x['nome']} ({pct(x['atual'])})' for x in seg])} "
                 f"{'seguraram' if len(seg) > 1 else 'segurou'} o índice.")
    if pos:
        x = pos[0]
        L.append(f"• {x['nome']} subiu {pct(x['atual'])} e foi o grupo que mais pressionou.")

    rg = d["regioes"]
    n_neg = sum(1 for r in rg if r["atual"] < 0)
    rmin, rmax = min(rg, key=lambda r: r["atual"]), max(rg, key=lambda r: r["atual"])
    if n_neg == 0:
        abre = f"As {len(rg)} regiões tiveram alta."
    elif n_neg == len(rg):
        abre = f"As {len(rg)} regiões tiveram deflação."
    else:
        abre = f"{n_neg} das {len(rg)} regiões {'teve' if n_neg == 1 else 'tiveram'} deflação."
    rio = next((r for r in rg if r["uf"] == "RJ"), None)
    L.append(f"• {abre} {rmax['nome']} teve a maior variação ({pct(rmax['atual'])}) e {rmin['nome']}, "
             f"a menor ({pct(rmin['atual'])})." + (f" No Rio, {pct(rio['atual'])}." if rio else ""))

    # 12 meses e meta
    doze = f"Em 12 meses, a inflação foi a {pct(ix['acumulado_12m'])} (ante {pct(ix['acumulado_12m_anterior'])})"
    teto = (d.get("meta") or {}).get("teto")
    if teto is not None:
        doze += f", {'acima do' if ix['acumulado_12m'] > teto else 'dentro do'} teto da meta, de {pct(teto)}"
    L += ["", doze + f". No ano, {pct(ix['acumulado_ano'])}."]

    # Focus
    alvo = f.get("ipca_ano_corrente")
    if alvo is not None and m < 12:
        falta = ((1 + alvo / 100) / (1 + ix["acumulado_ano"] / 100) - 1) * 100
        quando = "em dezembro" if m == 11 else ("em novembro e dezembro" if m == 10 else "até dezembro")
        L += ["", f"Para {a} fechar nos {pct(alvo)} projetados pelo Boletim Focus, faltam {pct(falta)} {quando}."]

    c = (d.get("cdi_ipca6") or {}).get("serie") or []
    if c:
        anos = round(len(c) / 12)
        n1 = lambda x: f"{x:.1f}".replace(".", ",")
        L += ["", f"Em {anos} anos, IPCA+6% acumulou {n1(c[-1]['ipca6'])}% e o CDI, {n1(c[-1]['cdi'])}%. "
              "Compare outros indicadores em hubmaison.com/comparadordeativos."]

    L += ["", f"Salve este post para comparar quando sair o IPCA de {prox}.", "",
          "#IPCA #inflação #economia #MaisonInvest", ""]

    fontes = f"IBGE ({br(d['divulgacao'])}); Banco Central, Boletim Focus"
    if P.get("fonte_mediana") and P["fonte_mediana"] != "Boletim Focus":
        fontes += f" e CDI; projeções compiladas por {nomes(sorted({P['fonte_mediana'], P.get('fonte_intervalo') or P['fonte_mediana']}))}"
    else:
        fontes += " e CDI"
    L.append("Conteúdo educativo, sem recomendação de investimento. Projeções de mercado não são garantia de resultado. "
             "Rentabilidade passada não garante resultado futuro; indicadores sem impostos e custos. "
             f"Fontes: {fontes}.")
    return "\n".join(L) + "\n"


def validar(txt):
    erros = []
    if "—" in txt or "–" in txt:
        erros.append("travessão")
    for p in PROIBIDAS:
        if p in txt.lower():
            erros.append(f"palavra de risco: {p}")
    if len(txt) > 2200 or txt.count("#") > 30:
        erros.append("passa do limite do Instagram")
    if erros:
        sys.exit("Legenda recusada: " + "; ".join(erros))


if __name__ == "__main__":
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    t = legenda(d)
    validar(t)
    sys.stdout.write(t)
