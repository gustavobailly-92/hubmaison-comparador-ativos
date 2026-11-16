#!/usr/bin/env python3
"""Monta o JSON semanal do post do Focus a partir da API Olinda do Banco Central.

Uso:
  python3 fetch_focus.py                 # último boletim disponível
  python3 fetch_focus.py --data 2026-11-06   # boletim com dados de uma sexta específica
  python3 fetch_focus.py --raw dados/     # usa raw_*.json já baixados (sem rede)

Saída: dados/focus-AAAA-MM-DD.json (data de divulgação, a segunda-feira).
"""
import argparse, datetime as dt, json, os, sys, time, urllib.parse, urllib.request

API = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"

INDICADORES = [
    # chave, nome na API, rótulo, unidade, casas, escala de relevância de uma mudança semanal
    ("ipca",   "IPCA",      "IPCA",   "%",    2, 0.10),
    ("selic",  "Selic",     "Selic",  "% a.a.", 2, 0.25),
    ("pib",    "PIB Total", "PIB",    "%",    2, 0.10),
    ("cambio", "Câmbio",    "Dólar",  "R$",   2, 0.05),
]
SEMANAS_SERIE = 26
HORIZONTE = 4          # anos à frente do corrente no slide do horizonte
META_INFLACAO = 3.0    # meta contínua do CMN
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def baixar(nome_api, desde):
    filtro = f"Indicador eq '{nome_api}' and baseCalculo eq 0 and Data ge '{desde}'"
    q = urllib.parse.urlencode({
        "$top": "5000", "$filter": filtro, "$orderby": "Data desc", "$format": "json",
        "$select": "Indicador,Data,DataReferencia,Mediana,Minimo,Maximo,numeroRespondentes",
    }, quote_via=urllib.parse.quote)
    ultimo_erro = None
    for tentativa in range(4):  # a API Olinda às vezes devolve corpo vazio
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
                return json.load(r)["value"]
        except Exception as e:
            ultimo_erro = e
            time.sleep(5 * (tentativa + 1))
    raise SystemExit(f"API Olinda falhou para {nome_api}: {ultimo_erro}")


def sexta_da_semana(d):
    return d + dt.timedelta(days=(4 - d.weekday()))


def serie_semanal(linhas, ano):
    """Mediana da última data de cada semana (o boletim usa a sexta)."""
    por_semana = {}
    for x in linhas:
        if x["DataReferencia"] != str(ano):
            continue
        d = dt.date.fromisoformat(x["Data"])
        s = sexta_da_semana(d)
        if s not in por_semana or d > por_semana[s][0]:
            por_semana[s] = (d, x)
    return [(s, v[1]) for s, v in sorted(por_semana.items())]


def sequencia(valores):
    """Sentido da última mudança e há quantas semanas seguidas ele se repete."""
    if len(valores) < 2:
        return "estavel", 0
    def sentido(a, b):
        return "alta" if b > a else "queda" if b < a else "estavel"
    ultimo = sentido(valores[-2], valores[-1])
    n = 0
    for i in range(len(valores) - 1, 0, -1):
        if sentido(valores[i - 1], valores[i]) == ultimo:
            n += 1
        else:
            break
    return ultimo, n


def fmt(v, casas=2):
    return f"{v:.{casas}f}".replace(".", ",")


def ordinal(n):
    return f"{n}ª"


