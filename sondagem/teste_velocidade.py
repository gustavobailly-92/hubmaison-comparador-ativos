"""Velocidade do RAD: pior caso (cache vazio, todo documento da janela) e segunda execução (tudo em cache)."""
import json, sys, time
from datetime import date
sys.path.insert(0, "pipeline")
import rad
OUT = []
ix = json.load(open("res/index.json"))
cvms = {c["cvm"] for c in ix["companhias"]}
for rodada in ("cache vazio", "cache cheio"):
    av = []
    t = time.time()
    n = rad.complementar({}, {}, {}, cvms, date.today(), "cache_teste", av)
    OUT.append(f"{rodada}: {n} documentos, {time.time() - t:.0f}s; avisos: {av[:5]}")
    print(OUT[-1])
open("sondagem/teste_velocidade.txt", "w", encoding="utf-8").write("\n".join(OUT))
