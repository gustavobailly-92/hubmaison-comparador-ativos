#!/usr/bin/env python3
"""Diz ao workflow se há boletim Focus novo para publicar.

Escreve no stdout (formato do $GITHUB_OUTPUT), só quando há o que publicar:
  sexta=AAAA-MM-DD   data da coleta (a do boletim)
  div=AAAA-MM-DD     data da divulgação (hoje, em Brasília)
  pasta=AAAA-MM-DD/FOCUS-AAAA-MM-DD   pasta na branch posts

Há o que publicar quando a API Olinda já tem a sexta mais recente e nenhuma pasta FOCUS daquela sexta
tem publicado.json na branch posts (em checkout em ./posts). Uso: python focus/hoje.py [AAAA-MM-DD da sexta]
"""
import datetime as dt
import glob
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"


def ultima_coleta():
    q = urllib.parse.urlencode({"$top": "1", "$filter": "Indicador eq 'IPCA' and baseCalculo eq 0",
                                "$orderby": "Data desc", "$format": "json", "$select": "Data"},
                               quote_via=urllib.parse.quote)
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
                return dt.date.fromisoformat(json.load(r)["value"][0]["Data"])
        except Exception:  # noqa: BLE001
            time.sleep(5 * (tentativa + 1))
    raise SystemExit("API Olinda fora do ar")


def main():
    hoje = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).date()
    if len(sys.argv) > 1 and sys.argv[1].strip():
        sexta = dt.date.fromisoformat(sys.argv[1].strip())
    else:
        if hoje.weekday() > 2:            # só segunda, terça e quarta
            return
        sexta = hoje - dt.timedelta(days=(hoje.weekday() - 4) % 7)
        if ultima_coleta() < sexta:       # o BC ainda não publicou o boletim desta semana
            print(f"boletim de {sexta} ainda não saiu", file=sys.stderr)
            return
    if glob.glob(os.path.join("posts", "*", f"FOCUS-{sexta}", "publicado.json")):
        print(f"boletim de {sexta} já publicado", file=sys.stderr)
        return
    print(f"sexta={sexta}")
    print(f"div={hoje}")
    print(f"pasta={hoje}/FOCUS-{sexta}")


if __name__ == "__main__":
    main()
