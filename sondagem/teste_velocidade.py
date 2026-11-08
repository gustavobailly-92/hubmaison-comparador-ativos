"""RAD: complementar() com cache vazio para as 15 primeiras companhias que entregaram ITR na última semana."""
import json, sys, time
from datetime import date, timedelta
sys.path.insert(0, "pipeline")
import rad
OUT = []
ix = json.load(open("res/index.json"))
todas = {c["cvm"] for c in ix["companhias"]}
s = rad._Sessao()
cv = []
for i in range(1, 8):
    for d in rad.listar(date.today() - timedelta(days=i), date.today() - timedelta(days=i), s):
        if d["cvm"] in todas and d["doc"] == "ITR" and d["cvm"] not in cv:
            cv.append(d["cvm"])
cvms = set(cv[:15])
av = []
t = time.time()
n = rad.complementar({}, {}, {}, cvms, date.today(), "cache_teste", av)
OUT.append(f"{len(cvms)} companhias, cache vazio: {n} documentos em {time.time() - t:.0f}s; avisos: {av}")
print(OUT[-1])
open("sondagem/teste_velocidade.txt", "w", encoding="utf-8").write("\n".join(OUT))
