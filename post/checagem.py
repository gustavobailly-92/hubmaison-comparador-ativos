#!/usr/bin/env python3
"""Checagens automáticas do JSON de uma empresa antes do post. Só aponta; não corrige nenhum número.

Uso: python3 -I checagem.py dados.json
Imprime uma linha por alerta (nada quando está tudo dentro do esperado).
"""
import json
import sys


def main() -> None:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    S, tri = d.get("serie") or {}, d.get("trimestres") or []
    n = len(tri) - 1
    out = []
    rec, luc = S.get("receita") or [], S.get("lucro") or []

    def v(a, i):
        return a[i] if 0 <= i < len(a) else None

    # lucro: trimestres seguidos que se anulam ou zeros exatos (sinal de erro ao tirar o trimestre do acumulado)
    for i in range(max(1, n - 12), n + 1):
        a, b = v(luc, i - 1), v(luc, i)
        if a is not None and b is not None and a != 0 and abs(a + b) < 1e-6:
            out.append(f"lucro de {tri[i - 1]} e {tri[i]} se anulam ({a:+.6f} e {b:+.6f}): conferir a série")
    zeros = [tri[i] for i in range(max(0, n - 12), n + 1) if v(luc, i) == 0]
    if zeros:
        out.append(f"lucro exatamente zero em {', '.join(zeros)}: conferir a série")
    # escala: lucro maior que a receita, receita que dobra ou cai à metade contra o trimestre anterior
    for i in range(max(0, n - 12), n + 1):
        r, l = v(rec, i), v(luc, i)
        if r and l is not None and abs(l) > abs(r):
            out.append(f"lucro maior que a receita em {tri[i]}")
        r0 = v(rec, i - 1)
        if r and r0 and r0 > 0 and (r / r0 > 2 or r / r0 < 0.5):
            out.append(f"receita de {tri[i]} é {r / r0:.1f}x a de {tri[i - 1]}")
    for k in ("receita", "lucro", "pl"):
        if k in S and v(S[k], n) is None:
            out.append(f"{k} do {tri[n]} ausente (n/d)")
    if (d.get("entrega") or {}).get("versao", 1) > 1:
        out.append(f"reapresentação: versão {d['entrega']['versao']} do documento")
    print("\n".join(out))


if __name__ == "__main__":
    main()
