"""RAD: tempo por download e taxa de falha com 1, 2 e 3 downloads simultâneos (amostra de documentos do 3T26)."""
import io, json, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
sys.path.insert(0, "pipeline")
import rad
OUT = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); OUT.append(s)
ix = json.load(open("res/index.json"))
cvms = {c["cvm"] for c in ix["companhias"]}
s = rad._Sessao()
docs = []
for i in range(1, 8):
    docs += [d for d in rad.listar(date.today() - timedelta(days=i), date.today() - timedelta(days=i), s) if d["cvm"] in cvms and d["doc"] == "ITR"]
log("amostra disponível:", len(docs))
def um(doc, sess):
    t = time.time()
    try:
        b = sess.abrir(doc["url"])
    except Exception as e:  # noqa: BLE001
        return time.time() - t, f"erro {e}", 0
    ok = b[:2] == b"PK"
    return time.time() - t, "zip" if ok else "não zip: " + b[:160].decode("latin-1", "replace").replace("\n", " "), len(b)
pos = 0
for par in (1, 2, 3):
    lote = docs[pos:pos + 6]; pos += 6
    t0 = time.time()
    sess = [rad._Sessao() for _ in range(par)]
    with ThreadPoolExecutor(par) as ex:
        res = list(ex.map(lambda x: um(x[1], sess[x[0] % par]), enumerate(lote)))
    ok = sum(1 for _, st, _ in res if st == "zip")
    log(f"== {par} simultâneo(s): {ok}/{len(lote)} zip em {time.time() - t0:.0f}s")
    for (dt, st, n), d in zip(res, lote):
        log(f"   {d['empresa'][:30]:30} {dt:5.1f}s {n/1e6:5.1f} MB {st}")
open("sondagem/teste_velocidade.txt", "w", encoding="utf-8").write("\n".join(OUT))
