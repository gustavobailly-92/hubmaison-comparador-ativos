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
  da        depreciação, amortização e exaustão (DVA 7.04.01, publicada com sinal negativo; usada em módulo), YTD
  lucro     lucro/prejuízo do período (DRE, conta de segundo nível com esse nome; 3.11 nas empresas), YTD; lucro_c é a parte
            atribuída aos sócios da controladora (3.11.01), usada quando existe
  ativo     ativo total (BPA 1)
Com isso, o acumulado de 12 meses (LTM) em um trimestre = YTD do trimestre + ano anterior fechado (DFP) − YTD do mesmo
trimestre do ano anterior; EBITDA = EBIT + D&A. Os crescimentos comparam o LTM (ou o PL) mais recente com o de 4, 8 e
12 trimestres antes. Bancos e seguradoras (receita de intermediação financeira ou de seguros na DRE, ou PL fora da conta 2.03)
ficam só com o PL e o seu crescimento.
Para o post diário de resultados (doc_resultado), cada companhia leva também a série dos 16 últimos trimestres (valor do
trimestre de receita, EBITDA e lucro; PL, dívida e ativo no fim do trimestre), o P/L e a data em que a CVM recebeu o ITR/DFP.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import calendar
import time
import unicodedata
import zipfile
from datetime import date

import fontes_extras as fx

URL_ITR = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{ano}.zip"
URL_DFP = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip"
ANOS_HISTORICO = 5          # anos de demonstrações além do corrente: 36 meses de crescimento em LTM precisam de 4 anos
                            # fechados e, de janeiro a março (DFP do ano anterior ainda não entregue), de um quinto
DIAS_CACHE_CORRENTE = 1     # o extrato do ano corrente é renovado a cada execução (a CVM atualiza os ZIPs diariamente e o post
                            # de resultados precisa do ITR entregue na véspera); o do ano anterior também, até abril (a DFP do
                            # ano anterior chega até o fim de março). Conta pela data do arquivo, não por 24 horas corridas
DIAS_CACHE_FECHADO = 90     # anos fechados: a CVM regera os ZIPs antigos com reapresentações; um refresh por trimestre basta
EXTRATO_VERSAO = 3          # formato do extrato em cache; muda quando a leitura das contas muda (2 = contas confirmadas pelo nome;
                            # 3 = lucro, ativo total e a data de recebimento de cada documento)
TRIMESTRES_SERIE = 16       # trimestres na série do post de resultados (36 meses de variação + 3 de folga para o acumulado)
# (campo, código da conta, começo do nome normalizado): o nome confirma a conta, porque bancos e seguradoras usam outro
# plano no balanço (PL em 2.07 ou 2.08; 2.02.01 = Depósitos; 2.01.04 = Capitalização) e outro na DRE (3.05 = resultado
# antes dos tributos). O PL é reconhecido pelo nome em qualquer conta de segundo nível.
# Opcionalmente, (…, trechos que excluem, trechos dos quais pelo menos um é exigido). O lucro é a conta de segundo nível
# "Lucro/Prejuízo (Consolidado) do Período" (3.11 nas empresas; outro número em bancos e seguradoras), sem confundir com o
# resultado das operações continuadas, o resultado antes dos tributos ou o lucro por ação (3.99).
CONTAS = {
    "BPP": [("pl", re.compile(r"^2\.\d\d$"), ("patrimonio liquido",)), ("div_c", "2.01.04", ("emprestimos",)), ("div_nc", "2.02.01", ("emprestimos",))],
    "BPA": [("ativo", "1", ("ativo total",)), ("caixa", "1.01.01", ("caixa", "disponib")), ("aplic", "1.01.02", ("aplicac",))],
    "DRE": [("receita", "3.01", None), ("ebit", "3.05", ("resultado antes do resultado financeiro",)),
            ("lucro", re.compile(r"^3\.\d\d$"), ("lucro", "prejuizo", "resultado liquido"), ("continuad", "antes", "por acao"), ("periodo", "exercicio")),
            ("lucro_c", re.compile(r"^3\.\d\d\.\d\d$"), ("atribuido",), ("nao controlador",), ("controlador",))],
    "DVA": [("da", "7.04.01", ("deprecia",))],
}
FIN_RECEITA = ("intermedia", "segur", "premio")   # DRE 3.01 de bancos e seguradoras


