"""ITR e DFP no mesmo dia, pelo RAD da CVM (sistema de entrega de documentos).

Os dados abertos de ITR e DFP da CVM são atualizados uma vez por semana. O RAD mostra cada documento na hora em que a
companhia entrega, com uma planilha (DadosDocumento.xlsx) das demonstrações nas mesmas contas dos dados abertos
(1 ativo, 2.03 PL, 3.01 receita, 3.05 EBIT, 3.11 lucro, 7.04.01 depreciação...). complementar() lê os ITR e DFP
entregues nos últimos DIAS_RAD dias que ainda não estão no extrato semanal (ou que estão numa versão mais antiga) e os
acrescenta a dados/fin/receb no mesmo formato de fundamentos._ler_demonstracao. Cada documento lido fica em cache.

Endpoints conforme a biblioteca mercados (github.com/PythonicCafe/mercados, mercados/cvm.py).
"""
from __future__ import annotations

import io
import json
import os
import re
import threading
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from http.cookiejar import CookieJar

import fontes_extras as fx

BASE = "https://www.rad.cvm.gov.br/ENET/"
DIAS_RAD = 21        # cobre com folga a semana de atraso dos dados abertos
PARALELO = 3         # downloads simultâneos; o RAD recusa os que passam do limite dele, e baixar() tenta de novo
UA_NAV = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
PLANILHAS = {"Ativo": "BPA", "Passivo": "BPP", "Resultado Periodo": "DRE", "Valor Adicionado": "DVA"}
log = fx.log


class _Sessao:
    def __init__(self) -> None:
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.pronta = False

    def abrir(self, url: str, dados: bytes | None = None, headers: dict | None = None, tentativas: int = 3) -> bytes:
        if not self.pronta:   # a busca pede o cookie da página de consulta
            self._uma(BASE + "frmConsultaExternaCVM.aspx")
            self.pronta = True
        return self._uma(url, dados, headers, tentativas)

    def _uma(self, url: str, dados: bytes | None = None, headers: dict | None = None, tentativas: int = 3) -> bytes:
        ultimo = None
        for i in range(tentativas):
            try:
                req = urllib.request.Request(url, data=dados, headers={"User-Agent": UA_NAV, **(headers or {})})
                with self.op.open(req, timeout=120) as r:
                    return r.read()
            except Exception as e:  # noqa: BLE001
                ultimo = e
                time.sleep(3 * (i + 1))
        raise RuntimeError(f"{url[:90]}: {ultimo}")


def _iso_span(campo: str) -> str:
    m = re.search(r"<spanOrder>(\d{8})</spanOrder>", campo)
    return f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else ""


def listar(ini: date, fim: date, sessao: _Sessao | None = None) -> list[dict]:
    """ITR e DFP entregues entre ini e fim (inclusive): cvm, empresa, doc, ref, entrega (AAAA-MM-DDTHH:MM), versao, url."""
    s = sessao or _Sessao()
    form = {"dataDe": ini.strftime("%d/%m/%Y"), "dataAte": fim.strftime("%d/%m/%Y"), "empresa": "", "setorAtividade": "-1",
            "categoriaEmissor": "-1", "situacaoEmissor": "-1", "tipoParticipante": "-1", "dataReferencia": "", "categoria": "",
            "periodo": "2", "horaIni": "00:00", "horaFim": "23:59", "palavraChave": "", "ultimaDtRef": "false",
            "tipoEmpresa": "0", "token": "", "versaoCaptcha": ""}
    raw = s.abrir(BASE + "frmConsultaExternaCVM.aspx/ListarDocumentos", json.dumps(form).encode(),
                  {"Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest"})
    d = json.loads(raw.decode("utf-8", "replace"))["d"]
    if d.get("msgErro"):
        raise RuntimeError(f"RAD: {d['msgErro']}")
    out = []
    for reg in (d.get("dados") or "").split("$&&*"):
        c = [x.strip() for x in reg.split("$&")]
        if len(c) < 11:
            continue
        doc = "ITR" if c[2].startswith("ITR") else "DFP" if c[2].startswith("DFP") else None
        if not doc or "cancel" in c[7].lower():
            continue
        m = re.search(r"OpenDownloadDocumentos\(([^)]*)\)", c[10])
        p = re.findall(r"'([^']*)'", m.group(1)) if m else []
        hm = re.search(r"(\d{2}):(\d{2})", c[6].split("</spanOrder>")[-1])
        try:
            cvm, ver = int(re.sub(r"\D", "", c[0])), int(c[8])
        except ValueError:
            continue
        if len(p) < 4:
            continue
        ent = _iso_span(c[6]) + (f"T{hm.group(1)}:{hm.group(2)}" if hm else "")
        out.append({"cvm": cvm, "empresa": c[1], "doc": doc, "ref": _iso_span(c[5]), "entrega": ent, "versao": ver,
                    "protocolo": p[2],
                    "url": (BASE + f"frmDownloadDocumento.aspx?Tela=ext&numSequencia={p[0]}&numVersao={ver}"
                            f"&numProtocolo={p[2]}&descTipo={p[3] or doc}&CodigoInstituicao=1")})
    return out


