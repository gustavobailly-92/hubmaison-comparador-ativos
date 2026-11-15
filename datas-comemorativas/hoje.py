#!/usr/bin/env python3
"""Diz ao workflow se hoje (ou a data passada) tem data comemorativa aprovada para publicar.

Saída no formato do GITHUB_OUTPUT: slug=..., data=..., pasta=... (vazios quando não há nada a fazer).
O motivo vai para o stderr, que aparece no log da execução.
"""
import datetime as dt, json, os, sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import ocorrencia  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))


def main():
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    hoje = dt.date.fromisoformat(arg) if arg else dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    cal = json.load(open(os.path.join(AQUI, "calendario.json"), encoding="utf-8"))
    aprov = set(json.load(open(os.path.join(AQUI, "aprovados.json"), encoding="utf-8"))["aprovados"])
    bloco = open(os.path.join(AQUI, "bloco_xp.txt"), encoding="utf-8").read()
    vazio = "slug=\ndata=\npasta="
    for e in cal["datas"]:
        if ocorrencia(e["regra"], hoje.year) != hoje:
            continue
        chave = f"{hoje.isoformat()}/{e['slug']}"
        if chave not in aprov:
            print(f"{chave}: data do dia, mas não está em aprovados.json; não publica", file=sys.stderr)
            print(vazio); return
        if "[" in bloco:
            print("bloco_xp.txt ainda tem marcador [ ]; não publica", file=sys.stderr)
            print(vazio); return
        print(f"{chave}: aprovado, segue", file=sys.stderr)
        print(f"slug={e['slug']}\ndata={hoje.isoformat()}\npasta={hoje.isoformat()}/DATA-{e['slug']}")
        return
    print(f"{hoje}: sem data comemorativa", file=sys.stderr)
    print(vazio)


if __name__ == "__main__":
    main()