def _campo(tipo: str, cod: str, ds_norm: str) -> str | None:
    for campo, c, prefixos, *resto in CONTAS[tipo]:
        if not (c.match(cod) if hasattr(c, "match") else cod == c):
            continue
        excl = resto[0] if resto else ()
        exige = resto[1] if len(resto) > 1 else ()
        if any(x in ds_norm for x in excl) or (exige and not any(x in ds_norm for x in exige)):
            continue
        if prefixos is None or any(ds_norm.startswith(p) for p in prefixos):
            return campo
    return None
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
            ds = _norm(c[i_ds])
            campo = _campo(tipo, cod, ds)
            if tipo == "DRE" and cod == "3.01" and any(p in ds for p in FIN_RECEITA):
                fin[cvm] = True
            if campo == "pl" and cod != "2.03":
                fin[cvm] = True   # plano de contas de instituição financeira ou seguradora
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


def _ler_indice(z: zipfile.ZipFile, nome: str, receb: dict) -> None:
    """Índice do ZIP (itr_cia_aberta_AAAA.csv / dfp_...): por companhia e data de referência, a data em que a CVM recebeu a
    primeira versão do documento e a da versão mais recente. receb["cvm:AAAA-MM-DD"] = [primeira, última, versão, ITR|DFP]."""
    with z.open(nome) as fh:
        rd = csv.reader(io.TextIOWrapper(fh, encoding="latin-1", newline=""), delimiter=";")
        hdr = [h.strip() for h in next(rd)]
        try:
            i_cvm, i_ref, i_ver, i_rec = (hdr.index(c) for c in ("CD_CVM", "DT_REFER", "VERSAO", "DT_RECEB"))
        except ValueError:
            return
        i_cat = hdr.index("CATEG_DOC") if "CATEG_DOC" in hdr else None
        for c in rd:
            try:
                cvm, ver = int(c[i_cvm]), int(c[i_ver])
            except (ValueError, IndexError):
                continue
            k = f"{cvm}:{c[i_ref].strip()[:10]}"
            dt = c[i_rec].strip()[:10]
            doc = (c[i_cat].strip() if i_cat is not None else "") or ("DFP" if "dfp_" in nome.lower() else "ITR")
            r = receb.get(k)
            if r is None:
                receb[k] = [dt, dt, ver, doc]
                continue
            if dt and (not r[0] or dt < r[0]):
                r[0] = dt
            if ver > r[2]:
                r[1], r[2] = dt, ver


def _ler_zip(raw: bytes, cvms: set[int] | None, dados: dict, fin: dict, receb: dict | None = None) -> int:
    """Lê as demonstrações de interesse (BPA, BPP, DRE, DVA; con e ind) de um ZIP anual da CVM e, se pedido, o índice com
    as datas de recebimento."""
    n = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for nome in z.namelist():
            m = re.search(r"_(BPA|BPP|DRE|DVA)_(con|ind)_\d{4}\.csv$", nome)
            if m:
                n += _ler_demonstracao(z, nome, m.group(1), cvms, dados, fin)
            elif receb is not None and re.search(r"(?:^|/)(?:itr|dfp)_cia_aberta_\d{4}\.csv$", nome, re.I):
                _ler_indice(z, nome, receb)
    return n


