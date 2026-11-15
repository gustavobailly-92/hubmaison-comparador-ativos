#!/usr/bin/env python3
"""Diz ao workflow quais datas aprovadas do dia já podem ser publicadas.

Saída no formato do GITHUB_OUTPUT: lista=<pasta> <pasta> ... (vazia quando não há nada a fazer).
Cada data tem um horário (padrão 07:40; ex.: Crianças 11:40, no mesmo dia de Aparecida). Uma data entra
quando o horário dela já passou. O workflow pula a pasta que já tem publicado.json.
Uso: python3 hoje.py [AAAA-MM-DD [HH:MM]]   (sem argumentos: agora, em Brasília)
"""
import datetime as dt, json, os, sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import ocorrencia  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))


def main():
    agora = dt.datetime.now(ZoneInfo("America/Sao_Paulo"))
    a = [x for x in sys.argv[1:] if x.strip()]
    hoje = dt.date.fromisoformat(a[0]) if a else agora.date()
    hora = a[1] if len(a) > 1 else ("23:59" if a else agora.strftime("%H:%M"))
    cal = json.load(open(os.path.join(AQUI, "calendario.json"), encoding="utf-8"))
    aprov = set(json.load(open(os.path.join(AQUI, "aprovados.json"), encoding="utf-8"))["aprovados"])
    bloco = open(os.path.join(AQUI, "bloco_xp.txt"), encoding="utf-8").read()
    if "[" in bloco:
        print("bloco_xp.txt com marcador [ ]; não publica nada", file=sys.stderr)
        print("lista="); return
    lista = []
    for e in cal["datas"]:
        if ocorrencia(e["regra"], hoje.year) != hoje:
            continue
        chave = f"{hoje.isoformat()}/{e['slug']}"
        h = e.get("horario", cal["horario_publicacao"])
        if chave not in aprov:
            print(f"{chave}: não está em aprovados.json", file=sys.stderr)
        elif h > hora:
            print(f"{chave}: aprovado, sai às {h}", file=sys.stderr)
        else:
            print(f"{chave}: aprovado, segue", file=sys.stderr)
            lista.append(f"{hoje.isoformat()}/DATA-{e['slug']}")
    if not lista:
        print(f"{hoje} {hora}: nada a publicar agora", file=sys.stderr)
    print("lista=" + " ".join(lista))


if __name__ == "__main__":
    main()
