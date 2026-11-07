#!/usr/bin/env python3
"""Escolhe as empresas do post do dia a partir do index.json da branch resultados.

A CVM publica os dados abertos de ITR e DFP uma vez por semana (domingo de manhã), e o workflow só roda de terça a
sábado; por isso o lote da semana entra na branch na terça. Lote = companhias com a primeira entrega à CVM nos 7 dias
que terminam na entrega mais recente do índice. Dentro do lote: uma ação por companhia (a mais negociada), em ordem de
valor de mercado; terça pega as N primeiras, quarta as N seguintes, e assim até sábado, sem repetir empresa na semana.
Se a entrega mais recente tiver mais de 9 dias, não há lote novo (a branch ainda não recebeu a atualização da CVM).

Uso: python3 selecionar.py index.json [AAAA-MM-DD] [--n 3]
Saída (JSON): {"hoje", "gerado", "branch_de_hoje", "lote": {"de", "ate", "empresas"}, "fatia", "tickers", "aviso"}
"""
import argparse
import json
from datetime import date, timedelta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("indice")
    ap.add_argument("hoje", nargs="?")
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()
    n = a.n
    ix = json.load(open(a.indice, encoding="utf-8"))
    hoje = date.fromisoformat(a.hoje) if a.hoje else date.today()
    gerado = (ix.get("gerado") or "")[:10]
    cias = [c for c in ix["companhias"] if c.get("entrega")]
    out = {"hoje": hoje.isoformat(), "gerado": gerado, "branch_de_hoje": gerado == hoje.isoformat(),
           "lote": None, "fatia": None, "tickers": [], "aviso": None}
    if not cias:
        out["aviso"] = "índice sem datas de entrega"
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    ultima = max(date.fromisoformat(c["entrega"]) for c in cias)
    if (hoje - ultima).days > 9:
        out["aviso"] = (f"sem lote novo: a entrega mais recente no índice é de {ultima.isoformat()}; "
                        "a atualização semanal da CVM ainda não chegou à branch")
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    de = ultima - timedelta(days=6)
    por_cia: dict = {}
    for c in cias:
        if de <= date.fromisoformat(c["entrega"]) <= ultima:
            atual = por_cia.get(c["cvm"])
            if atual is None or (c.get("liq") or 0) > (atual.get("liq") or 0):
                por_cia[c["cvm"]] = c
    lote = sorted(por_cia.values(), key=lambda c: -(c.get("valor_mercado") or 0))
    fatia = max(0, min(4, hoje.weekday() - 1))  # terça = 0 ... sábado = 4 (domingo e segunda: 0)
    escolha = lote[fatia * n:(fatia + 1) * n]
    out.update({"lote": {"de": de.isoformat(), "ate": ultima.isoformat(), "empresas": len(lote)}, "fatia": fatia + 1,
                "tickers": [{"ticker": c["ticker"], "empresa": c["empresa"], "periodo": c["periodo"], "doc": c["doc"],
                             "entrega": c["entrega"], "versao": c.get("versao"), "valor_mercado": c.get("valor_mercado"),
                             "financeira": c.get("financeira")} for c in escolha]})
    if not escolha:
        out["aviso"] = f"o lote de {de.isoformat()} a {ultima.isoformat()} tem {len(lote)} empresas; já cobertas nos dias anteriores"
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