def _extrato_ano(tipo: str, url: str, ano: int, hoje: date, pasta: str) -> tuple[dict, dict, dict]:
    """Extrato de um ZIP anual (todas as companhias) com cache em JSON: o ano corrente (e o anterior até abril) é renovado
    quando o extrato é de um dia anterior (DIAS_CACHE_CORRENTE), os fechados a cada DIAS_CACHE_FECHADO dias. Guardar só o
    extrato (poucos MB) evita manter os ZIPs (~30 MB cada) no cache. Devolve (dados, fin, receb)."""
    arq = os.path.join(pasta, f"{tipo}_{ano}.v{EXTRATO_VERSAO}.json")   # a versão no nome descarta extratos de leituras antigas
    if os.path.exists(arq) and os.path.getsize(arq) > 50:
        mtime = os.path.getmtime(arq)
        recente = ano >= hoje.year or (ano == hoje.year - 1 and hoje.month <= 4)
        valido = (hoje - date.fromtimestamp(mtime)).days < DIAS_CACHE_CORRENTE if recente else (time.time() - mtime) / 86400 < DIAS_CACHE_FECHADO
        if valido:
            j = json.load(open(arq, encoding="utf-8"))
            dados = {(int(k.split(":")[0]), k.split(":")[1]): {fim: {c: tuple(x) for c, x in cs.items()} for fim, cs in fins.items()}
                     for k, fins in j["dados"].items()}
            return dados, {int(c): True for c in j["fin"]}, j.get("receb") or {}
    raw = _baixar(url.format(ano=ano))
    dados: dict = {}
    fin: dict = {}
    receb: dict = {}
    n = _ler_zip(raw, None, dados, fin, receb)
    if n == 0:
        raise RuntimeError("ZIP sem as demonstrações esperadas")
    os.makedirs(pasta, exist_ok=True)
    tmp = arq + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"dados": {f"{k[0]}:{k[1]}": v for k, v in dados.items()}, "fin": sorted(fin), "receb": receb}, fh, separators=(",", ":"))
    os.replace(tmp, arq)
    return dados, fin, receb


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


def _datas_trimestres(fim: str, n: int) -> list[str]:
    """Os n fins de trimestre terminados em `fim`, do mais antigo ao mais recente, de 3 em 3 meses a partir do mês de `fim`
    (vale também para exercícios que não fecham em dezembro); fins de mês."""
    y, m = int(fim[:4]), int(fim[5:7])
    out = []
    for k in range(n - 1, -1, -1):
        t = y * 12 + (m - 1) - 3 * k
        yy, mm = t // 12, t % 12 + 1
        out.append(f"{yy:04d}-{mm:02d}-{calendar.monthrange(yy, mm)[1]:02d}")
    out[-1] = fim
    return out


def _meses(ini: str, fim: str) -> int:
    return (int(fim[:4]) * 12 + int(fim[5:7])) - (int(ini[:4]) * 12 + int(ini[5:7])) + 1


def _no_trimestre(d: dict, t: str, tp: str, campo: str):
    """Valor só do trimestre terminado em t: o acumulado do exercício em t menos o de tp (trimestre anterior, mesmo
    exercício, pelo DT_INI_EXERC); no primeiro trimestre do exercício o acumulado já é o trimestre. O 4º trimestre sai
    da DFP (ano) menos o ITR de 9 meses."""
    x = (d.get(t) or {}).get(campo)
    if not x:
        return None
    ini, _, v = x
    xp = (d.get(tp) or {}).get(campo)
    if xp and ini and xp[0] == ini:
        return v - xp[2]
    if ini and _meses(ini, t) <= 3:
        return v
    return None


