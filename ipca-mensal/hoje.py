#!/usr/bin/env python3
"""Diz ao workflow se há IPCA novo para publicar.

Uso: python ipca-mensal/hoje.py [AAAA-MM]   (sem argumento: o mês anterior ao de hoje, se o SIDRA já tiver)

Escreve no formato do GITHUB_OUTPUT:
    ref=AAAA-MM
    pasta=AAAA-MM-DD/IPCA-AAAA-MM
ou nada, quando não há o que publicar (SIDRA ainda sem o mês, ou o mês já publicado na branch posts).
Supõe a branch posts em ./posts.
"""
import datetime as dt, glob, json, sys, urllib.request

hoje = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).date()
pedido = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else None

if pedido:
    ref = pedido
else:
    a, m = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    ref = f"{a}-{m:02d}"
    url = "https://apisidra.ibge.gov.br/values/t/7060/n1/all/v/63/p/last%201/c315/7169"
    ultimo = json.loads(urllib.request.urlopen(url, timeout=60).read().decode())[1]["D3C"]
    if f"{ultimo[:4]}-{ultimo[4:]}" != ref:
        print(f"SIDRA ainda em {ultimo[:4]}-{ultimo[4:]}; esperando {ref}", file=sys.stderr)
        sys.exit(0)

if glob.glob(f"posts/*/IPCA-{ref}/publicado.json"):
    print(f"IPCA de {ref} já publicado", file=sys.stderr)
    sys.exit(0)

print(f"ref={ref}")
print(f"pasta={hoje.isoformat()}/IPCA-{ref}")
