"""Teste da ingestão no mesmo dia: fundamentos.carregar com o RAD para algumas companhias. Grava sondagem/teste_rad.txt."""
import os, sys, json, time
from datetime import date
sys.path.insert(0, "pipeline")
import fundamentos as fd
OUT = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.append(s)
cvms = {13986: "Suzano", 19348: "Itaú", 5258: "Raia", 9512: "Petrobras", 4170: "Vale", 14320: "Usiminas"}
av = []
t0 = time.time()
for rad_on in ("0", "1"):
    os.environ["RAD"] = rad_on
    res = fd.carregar(set(cvms), date.today(), "cache", av)
    log(f"== RAD={rad_on} ({int(time.time() - t0)}s)")
    for c, n in cvms.items():
        f = res.get(c)
        if not f:
            log(n, "sem dados"); continue
        s = f["serie"]
        bi = lambda xs: [None if x is None else round(x / 1e9, 3) for x in xs[-5:]]
        log(n, "| dt", f["dt"], "| entrega", f["entrega"], "| fin", f["fin"])
        log("   datas", s["datas"][-5:]); log("   receita", bi(s["receita"])); log("   ebitda", bi(s["ebitda"]))
        log("   lucro", bi(s["lucro"])); log("   pl", bi(s["pl"])); log("   ativo", bi(s["ativo"]))
log("avisos:", av)
open("sondagem/teste_rad.txt", "w", encoding="utf-8").write("\n".join(OUT))