def montar(raw, data_alvo=None):
    datas = sorted({x["Data"] for linhas in raw.values() for x in linhas})
    ultima = dt.date.fromisoformat(data_alvo or datas[-1])
    sexta = sexta_da_semana(ultima) if ultima.weekday() <= 4 else ultima
    if sexta > ultima:
        sexta = ultima  # semana ainda incompleta: usa o último dia disponível
    divulgacao = sexta + dt.timedelta(days=(7 - sexta.weekday()) % 7 or 7)  # segunda seguinte
    ano = sexta.year if sexta.month < 12 or sexta.day < 20 else sexta.year + 1
    anos = [ano, ano + 1]

    out = {
        "boletim": {
            "data_dados": sexta.isoformat(),
            "data_divulgacao": divulgacao.isoformat(),
            "rotulo": f"{divulgacao.day} {MESES[divulgacao.month-1]} {divulgacao.year}",
            "proxima": (divulgacao + dt.timedelta(days=7)).isoformat(),
            "fonte": "Banco Central do Brasil, Relatório Focus (mediana, base de 30 dias)",
        },
        "anos": anos,
        "indicadores": [],
    }
    for chave, nome, rotulo, unidade, casas, escala in INDICADORES:
        linhas = [x for x in raw[chave] if dt.date.fromisoformat(x["Data"]) <= sexta]
        item = {"chave": chave, "rotulo": rotulo, "unidade": unidade, "anos": {}}
        for a in anos:
            ser = serie_semanal(linhas, a)
            if not ser:
                raise SystemExit(f"Sem dados de {nome} {a}")
            vals = [round(x["Mediana"], casas) for _, x in ser]
            atual = vals[-1]
            sem_ant = vals[-2] if len(vals) > 1 else atual
            quatro = vals[-5] if len(vals) > 4 else vals[0]
            sentido, n = sequencia(vals)
            ult = ser[-1][1]
            item["anos"][str(a)] = {
                "mediana": atual,
                "semana_anterior": sem_ant,
                "ha_4_semanas": quatro,
                "variacao_semana": round(atual - sem_ant, casas),
                "sentido": sentido,
                "semanas_seguidas": n,
                "minimo": ult["Minimo"], "maximo": ult["Maximo"],
                "respondentes": ult["numeroRespondentes"],
                "serie": [{"semana": s.isoformat(), "mediana": v} for (s, _), v in
                          list(zip(ser, vals))[-SEMANAS_SERIE:]],
            }
        ult_data = max(x["Data"] for x in linhas)
        item["horizonte"] = [
            {"ano": int(x["DataReferencia"]), "mediana": round(x["Mediana"], casas),
             "respondentes": x["numeroRespondentes"]}
            for x in sorted(linhas, key=lambda x: x["DataReferencia"])
            if x["Data"] == ult_data and anos[0] <= int(x["DataReferencia"]) <= anos[0] + HORIZONTE]
        out["indicadores"].append(item)

    out["destaque"] = escolher_destaque(out)
    out["textos"] = textos(out)
    return out


PESO = {"ipca": 1.3, "selic": 1.3, "pib": 1.0, "cambio": 1.0}


def escolher_destaque(d):
    """Capa: o movimento mais relevante do ano corrente.
    nota = peso x (variação na semana / escala + 0,15 x semanas seguidas); Selic que mexe ganha +1.
    IPCA e Selic pesam mais porque são os que o público acompanha."""
    ano = str(d["anos"][0])
    melhor, nota_melhor = "ipca", 0.0
    for (chave, _, _, _, _, escala), item in zip(INDICADORES, d["indicadores"]):
        a = item["anos"][ano]
        if a["sentido"] == "estavel":
            continue
        nota = PESO[chave] * (abs(a["variacao_semana"]) / escala + 0.15 * a["semanas_seguidas"])
        if chave == "selic":
            nota += 1
        if nota > nota_melhor:
            melhor, nota_melhor = chave, nota
    return {"chave": melhor, "ano": int(ano), "sem_mudanca": nota_melhor == 0}


NOME_ANO = {
    "ipca": "IPCA de {a}", "selic": "Selic no fim de {a}",
    "pib": "PIB de {a}", "cambio": "dólar no fim de {a}",
}
ROTULO_CAPA = {
    "ipca": "IPCA esperado para {a}", "selic": "Selic esperada para o fim de {a}",
    "pib": "PIB esperado para {a}", "cambio": "Dólar esperado para o fim de {a}",
}
ORDINAIS = ["", "primeira", "segunda", "terceira", "quarta", "quinta", "sexta",
            "sétima", "oitava", "nona", "décima"]


def ordinal_extenso(n):
    return ORDINAIS[n] if n < len(ORDINAIS) else f"{n}ª"


def valor(chave, x):
    return f"R$ {fmt(x)}" if chave == "cambio" else f"{fmt(x)}%"


def variacao(chave, d):
    mag = fmt(abs(d))
    return f"R$ {mag}" if chave == "cambio" else f"{mag}%"