def _serie(d: dict, fim: str, e_fin: bool, lc: str) -> dict:
    """Série dos TRIMESTRES_SERIE trimestres até `fim`: receita, EBITDA e lucro do trimestre; PL, dívida bruta e ativo
    total no fim do trimestre. Bancos e seguradoras sem receita, EBITDA e dívida (planos de contas diferentes)."""
    datas = _datas_trimestres(fim, TRIMESTRES_SERIE + 1)   # +1: o trimestre anterior ao primeiro, para a diferença
    s: dict = {"datas": datas[1:], "receita": [], "ebitda": [], "lucro": [], "pl": [], "divida": [], "ativo": []}
    for tp, t in zip(datas[:-1], datas[1:]):
        eb, da = _no_trimestre(d, t, tp, "ebit"), _no_trimestre(d, t, tp, "da")
        lq = _no_trimestre(d, t, tp, lc)
        if lq is None and lc != "lucro":
            lq = _no_trimestre(d, t, tp, "lucro")
        pl = _val(d, t, "pl")
        dc, dn = _val(d, t, "div_c"), _val(d, t, "div_nc")
        s["receita"].append(None if e_fin else _no_trimestre(d, t, tp, "receita"))
        s["ebitda"].append(None if (e_fin or eb is None or da is None) else eb + abs(da))
        s["lucro"].append(lq)
        s["pl"].append(pl)
        # como no comparador, sem a conta de empréstimos a dívida é zero (quando há balanço no trimestre)
        s["divida"].append(None if e_fin or pl is None else (dc or 0.0) + (dn or 0.0))
        s["ativo"].append(_val(d, t, "ativo"))
    return s


def calcular(dados_cvm: dict, fin: dict, hoje: date, receb: dict | None = None) -> dict[int, dict]:
    """Por código CVM: o último trimestre com DRE, PL/dívida/caixa desse trimestre, LTM de receita e EBITDA, e os
    crescimentos de 12/24/36 meses. Consolidado quando existe; individual como reserva. Para o post de resultados:
    a série de 16 trimestres, o lucro de 12 meses (P/L) e a data de entrega do documento à CVM."""
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
        # no DVA da CVM a depreciação vem como retenção, com sinal negativo (-84 bi na Petrobras em 2025): entra em módulo
        ebitda = None if (e_fin or ebit is None or da is None) else ebit + abs(da)
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
                g_ebitda.append(_cresc(ebitda, None if eb_a is None or da_a is None else eb_a + abs(da_a)))
        # lucro: a parte dos sócios da controladora quando a DRE separa (P/L sobre o valor de mercado da controladora)
        lc = "lucro_c" if (d.get(fim) or {}).get("lucro_c") else "lucro"
        lucro12 = _ltm(d, fim, lc)
        if lucro12 is None and lc != "lucro":
            lucro12 = _ltm(d, fim, "lucro")
        out[cvm] = {"dt": fim, "pl": pl, "divida": None if e_fin else divida, "caixa": None if e_fin else caixa,
                    "receita": None if e_fin else rec, "ebitda": ebitda, "g_pl": g_pl, "g_rec": g_rec, "g_ebitda": g_ebitda, "fin": e_fin,
                    "lucro12": lucro12, "lucro_base": "controladores" if lc == "lucro_c" else "consolidado",
                    "serie": _serie(d, fim, e_fin, lc), "entrega": (receb or {}).get(f"{cvm}:{fim}")}
    return out


def carregar(cvms: set[int], hoje: date, cache: str, avisos: list[str]) -> dict[int, dict]:
    """Baixa (ou lê do cache) ITR e DFP dos últimos anos e devolve calcular() para as companhias pedidas."""
    if not cvms:
        return {}
    pasta = os.path.join(cache, "cvm_dfs")
    os.makedirs(pasta, exist_ok=True)
    dados: dict = {}
    fin: dict = {}
    receb: dict = {}
    anos = list(range(hoje.year - ANOS_HISTORICO, hoje.year + 1))
    t0 = time.time()
    n_arq = 0
    for ano in anos:
        for tipo, url in (("itr", URL_ITR), ("dfp", URL_DFP)):
            try:
                d_ano, fin_ano, receb_ano = _extrato_ano(tipo, url, ano, hoje, pasta)
            except Exception as e:  # noqa: BLE001
                avisos.append(f"CVM {tipo.upper()} {ano}: {e}")
                continue
            _mesclar(dados, d_ano, cvms)
            fin.update({c: True for c in fin_ano if c in cvms})
            receb.update(receb_ano)
            n_arq += 1
    res = calcular(dados, fin, hoje, receb)
    n_ent = sum(1 for r in res.values() if r.get("entrega"))
    n_luc = sum(1 for r in res.values() if r.get("lucro12") is not None)
    log(f"  fundamentos CVM: {n_arq} arquivos (ITR/DFP {anos[0]}-{anos[-1]}), {len(res)} de {len(cvms)} companhias com dados, "
        f"{n_luc} com lucro de 12 meses, {n_ent} com data de entrega ({int(time.time() - t0)}s)")
    return res


