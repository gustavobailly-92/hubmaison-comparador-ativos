"""Antes e depois da correção do lucro e do escopo, com dados reais (cache do Actions + RAD)."""
import os, sys, subprocess
from datetime import date
sys.path.insert(0, "pipeline")
import fundamentos as fd
OUT = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); OUT.append(s)
cvms = {14443: "Sabesp", 27707: "Automob", 25372: "Assaí", 20958: "ABC Brasil", 25780: "PetroRecôncavo", 18414: "Padtec",
        20036: "BrasilAgro", 24716: "Vamos", 13986: "Suzano", 19348: "Itaú", 4170: "Vale", 9512: "Petrobras"}
av = []
res = fd.carregar(set(cvms), date.today(), "cache", av)
for c, n in cvms.items():
    f = res.get(c)
    if not f:
        log(n, "sem dados"); continue
    s = f["serie"]; b = lambda xs: [None if x is None else round(x / 1e9, 3) for x in xs[-6:]]
    log(f"{n}: dt {f['dt']} | lucro12 {None if f['lucro12'] is None else round(f['lucro12'] / 1e9, 3)} ({f['lucro_base']}) | pl {None if f['pl'] is None else round(f['pl'] / 1e9, 2)}")
    log("   ", s["datas"][-6:]); log("    lucro", b(s["lucro"]), "| receita", b(s["receita"]))
log("avisos:", av)
open("sondagem/teste_lucro.txt", "w", encoding="utf-8").write("\n".join(OUT))
