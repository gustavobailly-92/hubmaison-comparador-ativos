"""Sondagem do RAD (sistema de entrega de documentos da CVM): lista os ITR entregues em um intervalo e baixa um deles,
para ver a estrutura do arquivo. Só leitura; grava o que encontrou em sondagem/saida.txt.

Endpoints conforme a biblioteca mercados (PythonicCafe/mercados, mercados/cvm.py).
"""
import io
import json
import re
import sys
import urllib.request
import zipfile
from datetime import date, timedelta
from http.cookiejar import CookieJar

BASE = "https://www.rad.cvm.gov.br/ENET/"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
OUT = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    OUT.append(s)


def get(url, data=None, headers=None):
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with op.open(req, timeout=90) as r:
        return r.read(), dict(r.headers)


def main() -> None:
    html, _ = get(BASE + "frmConsultaExternaCVM.aspx")
    html = html.decode("utf-8", "replace")
    sel = re.search(r'<select[^>]*id="cboCategorias"[^>]*>(.*?)</select>', html, re.S)
    cats = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>', sel.group(1), re.S) if sel else []
    log("categorias:", len(cats))
    for v, t in cats:
        t = re.sub(r"\s+", " ", re.sub("<[^>]+>", "", t)).strip()
        if any(k in t.upper() for k in ("ITR", "DFP", "TRIMESTRA", "PADRONIZADAS", "RELEASE", "COMUNICADO", "FATO")):
            log("  ", v, "|", t)
    cod_itr = next((v for v, t in cats if re.sub("<[^>]+>", "", t).strip().upper().startswith("ITR")), None)
    log("código ITR:", cod_itr)
    cat = f"EST_{int(cod_itr[4:])}" if cod_itr and cod_itr.startswith("9000") else (f"IPE_{int(cod_itr)}_-1_-1" if cod_itr else "")
    fim = date(2026, 11, 7)
    ini = fim - timedelta(days=4)
    form = {"dataDe": ini.strftime("%d/%m/%Y"), "dataAte": fim.strftime("%d/%m/%Y"), "empresa": "", "setorAtividade": "-1",
            "categoriaEmissor": "-1", "situacaoEmissor": "-1", "tipoParticipante": "-1", "dataReferencia": "",
            "categoria": cat, "periodo": "2", "horaIni": "00:00", "horaFim": "23:59", "palavraChave": "",
            "ultimaDtRef": "false", "tipoEmpresa": "0", "token": "", "versaoCaptcha": ""}
    raw, hd = get(BASE + "frmConsultaExternaCVM.aspx/ListarDocumentos", json.dumps(form).encode(),
                  {"Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest"})
    d = json.loads(raw.decode("utf-8", "replace"))["d"]
    log("msgErro:", d.get("msgErro"), "| chaves:", list(d.keys()))
    regs = [r for r in d.get("dados", "").split("$&&*") if r.strip()]
    log("ITR entregues de", ini, "a", fim, ":", len(regs))
    alvo = None
    regs = [r for r in regs if "ITR - " in r or "DFP - " in r]
    log("só ITR e DFP:", len(regs))
    for r in regs[:400]:
        c = [x.strip() for x in r.split("$&")]
        dl = re.search(r"OpenDownloadDocumentos\(([^)]*)\)", c[10] if len(c) > 10 else "")
        p = re.findall(r"'([^']*)'", dl.group(1)) if dl else []
        log(" |", c[0], "|", c[1][:40], "|", c[2], "|", c[5], "|", c[6], "|v", c[8], "| dl:", p)
        if p and alvo is None and "SUZANO" in c[1].upper():
            alvo = (c, p)
    if alvo is None and regs:
        c = [x.strip() for x in regs[0].split("$&")]
        dl = re.search(r"OpenDownloadDocumentos\(([^)]*)\)", c[10])
        alvo = (c, re.findall(r"'([^']*)'", dl.group(1)) if dl else [])
    if alvo and alvo[1]:
        c, p = alvo
        url = (BASE + f"frmDownloadDocumento.aspx?Tela=ext&numSequencia={p[0]}&numVersao={c[8]}&numProtocolo={p[2]}"
               f"&descTipo={p[3]}&CodigoInstituicao=1")
        log("download:", url)
        data, hd = get(url)
        log("bytes:", len(data), "| content-type:", hd.get("Content-Type"), "| disposition:", hd.get("Content-Disposition"))
        mostra_zip(data, 0)


