"""Fundamentos das companhias abertas pelas demonstrações financeiras da CVM (ITR trimestral e DFP anual).

Fonte: dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_AAAA.zip e .../DFP/DADOS/dfp_cia_aberta_AAAA.zip.
Cada ZIP traz um CSV por demonstração (BPA, BPP, DRE, DVA...), consolidada ("con") e individual ("ind"), com as
colunas CD_CVM, DT_REFER, VERSAO, ORDEM_EXERC, DT_INI_EXERC, DT_FIM_EXERC, CD_CONTA, DS_CONTA, VL_CONTA, ESCALA_MOEDA.

Por companhia (código CVM), em cada fim de trimestre:
  pl        patrimônio líquido (BPP 2.03)
  divida    empréstimos e financiamentos, circulante + não circulante (BPP 2.01.04 + 2.02.01)
  caixa     caixa e equivalentes + aplicações financeiras de curto prazo (BPA 1.01.01 + 1.01.02)
  receita   receita de venda de bens e/ou serviços (DRE 3.01), acumulada no ano (YTD)
  ebit      resultado antes do resultado financeiro e dos tributos (DRE 3.05), YTD
  da        depreciação, amortização e exaustão (DVA 7.04.01), YTD
Com isso, o acumulado de 12 meses (LTM) em um trimestre = YTD do trimestre + ano anterior fechado (DFP) − YTD do mesmo
trimestre do ano anterior; EBITDA = EBIT + D&A. Os crescimentos comparam o LTM (ou o PL) mais recente com o de 4, 8 e
12 trimestres antes. Bancos e seguradoras (receita de intermediação financeira ou de seguros na DRE) ficam só com o PL.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import unicodedata
import zipfile
from datetime import date

import fontes_extras as fx

URL_ITR = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{ano}.zip"
URL_DFP = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip"
ANOS_HISTORICO = 5          # anos de demonstrações além do corrente: 36 meses de crescimento em LTM precisam de 4 anos
                            # fechados e, de janeiro a março (DFP do ano anterior ainda não entregue), de um quinto
DIAS_CACHE_CORRENTE = 7     # o extrato do ano corrente é renovado toda semana (a CVM atualiza os ZIPs diariamente); o do ano
                            # anterior também, até abril (a DFP do ano anterior chega até o fim de março)
DIAS_CACHE_FECHADO = 90     # anos fechados: a CVM regera os ZIPs antigos com reapresentações; um refresh por trimestre basta
CONTAS = {
    "BPP": {"2.03": "pl", "2.01.04": "div_c", "2.02.01": "div_nc"},
    "BPA": {"1.01.01": "caixa", "1.01.02": "aplic"},
    "DRE": {"3.01": "receita", "3.05": "ebit"},
    "DVA": {"7.04.01": "da"},
}
log = fx.log


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _baixar(url: str) -> bytes:
    raw = fx.http_get(url, tentativas=3, timeout=900)
    if raw[:2] != b"PK":
        raise RuntimeError("não é ZIP")
    return raw


def _guardar(dados: dict, cvm: int, escopo: str, fim: str, campo: str, ini: str, ver: int, v: float) -> None:
    """Fica o período mais longo (menor DT_INI, o acumulado do ano) e, entre versões da mesma demonstração, a mais recente."""
    d = dados.setdefault((cvm, escopo), {}).setdefault(fim, {})
    atual = d.get(campo)
    if atual is None or (ini and ini < atual[0]) or (ini == atual[0] and ver > -atual[1]):
        d[campo] = (ini, -ver, v)


def _ler_demonstracao(z: zipfile.ZipFile, nome: str, tipo: str, cvms: set[int] | None, dados: dict, fin: dict) -> int:
    """Lê um CSV (uma demonstração, con ou ind) e acumula em dados[(cvm, escopo)][dt_fim][campo] = (ini, -versao, valor).
    Só as contas de CONTAS[tipo], ORDEM_EXERC 'ÚLTIMO' e, nas demonstrações de resultado, o período mais longo
    (acumulado do ano) por data de fim. cvms=None lê todas as companhias. Devolve o número de linhas aproveitadas."""
    contas = CONTAS[tipo]
    escopo = "con" if "_con_" in nome.lower() else "ind"
    n = 0
    with z.open(nome) as fh:
        txt = io.TextIOWrapper(fh, encoding="latin-1", newline="")
        rd = csv.reader(txt, delimiter=";")
        hdr = [h.strip() for h in next(rd)]
        try:
            i_cvm, i_ver, i_ord, i_fim, i_cod, i_ds, i_val, i_esc = (hdr.index(c) for c in ("CD_CVM", "VERSAO", "ORDEM_EXERC", "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA", "ESCALA_MOEDA"))
        except ValueError:
            return 0
        i_ini = hdr.index("DT_INI_EXERC") if "DT_INI_EXERC" in hdr else None
        for c in rd:
            if len(c) <= max(i_cvm, i_ver, i_ord, i_fim, i_cod, i_val, i_esc):
                continue
            try:
                cvm = int(c[i_cvm])
            except ValueError:
                continue
            if cvms is not None and cvm not in cvms:
                continue
            cod = c[i_cod].strip()
            campo = contas.get(cod)
            if tipo == "DRE" and cod == "3.01":
                ds = _norm(c[i_ds])
                if "intermedia" in ds or "seguro" in ds or "premio" in ds:
                    fin[cvm] = True
            if not campo or not _norm(c[i_ord]).startswith("ultimo"):
                continue
            try:
                v = float(c[i_val].replace(",", "."))
            except ValueError:
                continue
            esc = _norm(c[i_esc])
            if esc.startswith("mil"):
                v *= 1000.0
            fim = c[i_fim].strip()[:10]
            ini = c[i_ini].strip()[:10] if i_ini is not None else ""
            try:
                ver = int(c[i_ver])
            except ValueError:
                ver = 0
            _guardar(dados, cvm, escopo, fim, campo, ini, ver, v)
            n += 1
    return n


def _ler_zip(raw: bytes, cvms: set[int] | None, dados: dict, fin: dict) -> int:
    """Lê as demonstrações de interesse (BPA, BPP, DRE, DVA; con e ind) de um ZIP anual da CVM."""
    n = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for nome in z.namelist():
            m = re.search(r"_(BPA|BPP|DRE|DVA)_(con|ind)_\d{4}\.csv$", nome)
            if m:
                n += _ler_demonstracao(z, nome, m.group(1), cvms, dados, fin)
    return n


def _extrato_ano(tipo: str, url: str, ano: int, hoje: date, pasta: str) -> tuple[dict, dict]:
    """Extrato de um ZIP anual (todas as companhias) com cache em JSON: o ano corrente (e o anterior até abril) é renovado
    a cada DIAS_CACHE_CORRENTE dias, os fechados a cada DIAS_CACHE_FECHADO. Guardar só o extrato (poucos MB) evita manter
    os ZIPs (~30 MB cada) no cache."""
    arq = os.path.join(pasta, f"{tipo}_{ano}.json")
    if os.path.exists(arq) and os.path.getsize(arq) > 50:
        idade = (time.time() - os.path.getmtime(arq)) / 86400
        recente = ano >= hoje.year or (ano == hoje.year - 1 and hoje.month <= 4)
        if idade < (DIAS_CACHE_CORRENTE if recente else DIAS_CACHE_FECHADO):
            j = json.load(open(arq, encoding="utf-8"))
            dados = {(int(k.split(":")[0]), k.split(":")[1]): {fim: {c: tuple(x) for c, x in cs.items()} for fim, cs in fins.items()}
                     for k, fins in j["dados"].items()}
            return dados, {int(c): True for c in j["fin"]}
    raw = _baixar(url.format(ano=ano))
    dados: dict = {}
    fin: dict = {}
    n = _ler_zip(raw, None, dados, fin)
    if n == 0:
        raise RuntimeError("ZIP sem as demonstrações esperadas")
    os.makedirs(pasta, exist_ok=True)
    tmp = arq + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"dados": {f"{k[0]}:{k[1]}": v for k, v in dados.items()}, "fin": sorted(fin)}, fh, separators=(",", ":"))
    os.replace(tmp, arq)
    return dados, fin


def _mesclar(dados: dict, extra: dict, cvms: set[int]) -> None:
    for (cvm, escopo), fins in extra.items():
        if cvm not in cvms:
            continue
        for fim, campos in fins.items():
            for campo, (ini, negver, v) in campos.items():
                _guardar(dados, cvm, escopo, fim, campo, ini, -negver, v)


def _ano_antes(dt: str, anos: int) -> str:
    y, m, dd = dt.split("-")
    return f"{int(y) - anos:04d}-{m}-{dd}"


def _val(d: dict, fim: str, campo: str):
    x = (d.get(fim) or {}).get(campo)
    return x[2] if x else None


def _ltm(d: dict, fim: str, campo: str):
    """Acumulado de 12 meses terminado em `fim` (fim de trimestre): YTD + ano anterior fechado − YTD de um ano antes.
    No fim do ano (dezembro) o YTD já é o ano inteiro."""
    ytd = _val(d, fim, campo)
    if ytd is None:
        return None
    if fim[5:] == "12-31":
        return ytd
    y = int(fim[:4])
    anual = _val(d, f"{y - 1}-12-31", campo)
    ytd_ant = _val(d, _ano_antes(fim, 1), campo)
    if anual is None or ytd_ant is None:
        return None
    return ytd + anual - ytd_ant


def _cresc(atual, antes):
    if atual is None or antes is None or antes <= 0 or atual <= 0:
        return None
    return round(atual / antes - 1.0, 4)


def calcular(dados_cvm: dict, fin: dict, hoje: date) -> dict[int, dict]:
    """Por código CVM: o último trimestre com DRE, PL/dívida/caixa desse trimestre, LTM de receita e EBITDA, e os
    crescimentos de 12/24/36 meses. Consolidado quando existe; individual como reserva."""
    out: dict[int, dict] = {}
    cvms = {k[0] for k in dados_cvm}
    for cvm in cvms:
        d = dados_cvm.get((cvm, "con")) or {}
        if not any("receita" in v or "pl" in v for v in d.values()):
            d = dados_cvm.get((cvm, "ind")) or {}
        if not d:
            continue
        fins = sorted(f for f, v in d.items() if "receita" in v or "pl" in v)
        if not fins:
            continue
        fim = fins[-1]
        e_fin = bool(fin.get(cvm))
        pl = _val(d, fim, "pl")
        divida = (_val(d, fim, "div_c") or 0.0) + (_val(d, fim, "div_nc") or 0.0)
        caixa = (_val(d, fim, "caixa") or 0.0) + (_val(d, fim, "aplic") or 0.0)
        rec = _ltm(d, fim, "receita")
        ebit = _ltm(d, fim, "ebit")
        da = _ltm(d, fim, "da")
        ebitda = None if (e_fin or ebit is None or da is None) else ebit + da
        g_pl, g_rec, g_ebitda = [], [], []
        for anos in (1, 2, 3):
            antes = _ano_antes(fim, anos)
            g_pl.append(_cresc(pl, _val(d, antes, "pl")))
            if e_fin:
                g_rec.append(None)
                g_ebitda.append(None)
            else:
                g_rec.append(_cresc(rec, _ltm(d, antes, "receita")))
                eb_a, da_a = _ltm(d, antes, "ebit"), _ltm(d, antes, "da")
                g_ebitda.append(_cresc(ebitda, None if eb_a is None or da_a is None else eb_a + da_a))
        out[cvm] = {"dt": fim, "pl": pl, "divida": divida, "caixa": caixa, "receita": None if e_fin else rec, "ebitda": ebitda,
                    "g_pl": g_pl, "g_rec": g_rec, "g_ebitda": g_ebitda, "fin": e_fin}
    return out


def carregar(cvms: set[int], hoje: date, cache: str, avisos: list[str]) -> dict[int, dict]:
    """Baixa (ou lê do cache) ITR e DFP dos últimos anos e devolve calcular() para as companhias pedidas."""
    if not cvms:
        return {}
    pasta = os.path.join(cache, "cvm_dfs")
    os.makedirs(pasta, exist_ok=True)
    dados: dict = {}
    fin: dict = {}
    anos = list(range(hoje.year - ANOS_HISTORICO, hoje.year + 1))
    t0 = time.time()
    n_arq = 0
    for ano in anos:
        for tipo, url in (("itr", URL_ITR), ("dfp", URL_DFP)):
            try:
                d_ano, fin_ano = _extrato_ano(tipo, url, ano, hoje, pasta)
            except Exception as e:  # noqa: BLE001
                avisos.append(f"CVM {tipo.upper()} {ano}: {e}")
                continue
            _mesclar(dados, d_ano, cvms)
            fin.update({c: True for c in fin_ano if c in cvms})
            n_arq += 1
    res = calcular(dados, fin, hoje)
    log(f"  fundamentos CVM: {n_arq} arquivos (ITR/DFP {anos[0]}-{anos[-1]}), {len(res)} de {len(cvms)} companhias com dados ({int(time.time() - t0)}s)")
    return res


def sintetico(cvms: set[int], hoje: date) -> dict[int, dict]:
    """Base de teste (modo offline): números fictícios, mas plausíveis, por companhia."""
    out = {}
    for k, cvm in enumerate(sorted(cvms)):
        e_fin = k % 5 == 4
        pl = 2.0e9 * (1 + k)
        out[cvm] = {"dt": date(hoje.year, 6, 30).isoformat(), "pl": pl, "divida": 0.6 * pl, "caixa": 0.25 * pl,
                    "receita": None if e_fin else 1.8 * pl, "ebitda": None if e_fin else 0.35 * pl,
                    "g_pl": [round(0.08 + 0.01 * k, 4), round(0.17 + 0.02 * k, 4), round(0.26 + 0.03 * k, 4)],
                    "g_rec": [None] * 3 if e_fin else [round(0.05 + 0.02 * k, 4), round(0.12 + 0.03 * k, 4), round(0.20 + 0.04 * k, 4)],
                    "g_ebitda": [None] * 3 if e_fin else [round(-0.04 + 0.03 * k, 4), round(0.09 + 0.02 * k, 4), round(0.15 + 0.05 * k, 4)], "fin": e_fin}
    return out


def indicadores(f: dict | None, mcap: float | None) -> dict:
    """Indicadores por papel a partir dos fundamentos da companhia e do valor de mercado."""
    if not f:
        return {}
    pl = f.get("pl")
    pvpa = round(mcap / pl, 2) if mcap and pl and pl > 0 else None
    ev = (mcap + (f.get("divida") or 0.0) - (f.get("caixa") or 0.0)) if mcap else None
    eb = f.get("ebitda")
    ev_ebitda = round(ev / eb, 2) if ev is not None and eb and eb > 0 and not f.get("fin") else None
    return {"pvpa": pvpa, "ev_ebitda": ev_ebitda, "g_pl": f.get("g_pl"), "g_rec": f.get("g_rec"), "g_ebitda": f.get("g_ebitda"),
            "fin": bool(f.get("fin")), "dt_fund": f.get("dt"), "pl": f.get("pl"), "ebitda": eb, "receita": f.get("receita"), "divida_liq": (f.get("divida") or 0.0) - (f.get("caixa") or 0.0)}