def _planilhas(data: bytes) -> dict[str, list[list[str]]]:
    """DadosDocumento.xlsx -> {nome da planilha: linhas}, só com a biblioteca padrão."""
    z = zipfile.ZipFile(io.BytesIO(data))
    sst = [re.sub("<[^>]+>", "", s) for s in re.findall(r"<x:si>(.*?)</x:si>", z.read("xl/sharedStrings.xml").decode("utf-8"), re.S)]
    rels_xml = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    rels = {}
    for tag in re.findall(r"<Relationship[^>]*>", rels_xml):
        i, t = re.search(r'Id="([^"]+)"', tag), re.search(r'Target="([^"]+)"', tag)
        if i and t:
            rels[i.group(1)] = t.group(1)
    out = {}
    for nome, rid in re.findall(r'<x:sheet name="([^"]+)"[^>]*r:id="([^"]+)"', z.read("xl/workbook.xml").decode("utf-8")):
        alvo = rels.get(rid, "").lstrip("/")
        alvo = alvo if alvo.startswith("xl/") else "xl/" + alvo
        linhas = []
        for row in re.findall(r"<x:row[^>]*>(.*?)</x:row>", z.read(alvo).decode("utf-8"), re.S):
            cel = []
            for attrs, corpo in re.findall(r"<x:c([^>]*)>(.*?)</x:c>", row, re.S):
                v = re.search(r"<x:v>(.*?)</x:v>", corpo, re.S)
                v = v.group(1) if v else re.sub("<[^>]+>", "", corpo)
                # texto (string compartilhada ou inline) vem formatado em pt-BR; célula numérica leva "#" para _num
                cel.append(sst[int(v)] if 't="s"' in attrs and v.isdigit() else v if "t=" in attrs else "#" + v)
            linhas.append(cel)
        out[nome] = linhas
    return out