def frase_capa(item, ano):
    """Frase sob o número grande: comparação com a semana anterior (valor em <b>)."""
    a = item["anos"][str(ano)]
    ant = valor(item["chave"], a["semana_anterior"])
    if a["sentido"] == "estavel":
        return f"Mesma mediana da semana anterior: <b>{ant}</b>."
    nome = "Alta" if a["sentido"] == "alta" else "Queda"
    return f"{nome} de {variacao(item['chave'], a['variacao_semana'])}: na semana anterior, a mediana era <b>{ant}</b>."


def frase_capa_v4(item, ano):
    """Uma frase só sob o número: o contexto da série e a variação contra a semana anterior."""
    a = item["anos"][str(ano)]
    ctx = contexto_capa(item, ano)
    if a["sentido"] == "estavel":
        return ctx + "." if ctx.startswith("Parada") else "Mesma mediana da semana anterior."
    lado = "acima" if a["sentido"] == "alta" else "abaixo"
    var = variacao(item["chave"], a["variacao_semana"])
    if ctx.endswith("na semana"):
        return f"<b>{var}</b> {lado} da semana anterior."
    return f"{ctx}, <b>{var}</b> {lado} da semana anterior."


def contexto_capa(item, ano):
    """Frase curta ao lado do seletor Queda · Estável · Alta, lida da série semanal."""
    vals = [p["mediana"] for p in item["anos"][str(ano)]["serie"]]
    sent = ["alta" if b > a else "queda" if b < a else "estavel" for a, b in zip(vals, vals[1:])]
    if not sent:
        return ""
    atual, n = sent[-1], 1
    while n < len(sent) and sent[-1 - n] == atual:
        n += 1
    antes = sent[-1 - n] if n < len(sent) else None
    k = 0
    if antes:
        while k < len(sent) - n and sent[-1 - n - k] == antes:
            k += 1
    if atual == "estavel":
        return f"Parada há {n + 1} semanas" if n >= 2 else "Sem mudança na semana"
    palavra = atual
    if n >= 2:
        return f"{ordinal_extenso(n).capitalize()} {palavra} seguida"
    if antes == "estavel" and k >= 2:
        return f"Primeira {palavra} em {k + 1} semanas"
    if antes and antes != "estavel":
        oposto = "altas" if antes == "alta" else "quedas"
        return f"Virada depois de {k} {oposto}" if k >= 2 else f"Virada na semana"
    return f"{palavra.capitalize()} na semana"


def frase_horizonte(d):
    ano = d["anos"][0]
    por = {i["chave"]: i for i in d["indicadores"]}
    sel, ipca = por["selic"]["horizonte"], por["ipca"]["horizonte"]
    ini, fim = sel[0], sel[-1]
    if fim["mediana"] < ini["mediana"]:
        j = f"Selic cai para {valor('selic', fim['mediana'])} até {fim['ano']}"
    elif fim["mediana"] > ini["mediana"]:
        j = f"Selic sobe para {valor('selic', fim['mediana'])} até {fim['ano']}"
    else:
        j = f"Selic em {valor('selic', ini['mediana'])} até {fim['ano']}"
    na_meta = [h["ano"] for h in ipca if h["mediana"] <= META_INFLACAO]
    if na_meta:
        i = f"IPCA na meta de 3% em {na_meta[0]}"
    else:
        i = "IPCA acima da meta em todos os anos"
    return f"{j}; {i}."


NOME_APOIO = {
    "ipca": "o IPCA esperado para {a}", "selic": "a Selic esperada para o fim de {a}",
    "pib": "o PIB esperado para {a}", "cambio": "o dólar esperado para o fim de {a}",
}


def frase_indicador(item, ano):
    a = item["anos"][str(ano)]
    nome = NOME_APOIO[item["chave"]].format(a=ano)
    n = a["semanas_seguidas"]
    if a["sentido"] == "estavel":
        return f"{nome} ficou em {valor(item['chave'], a['mediana'])}"
    verbo = "subiu" if a["sentido"] == "alta" else "caiu"
    frase = f"{nome} {verbo} para {valor(item['chave'], a['mediana'])}"
    if n >= 2:
        frase += f", a {ordinal_extenso(n)} {a['sentido']} seguida"
    return frase


