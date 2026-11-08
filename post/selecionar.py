#!/usr/bin/env python3
"""Escolhe as empresas a postar a partir do index.json da branch resultados.

Com a leitura do RAD (CVM), o index.json traz cada ITR/DFP no mesmo dia da entrega, com a hora. Entram as companhias
cuja primeira entrega do período mais recente caiu nas últimas --horas (padrão 36), uma ação por companhia (a mais
negociada), da entrega mais recente para a mais antiga e, no mesmo dia, por valor de mercado. Ficam de fora as que já
têm pasta na branch posts (já preparadas ou publicadas), para nenhuma empresa repetir. Sem limite por dia, a não ser
que se passe --max.

Uso: python3 selecionar.py index.json [--posts PASTA_DA_BRANCH_POSTS] [--horas 36] [--max 0] [--agora AAAA-MM-DDTHH:MM]
Saída (JSON): {"agora", "gerado", "branch_atualizada", "desde", "tickers": [...], "ja_preparados": [...], "aviso"}
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))


def preparados(pasta: str | None) -> set[str]:
    """Pastas TICKER-PERIODO já existentes em qualquer data da branch posts."""
    out = set()
    if not pasta or not os.path.isdir(pasta):
        return out
    for dia in os.listdir(pasta):
        p = os.path.join(pasta, dia)
        if os.path.isdir(p) and len(dia) == 10 and dia[4] == "-":
            out.update(os.listdir(p))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("indice")
    ap.add_argument("--posts")
    ap.add_argument("--horas", type=float, default=36)
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--agora")
    a = ap.parse_args()
    agora = datetime.fromisoformat(a.agora).replace(tzinfo=BRT) if a.agora else datetime.now(BRT)
    desde = agora - timedelta(hours=a.horas)
    ix = json.load(open(a.indice, encoding="utf-8"))
    gerado = ix.get("gerado") or ""
    try:
        idade = (datetime.now(timezone.utc) - datetime.fromisoformat(gerado.replace("Z", "+00:00"))).total_seconds() / 3600
    except ValueError:
        idade = None
    feitos = preparados(a.posts)
    por_cia: dict = {}
    for c in ix["companhias"]:
        if not c.get("entrega"):
            continue
        quando = datetime.fromisoformat(f"{c['entrega']}T{c.get('hora') or '12:00'}").replace(tzinfo=BRT)
        if not desde <= quando <= agora + timedelta(minutes=5):
            continue
        atual = por_cia.get(c["cvm"])
        if atual is None or (c.get("liq") or 0) > (atual[1].get("liq") or 0):
            por_cia[c["cvm"]] = (quando, c)
    lista = sorted(por_cia.values(), key=lambda x: (x[0].date(), x[1].get("valor_mercado") or 0), reverse=True)
    escolha, ja = [], []
    for quando, c in lista:
        chave = f"{c['ticker']}-{c['periodo']}"
        if chave in feitos:
            ja.append(chave)
            continue
        escolha.append({"ticker": c["ticker"], "empresa": c["empresa"], "periodo": c["periodo"], "doc": c["doc"],
                        "entrega": c["entrega"], "hora": c.get("hora"), "versao": c.get("versao"),
                        "valor_mercado": c.get("valor_mercado"), "financeira": c.get("financeira"), "pasta": chave})
    if a.max:
        escolha = escolha[:a.max]
    aviso = None
    if idade is not None and idade > 26:
        aviso = f"a branch resultados foi gerada há {idade:.0f} horas: os dados podem estar atrasados"
    elif not escolha:
        aviso = f"nenhuma entrega nova à CVM desde {desde.strftime('%d/%m %H:%M')}"
    print(json.dumps({"agora": agora.strftime("%Y-%m-%dT%H:%M"), "gerado": gerado,
                      "branch_atualizada": idade is not None and idade <= 26, "desde": desde.strftime("%Y-%m-%dT%H:%M"),
                      "tickers": escolha, "ja_preparados": ja, "aviso": aviso}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