def _num(s: str) -> float | None:
    """'16.515.544' e '121.449' (ponto de milhar), '1,70815' (vírgula decimal); '#123.5' é célula numérica do Excel."""
    s = (s or "").strip()
    if not s or s == "#":
        return None
    try:
        return float(s[1:]) if s.startswith("#") else float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def ler_documento(raw: bytes) -> dict:
    """ZIP do RAD -> {"escopo", "ini_ano", "linhas": [[tipo, conta, descrição, valor em reais], ...]}.
    Demonstração de resultado e DVA: acumulado do ano; balanço: posição no fim do período. Consolidado quando existe."""
    z = zipfile.ZipFile(io.BytesIO(raw))
    nomes = z.namelist()
    xlsx = next((n for n in nomes if n.lower().endswith("dadosdocumento.xlsx")), None)
    if not xlsx:
        raise RuntimeError("documento sem DadosDocumento.xlsx")
    ini_ano = ""
    xml = next((n for n in nomes if n.lower().endswith(".xml")), None)
    if xml:
        with z.open(xml) as fh:
            cab = fh.read(40000).decode("utf-8", "replace")
        m = re.search(r"<DtInicioExercicioSocialCurso>(\d{2})/(\d{2})/(\d{4})<", cab) or \
            re.search(r"<DataInicioExercicioSocial\w*>(\d{2})/(\d{2})/(\d{4})<", cab)
        if m:
            ini_ano = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    pl = _planilhas(z.read(xlsx))
    # consolidado só quando tem números: sem controladas, a planilha "DF Cons" vem com as contas zeradas
    def ativo_total(rows: list[list[str]]) -> float:
        if len(rows) < 2:
            return 0.0
        hdr = [h.strip().lower() for h in rows[0]]
        if "codigo conta" not in hdr or "valor trimestre atual" not in hdr and "valor ultimo exercicio" not in hdr:
            return 0.0
        i_c = hdr.index("codigo conta")
        i_v = hdr.index("valor trimestre atual") if "valor trimestre atual" in hdr else hdr.index("valor ultimo exercicio")
        return next((abs(_num(r[i_v]) or 0.0) for r in rows[1:] if len(r) > i_v and r[i_c].strip() == "1"), 0.0)
    escopo = "con" if ativo_total(pl.get("DF Cons Ativo", [])) > 0 else "ind"
    linhas = []
    for sufixo, tipo in PLANILHAS.items():
        rows = pl.get(f"DF {'Cons' if escopo == 'con' else 'Ind'} {sufixo}") or []
        if len(rows) < 2:
            continue
        hdr = [h.strip().lower() for h in rows[0]]
        try:
            i_cod, i_ds = hdr.index("codigo conta"), hdr.index("descricao conta")
        except ValueError:
            continue
        pref = (["valor acumulado atual exercicio", "valor ultimo exercicio", "valor trimestre atual"] if tipo in ("DRE", "DVA")
                else ["valor trimestre atual", "valor ultimo exercicio"])
        i_v = next((hdr.index(p) for p in pref if p in hdr), None)
        if i_v is None:
            continue
        i_p = hdr.index("precisao") if "precisao" in hdr else None
        for r in rows[1:]:
            if len(r) <= max(i_cod, i_ds, i_v):
                continue
            v = _num(r[i_v])
            if v is None:
                continue
            esc = (r[i_p] if i_p is not None and len(r) > i_p else "").strip().lower()
            linhas.append([tipo, r[i_cod].strip(), r[i_ds].strip(), v * 1000.0 if esc.startswith("mil") else v])
    return {"escopo": escopo, "ini_ano": ini_ano, "linhas": linhas}