def le_xlsx(data):
    """Planilhas do DadosDocumento.xlsx: {nome: [linhas]}, só com a biblioteca padrão."""
    z = zipfile.ZipFile(io.BytesIO(data))
    sst = [re.sub("<[^>]+>", "", s) for s in re.findall(r"<x:si>(.*?)</x:si>", z.read("xl/sharedStrings.xml").decode("utf-8"), re.S)]
    wb = z.read("xl/workbook.xml").decode("utf-8")
    rels = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', z.read("xl/_rels/workbook.xml.rels").decode("utf-8")))
    rels.update({k: v for v, k in re.findall(r'Target="([^"]+)"[^>]*Id="([^"]+)"', z.read("xl/_rels/workbook.xml.rels").decode("utf-8"))})
    out = {}
    for nome, rid in re.findall(r'<x:sheet name="([^"]+)"[^>]*r:id="([^"]+)"', wb):
        alvo = rels.get(rid, "")
        xml = z.read("xl/" + alvo.lstrip("/").replace("xl/", "")).decode("utf-8")
        linhas = []
        for row in re.findall(r"<x:row[^>]*>(.*?)</x:row>", xml, re.S):
            cel = []
            for attrs, corpo in re.findall(r"<x:c([^>]*)>(.*?)</x:c>", row, re.S):
                v = re.search(r"<x:v>(.*?)</x:v>", corpo, re.S)
                v = v.group(1) if v else re.sub("<[^>]+>", "", corpo)
                cel.append(sst[int(v)] if 't="s"' in attrs and v.isdigit() else v)
            linhas.append(cel)
        out[nome] = linhas
    return out


def mostra_zip(data, nivel):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        log("  " * nivel + "não é zip; início:", data[:300])
        return
    for i in z.infolist():
        log("  " * nivel + f"- {i.filename} ({i.file_size} bytes)")
        b = z.read(i)
        if i.filename == "DadosDocumento.xlsx":
            for nome, linhas in le_xlsx(b).items():
                log(f"  PLANILHA {nome}: {len(linhas)} linhas")
                for ln in linhas[:60 if ("Cons" in nome or "Composi" in nome) else 4]:
                    log("     ", " | ".join(c[:60] for c in ln))
            continue
        if i.filename.lower().endswith((".zip", ".itr", ".dfp")) or b[:2] == b"PK":
            mostra_zip(b, nivel + 1)
        elif i.filename.lower().endswith(".xml") and nivel < 3 and i.file_size < 100000:
            t = b.decode("utf-8", "replace")
            log("  " * nivel + "  início:", t[:1500].replace("\n", " "))
            if "InfoFinaDFin" in i.filename or "<NumeroConta>" in t:
                contas = re.findall(r"<NumeroConta>([^<]*)</NumeroConta>.*?<DescricaoConta1>([^<]*)</DescricaoConta1>(.*?)</InfoFinaDFin>", t, re.S)
                log("  " * nivel + f"  contas: {len(contas)}")
                for n, desc, resto in contas[:40]:
                    vals = re.findall(r"<(ValorConta\d+)>([^<]*)</ValorConta\d+>", resto)
                    log("  " * nivel + f"   {n} | {desc[:50]} | {vals[:6]}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - sondagem: registra o erro e segue para gravar a saída
        import traceback
        log("ERRO:", repr(e))
        log(traceback.format_exc())
    open(sys.argv[1] if len(sys.argv) > 1 else "sondagem/saida.txt", "w", encoding="utf-8").write("\n".join(OUT))