def consenso(d):
    """Dispersão relativa (maior menos menor projeção, sobre a mediana) no ano corrente."""
    ano = str(d["anos"][0])
    disp = {i["chave"]: (i["anos"][ano]["maximo"] - i["anos"][ano]["minimo"]) / abs(i["anos"][ano]["mediana"])
            for i in d["indicadores"]}
    return min(disp, key=disp.get), max(disp, key=disp.get)


NOME_CURTO = {"ipca": "IPCA", "selic": "Selic", "pib": "PIB", "cambio": "dólar"}


def textos(d):
    ano = d["anos"][0]
    por_chave = {i["chave"]: i for i in d["indicadores"]}
    dest = d["destaque"]
    item_dest = por_chave[dest["chave"]]
    outros = sorted(
        (i for i in d["indicadores"] if i["chave"] != dest["chave"]
         and i["anos"][str(ano)]["sentido"] != "estavel"),
        key=lambda i: -i["anos"][str(ano)]["semanas_seguidas"])
    if outros:
        apoio = "Também na semana, " + frase_indicador(outros[0], ano) + "."
    else:
        apoio = f"As demais projeções para {ano} ficaram onde estavam."
    mudaram = sum(1 for i in d["indicadores"] for a in d["anos"]
                  if i["anos"][str(a)]["sentido"] != "estavel")
    maior_cons, menor_cons = consenso(d)
    return {
        "capa_rotulo": ROTULO_CAPA[dest["chave"]].format(a=ano),
        "capa_frase": frase_capa_v4(item_dest, ano),
        "capa_contexto": contexto_capa(item_dest, ano),
        "capa_apoio": apoio,
        "painel_titulo": f"As projeções para {ano}",
        "painel_sub": ((frase_indicador(outros[0], ano)[0].upper() + frase_indicador(outros[0], ano)[1:] + ".")
                       if outros else f"Sem outras mudanças para {ano} na semana."),
        "horizonte_titulo": "Previsão do mercado",
        "horizonte_sub": frase_horizonte(d),
        "consenso_titulo": "Onde há consenso",
        "consenso_sub": f"Da menor à maior projeção de cada indicador para {ano}.",
        "fechamento_titulo": "O mercado, semana a semana",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", help="data dos dados (sexta), AAAA-MM-DD")
    p.add_argument("--raw", help="pasta com raw_<chave>.json já baixados")
    p.add_argument("--saida", default="dados")
    p.add_argument("--divulgacao", help="data em que o boletim saiu (AAAA-MM-DD), quando não foi na segunda")
    args = p.parse_args()

    desde = (dt.date.today() - dt.timedelta(days=SEMANAS_SERIE * 7 + 60)).isoformat()
    raw = {}
    for chave, nome, *_ in INDICADORES:
        if args.raw:
            raw[chave] = json.load(open(os.path.join(args.raw, f"raw_{chave}.json")))["value"]
        else:
            raw[chave] = baixar(nome, desde)
            os.makedirs(os.path.join(args.saida, "raw"), exist_ok=True)
            json.dump({"value": raw[chave]}, open(os.path.join(args.saida, "raw", f"raw_{chave}.json"), "w"))
    d = montar(raw, args.data)
    if args.divulgacao:
        div = dt.date.fromisoformat(args.divulgacao)
        d["boletim"]["data_divulgacao"] = div.isoformat()
        d["boletim"]["rotulo"] = f"{div.day} {MESES[div.month-1]} {div.year}"
        prox = div + dt.timedelta(days=7 - div.weekday())  # segunda seguinte
        d["boletim"]["proxima"] = prox.isoformat()
    os.makedirs(args.saida, exist_ok=True)
    caminho = os.path.join(args.saida, f"focus-{d['boletim']['data_divulgacao']}.json")
    json.dump(d, open(caminho, "w"), ensure_ascii=False, indent=1)
    print(caminho)
    for k in ("capa_rotulo", "capa_frase", "capa_apoio", "painel_sub", "consenso_sub"):
        print(f"  {k}: {d['textos'][k]}")


if __name__ == "__main__":
    main()