def _serie_sintetica(k: int, pl: float, e_fin: bool, fim: str) -> dict:
    """Série fictícia de 16 trimestres que termina nos valores atuais do sintético; a companhia k % 7 == 3 sai de
    prejuízo para lucro (exercita o n.m. do post)."""
    n = TRIMESTRES_SERIE
    s: dict = {"datas": _datas_trimestres(fim, n), "receita": [], "ebitda": [], "lucro": [], "pl": [], "divida": [], "ativo": []}
    for j in range(n):
        f = (1 + 0.02 * (1 + k % 3)) ** (j - (n - 1))
        saz = 1 + 0.04 * ((j % 4) - 1.5) / 1.5
        s["receita"].append(None if e_fin else 1.8 * pl / 4 * f * saz)
        s["ebitda"].append(None if e_fin else 0.35 * pl / 4 * f * saz)
        s["lucro"].append(0.12 * pl / 4 * f * saz - (0.06 * pl if k % 7 == 3 and j < 7 else 0.0))
        s["pl"].append(pl * f ** 0.5)
        s["divida"].append(None if e_fin else 0.6 * pl * (1 - 0.01 * (n - 1 - j)))
        s["ativo"].append(3.2 * pl * f ** 0.4)
    return s


def sintetico(cvms: set[int], hoje: date) -> dict[int, dict]:
    """Base de teste (modo offline): números fictícios, mas plausíveis, por companhia."""
    out = {}
    for k, cvm in enumerate(sorted(cvms)):
        e_fin = k % 5 == 4
        pl = 2.0e9 * (1 + k)
        fim = date(hoje.year, 6, 30).isoformat()
        s = _serie_sintetica(k, pl, e_fin, fim)
        ent = date.fromordinal(hoje.toordinal() - 1 - 3 * (k % 4)).isoformat()
        out[cvm] = {"dt": fim, "pl": pl, "divida": 0.6 * pl, "caixa": 0.25 * pl,
                    "receita": None if e_fin else 1.8 * pl, "ebitda": None if e_fin else 0.35 * pl,
                    "g_pl": [round(0.08 + 0.01 * k, 4), round(0.17 + 0.02 * k, 4), round(0.26 + 0.03 * k, 4)],
                    "g_rec": [None] * 3 if e_fin else [round(0.05 + 0.02 * k, 4), round(0.12 + 0.03 * k, 4), round(0.20 + 0.04 * k, 4)],
                    "g_ebitda": [None] * 3 if e_fin else [round(-0.04 + 0.03 * k, 4), round(0.09 + 0.02 * k, 4), round(0.15 + 0.05 * k, 4)], "fin": e_fin,
                    "lucro12": sum(s["lucro"][-4:]), "lucro_base": "controladores", "serie": s, "entrega": [ent, ent, 1, "ITR"]}
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
    l12 = f.get("lucro12")
    p_l = round(mcap / l12, 2) if mcap and l12 and l12 > 0 else None
    return {"pvpa": pvpa, "ev_ebitda": ev_ebitda, "p_l": p_l, "g_pl": f.get("g_pl"), "g_rec": f.get("g_rec"), "g_ebitda": f.get("g_ebitda"),
            "fin": bool(f.get("fin")), "dt_fund": f.get("dt"), "pl": f.get("pl"), "ebitda": eb, "receita": f.get("receita"),
            "divida_liq": None if f.get("fin") else (f.get("divida") or 0.0) - (f.get("caixa") or 0.0)}


