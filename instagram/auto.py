"""Escolhe os carrosséis que podem ir ao ar sozinhos no @maison.invest (regra do Gustavo de 10/11/2026).

Publica sem esperar o ok dele só o carrossel que cumpre tudo:
- resultado trimestral confirmado pela CVM (ITR ou DFP com data de entrega), entregue a partir de REGRA_DESDE;
- receita do trimestre acima de R$ 500 mi (conta 3.01 da DRE, campo receita_301 do JSON; bancos e seguradoras inclusive);
- avisos.txt existe e está vazio (qualquer aviso do gerador ou da checagem segura a pasta para revisão);
- ainda sem publicado.json (o arquivo marca o que já foi ao ar, pela API ou à mão, e nunca deixa repetir);
- não é notícia (capa do tipo resultado).

Uso: python instagram/auto.py PASTA_POSTS PASTA_RESULTADOS
Imprime uma pasta elegível por linha (AAAA-MM-DD/TICKER-PERIODO) e, no GITHUB_STEP_SUMMARY quando houver, a lista das
que ficaram pendentes e por quê.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

REGRA_DESDE = "2026-11-10"      # vale para as entregas daqui em diante
RECEITA_MIN = 0.5               # R$ bi no trimestre (conta 3.01)
PASTA = re.compile(r"^(\d{4}-\d{2}-\d{2})/([A-Z0-9]{4,6})-([1-4]T\d{2})$")


def avaliar(posts: str, dados: str):
    ok, presas = [], []
    for d in sorted(glob.glob(os.path.join(posts, "????-??-??", "*"))):
        if not os.path.isdir(d):
            continue
        rel = os.path.relpath(d, posts).replace(os.sep, "/")
        m = PASTA.match(rel)
        if not m or m.group(1) < REGRA_DESDE:
            continue
        if os.path.exists(os.path.join(d, "publicado.json")):
            continue
        ticker, periodo = m.group(2), m.group(3)
        motivo = None
        av = os.path.join(d, "avisos.txt")
        if not os.path.exists(av):
            motivo = "sem avisos.txt (gerado fora do fluxo automático)"
        elif open(av, encoding="utf-8").read().strip():
            motivo = "avisos: " + "; ".join(x.strip() for x in open(av, encoding="utf-8") if x.strip())
        j = os.path.join(dados, f"{ticker}.json")
        if motivo is None:
            if not os.path.exists(j):
                motivo = "sem o JSON da empresa na branch resultados"
            else:
                x = json.load(open(j, encoding="utf-8"))
                ent = (x.get("entrega") or {}).get("primeira") or x.get("divulgacao") or ""
                rec = x.get("receita_301")
                if x.get("periodo") != periodo:
                    motivo = f"o JSON está em {x.get('periodo')}, a pasta em {periodo}"
                elif (x.get("capa") or {}).get("tipo") != "resultado":
                    motivo = "não é post de resultado"
                elif not ent or ent < REGRA_DESDE:
                    motivo = f"entregue em {ent or 'data desconhecida'}, antes da regra ({REGRA_DESDE})"
                elif rec is None:
                    motivo = "receita do trimestre (conta 3.01) ausente"
                elif rec <= RECEITA_MIN:
                    motivo = f"receita do trimestre de R$ {rec * 1000:.0f} mi, abaixo de R$ 500 mi"
        if motivo is None:
            ok.append(rel)
        else:
            presas.append((rel, motivo))
    return ok, presas


def main() -> None:
    ok, presas = avaliar(sys.argv[1], sys.argv[2])
    print("\n".join(ok))
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(f"### Publicação automática\n\nElegíveis: {', '.join(ok) or 'nenhuma'}\n\n")
            if presas:
                f.write("Pendentes (não publicam sozinhas):\n\n" + "".join(f"- **{p}**: {m}\n" for p, m in presas))


if __name__ == "__main__":
    main()