def complementar(dados: dict, fin: dict, receb: dict, cvms: set[int], hoje: date, cache: str, avisos: list[str]) -> int:
    """Acrescenta os ITR/DFP entregues nos últimos DIAS_RAD dias que o extrato semanal ainda não tem (ou tem em versão
    mais antiga). receb ganha a hora da entrega (5º elemento). Devolve o número de documentos acrescentados."""
    import fundamentos as fd   # import tardio: fundamentos importa este módulo dentro de carregar()

    pasta = os.path.join(cache, "rad")
    os.makedirs(pasta, exist_ok=True)
    s = _Sessao()
    t0 = time.time()
    docs, falhas, de_cache = [], 0, 0
    for i in range(DIAS_RAD + 1):   # um dia por consulta: a resposta do RAD traz todos os documentos do período, sem paginação
        dia = hoje - timedelta(days=i)
        arq_l = os.path.join(pasta, f"lista-{dia.isoformat()}.json")
        if i >= 2 and os.path.exists(arq_l):   # dia fechado há mais de um dia: a lista não muda mais
            docs += json.load(open(arq_l, encoding="utf-8"))
            de_cache += 1
            continue
        try:
            lista = listar(dia, dia, s)
        except Exception as e:  # noqa: BLE001
            falhas += 1
            if falhas == 1:
                avisos.append(f"RAD (CVM): busca de {dia.isoformat()} falhou: {e}")
            continue
        docs += lista
        if i >= 1:   # ontem já fechou; a partir de amanhã esta lista vem do cache
            json.dump(lista, open(arq_l, "w", encoding="utf-8"), ensure_ascii=False)
    if not docs and falhas:
        return 0
    t_lista = time.time() - t0

    # por companhia e período: a versão mais recente dá os números; a primeira entrega dá a data e a hora
    grupos: dict = {}
    for d in docs:
        if d["cvm"] in cvms and d["ref"]:
            grupos.setdefault((d["cvm"], d["ref"]), []).append(d)
    pend = []
    for (cvm, ref), ds in grupos.items():
        ult = max(ds, key=lambda x: x["versao"])
        r = receb.get(f"{cvm}:{ref}")
        if r is not None and (r[2] or 0) >= ult["versao"]:
            continue   # o extrato semanal já tem esta versão
        pend.append((ult, min(x["entrega"] for x in ds), r))

    local = threading.local()

    def baixar(doc: dict):
        arq = os.path.join(pasta, re.sub(r"[^\w.-]", "_", doc["protocolo"]) + ".json")
        if os.path.exists(arq):
            lido = json.load(open(arq, encoding="utf-8"))
            zerado = lido.get("escopo") == "con" and not any(l[0] == "BPA" and l[1] == "1" and l[3] for l in lido.get("linhas", []))
            if not zerado:   # lido antes da correção com o consolidado vazio: baixa de novo
                return lido, None, False
        try:
            if not hasattr(local, "s"):
                local.s = _Sessao()
            # com outro download em curso, o RAD devolve na hora a página de consulta em vez do ZIP: espera e tenta de novo
            for tentativa in range(8):
                raw = local.s.abrir(doc["url"])
                if raw[:2] == b"PK":
                    break
                time.sleep(4 + 6 * tentativa)
            else:
                raise RuntimeError("o RAD devolveu a página de consulta em vez do arquivo, 8 vezes")
            lido = ler_documento(raw)
            json.dump(lido, open(arq, "w", encoding="utf-8"), ensure_ascii=False)
            return lido, None, True
        except Exception as e:  # noqa: BLE001
            return None, e, True

    t1 = time.time()
    with ThreadPoolExecutor(max_workers=PARALELO) as ex:   # o RAD responde devagar (ZIP de ~7 MB por documento)
        res = list(ex.map(baixar, [p[0] for p in pend]))
    t_dl = time.time() - t1
    n = baixados = 0
    for (doc, primeira, r), (lido, erro, baixou) in zip(pend, res):
        baixados += baixou
        cvm, ref, ver = doc["cvm"], doc["ref"], doc["versao"]
        if erro is not None:
            avisos.append(f"RAD (CVM): {doc['empresa'][:40]} {doc['doc']} {ref}: {erro}")
            continue
        ini = lido.get("ini_ano") or f"{ref[:4]}-01-01"
        for tipo, cod, ds, v in lido["linhas"]:
            dsn = fd._norm(ds)
            campo = fd._campo(tipo, cod, dsn)
            if tipo == "DRE" and cod == "3.01" and any(p in dsn for p in fd.FIN_RECEITA):
                fin[cvm] = True
            if campo == "pl" and cod != "2.03":
                fin[cvm] = True
            if campo:
                fd._guardar(dados, cvm, lido["escopo"], ref, campo, ini if tipo in ("DRE", "DVA") else "", ver, v)
        k = f"{cvm}:{ref}"
        dia, hora = primeira[:10], primeira[11:16] or None
        if r is None:
            receb[k] = [dia, doc["entrega"][:10], ver, doc["doc"], hora]
        else:
            receb[k] = [r[0] or dia, doc["entrega"][:10], ver, r[3] or doc["doc"], r[4] if len(r) > 4 else None]
        n += 1
    log(f"  RAD (CVM): {len(docs)} ITR/DFP nos últimos {DIAS_RAD} dias (listas em {t_lista:.0f}s, {de_cache} dias do cache); "
        f"{len(pend)} fora do extrato semanal, {baixados} baixados em {t_dl:.0f}s, {n} acrescentados")
    return n