# ---------------------------------------------------------------- post diário de resultados (Instagram da Maison Invest)
def _rotulo_tri(dt: str) -> str:
    return f"{(int(dt[5:7]) - 1) // 3 + 1}T{dt[2:4]}"


def _dmy(dt: str | None) -> str:
    return "/".join(reversed(dt.split("-"))) if dt else ""


def _por_extenso(v: float) -> str:
    """R$ 4,2 bilhões / R$ 880 milhões / R$ 1,0 bilhão (o destaque da capa)."""
    a = abs(v)
    for lim, sing, plur in ((1e12, "trilhão", "trilhões"), (1e9, "bilhão", "bilhões"), (1e6, "milhão", "milhões"), (1e3, "mil", "mil")):
        if a >= lim:
            x = a / lim
            txt = f"{x:,.{1 if x < 100 else 0}f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"R$ {txt} {sing if x < 2 else plur}"
    return f"R$ {a:,.0f}".replace(",", ".")


def doc_resultado(ticker: str, nome: str, setor: str | None, cvm: int | None, f: dict | None, ind: dict, mcap: float | None, data_cotacao: str) -> dict | None:
    """JSON de uma companhia no formato do template do carrossel (valores em bilhões de reais; série de 16 trimestres)."""
    s = (f or {}).get("serie")
    if not s or s["pl"][-1] is None:
        return None
    bi = lambda xs: [None if x is None else round(x / 1e9, 6) for x in xs]  # noqa: E731
    periodo = _rotulo_tri(f["dt"])
    ent = f.get("entrega") or [None, None, None, None]
    doc = (ent[3] or ("DFP" if f["dt"][5:] == "12-31" else "ITR")).upper()
    nome_doc = f"DFP de {f['dt'][:4]}" if doc == "DFP" else f"ITR do {periodo}"
    fonte_dem = f"{nome_doc} entregue à CVM em {_dmy(ent[0])}" if ent[0] else f"{nome_doc} (CVM)"
    if ent[2] and ent[2] > 1 and ent[1] and ent[1] != ent[0]:
        fonte_dem += f", reapresentado em {_dmy(ent[1])}"
    if f.get("fin"):
        lq = s["lucro"][-1]
        destaque = None if lq is None else f"{'Lucro líquido' if lq >= 0 else 'Prejuízo'} de {_por_extenso(lq)} no {periodo}"
    else:
        rq = s["receita"][-1]
        destaque = None if rq is None else f"Receita líquida de {_por_extenso(rq)} no {periodo}"
    return {
        "ilustrativo": False, "empresa": re.sub(r"\s+(ON|PN[A-D]?|UNT)$", "", nome or ticker), "ticker": ticker, "cvm": cvm,
        "setor": setor, "financeira": bool(f.get("fin")), "logo": None, "periodo": periodo, "divulgacao": ent[0],
        "capa": {"tipo": "resultado", "destaque": destaque}, "noticia": None,
        "trimestres": [_rotulo_tri(x) for x in s["datas"]],
        "serie": {"receita": bi(s["receita"]), "ebitda": bi(s["ebitda"]), "lucro": bi(s["lucro"]), "pl": bi(s["pl"]),
                  "divida": bi(s["divida"]), "ativos": bi(s["ativo"])},
        "lucro_base": f.get("lucro_base"),
        "multiplos": {"pvp": ind.get("pvpa"), "pl": ind.get("p_l"), "ev_ebitda": ind.get("ev_ebitda"), "data_cotacao": data_cotacao,
                      "fonte": "Comparador de Ativos Maison Hub", "valor_mercado": round(mcap) if mcap else None},
        "fontes": {"demonstracoes": fonte_dem,
                   "multiplos": f"Cálculo Maison Hub com a cotação de fechamento na B3 em {_dmy(data_cotacao)} e as demonstrações entregues à CVM"},
        "entrega": {"primeira": ent[0], "ultima": ent[1], "versao": ent[2], "doc": doc},
    }
