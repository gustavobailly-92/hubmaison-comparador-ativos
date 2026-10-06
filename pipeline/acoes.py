"""Ações, BDRs e fundos imobiliários negociados na B3, só com fontes oficiais e abertas.

Universo e preços: os arquivos anuais de cotações históricas da B3 (COTAHIST), mercado à vista: ações em lote padrão
(CODBDI 02: ON, PN, UNT), BDRs (CODBDI 34/35/36: DRN, DR1, DR2, DR3, DRE) e cotas de fundos imobiliários (CODBDI 12). Entram os papéis com negócios em
pelo menos LIQ_MIN dos pregões dos últimos 12 meses; os ilíquidos ficam com preço parado por semanas e distorcem a comparação.

Duas séries por papel, alinhadas ao calendário:
  qp  cotação só de preço: fechamentos do COTAHIST ajustados por desdobramentos, grupamentos e bonificações;
  q   cotação com proventos reinvestidos (total return), comparável à cota de um fundo: a série qp descontada, antes de cada
      data "com", do provento pago (dividendos e JCP brutos das empresas, pela API de empresas listadas da B3; rendimentos
      mensais dos FIIs pelo informe mensal da CVM, campo Percentual_Dividend_Yield_Mes).
Os eventos societários das empresas e dos FIIs vêm da API de empresas/fundos listados da B3 (a mesma que o site da B3 usa).
BDRs: sem fonte aberta de proventos; os desdobramentos são detectados pelo salto de preço (razão inteira) e a série q é igual
à qp. O Yahoo Finance foi abandonado: devolve 429 para os IPs do GitHub Actions.
"""
from __future__ import annotations

import base64
import bisect
import io
import json
import os
import re
import time
import zipfile
from datetime import date

import numpy as np

import fontes_extras as fx

COTAHIST_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP"
B3_EMPRESAS = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/"
B3_FUNDOS = "https://sistemaswebb3-listados.b3.com.br/fundsProxy/fundsCall/"
CVM_FII = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{ano}.zip"
LIQ_MIN = 0.60          # fração mínima dos pregões com negócio (últimos 12 meses)
SESSOES_MIN = 20        # pregões mínimos com negócio
PREGOES_12M = 252
PAUSA_B3 = 0.2          # segundos entre chamadas à API da B3
ESPECIES_ACAO = ("ON", "PN", "PNA", "PNB", "PNC", "PND", "PNE", "PNF", "UNT")
ESPECIES_BDR = ("DRN", "DR1", "DR2", "DR3", "DRE")
CODBDI_BDR = ("34", "35", "36")   # no COTAHIST os BDRs não vêm em lote padrão (02): 34 não patrocinado, 35 patrocinado, 36 ETF
CASH_PAGINA = 100       # proventos em dinheiro por página na API da B3 (acima de ~120 a API devolve vazio)
EVENTOS_VERSAO = 2      # formato do cache de eventos; muda quando a leitura da API muda (invalida caches antigos)
RAZOES_SPLIT = (2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 100)

log = fx.log


def _b3_headers() -> dict:
    return {"Accept": "application/json, text/plain, */*", "Referer": "https://www.b3.com.br/", "Origin": "https://www.b3.com.br"}


def _b3_json(url_base: str, metodo: str, payload: dict, tentativas: int = 3):
    token = base64.b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()).decode()
    raw = fx.http_get(f"{url_base}{metodo}/{token}", tentativas=tentativas, timeout=60, headers=_b3_headers())
    txt = raw.decode("utf-8", errors="replace").strip()
    if not txt:
        return None
    return json.loads(txt)


def _num_br(s) -> float | None:
    try:
        return float(str(s).replace(".", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _data_br(s) -> str | None:
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(s or ""))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


# --------------------------------------------------------------------------- COTAHIST

def _ler_cotahist(raw: bytes, por_ticker: dict, pregoes: set, apenas: set | None = None) -> None:
    """Lê um ZIP anual da B3 (registros de 245 posições) e acumula, por papel, os pregões com negócio.
    apenas: conjunto de tickers a guardar (None = todos os elegíveis)."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        nome = next((n for n in z.namelist() if n.upper().endswith(".TXT")), None)
        if not nome:
            raise RuntimeError("ZIP sem o TXT de cotações")
        with z.open(nome) as fh:
            for linha in io.TextIOWrapper(fh, encoding="latin-1", newline=None):
                if not linha.startswith("01") or linha[24:27] != "010":
                    continue
                ticker = linha[12:24].strip()
                if apenas is not None and ticker not in apenas:
                    continue
                codbdi = linha[10:12]
                especi = linha[39:49].split()
                esp = especi[0] if especi else ""
                if codbdi == "02" and esp in ESPECIES_ACAO:
                    tipo = "acao"
                elif codbdi in CODBDI_BDR and esp in ESPECIES_BDR:
                    tipo = "bdr"   # 34 = BDR não patrocinado, 35 = patrocinado (DR1/DR2/DR3), 36 = BDR de ETF
                elif codbdi == "12" and esp.startswith("CI"):
                    tipo = "fii"   # cotas de fundos imobiliários (e fiagros) em lote padrão
                else:
                    continue
                if not re.fullmatch(r"[A-Z0-9]{4}\d{1,2}", ticker):
                    continue
                d = linha[2:10]
                dia = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
                try:
                    fat = int(linha[210:217]) or 1
                    ult = int(linha[108:121]) / 100.0 / fat
                    vol = int(linha[170:188]) / 100.0
                    neg = int(linha[147:152])
                except ValueError:
                    continue
                if ult <= 0 or neg <= 0:
                    continue
                pregoes.add(dia)
                p = por_ticker.get(ticker)
                if p is None:
                    p = por_ticker[ticker] = {"ticker": ticker, "nome": linha[27:39].strip(), "especi": esp, "tipo": tipo,
                                              "isin": linha[230:242].strip(), "dias": {}}
                p["dias"][dia] = (ult, vol)
                isin = linha[230:242].strip()
                if isin:
                    p["isin"] = isin


def _baixar_cotahist(ano: int, cache: str, atual: bool) -> bytes:
    """O arquivo do ano corrente é baixado a cada execução (muda todo dia); os anos fechados ficam em cache."""
    os.makedirs(cache, exist_ok=True)
    arq = os.path.join(cache, f"COTAHIST_A{ano}.ZIP")
    if not atual and os.path.exists(arq) and os.path.getsize(arq) > 1_000_000:
        with open(arq, "rb") as fh:
            return fh.read()
    raw = fx.http_get(COTAHIST_URL.format(ano=ano), tentativas=3, timeout=600,
                      headers={"Accept": "application/zip,application/octet-stream,*/*", "Referer": "https://www.b3.com.br/"})
    if len(raw) < 100_000 or raw[:2] != b"PK":
        raise RuntimeError(f"COTAHIST {ano}: resposta inesperada ({len(raw)} bytes)")
    if not atual:
        with open(arq, "wb") as fh:
            fh.write(raw)
    return raw


def universo(hoje: date, cache: str, avisos: list[str]) -> tuple[list[dict], dict, dict]:
    """Papéis em negociação com liquidez mínima. Devolve (lista, info, por_ticker do ano corrente)."""
    por_ticker: dict[str, dict] = {}
    pregoes: set[str] = set()
    _ler_cotahist(_baixar_cotahist(hoje.year, cache, atual=True), por_ticker, pregoes)
    if len(pregoes) < PREGOES_12M // 2:
        try:
            _ler_cotahist(_baixar_cotahist(hoje.year - 1, cache, atual=False), por_ticker, pregoes)
        except Exception as e:  # noqa: BLE001
            avisos.append(f"COTAHIST {hoje.year - 1}: {e}")
    ordem = sorted(pregoes)
    janela = ordem[-PREGOES_12M:]
    out = []
    for p in por_ticker.values():
        dias = p["dias"]
        if not dias:
            continue
        primeiro = min(dias)
        possiveis = [d for d in janela if d >= primeiro]
        com_negocio = [d for d in possiveis if d in dias]
        if len(possiveis) == 0 or len(com_negocio) < SESSOES_MIN or len(com_negocio) / len(possiveis) < LIQ_MIN:
            continue
        ultimo = max(dias)
        vols = sorted(dias[d][1] for d in com_negocio)
        out.append({
            "ticker": p["ticker"], "nome": p["nome"], "especi": p["especi"], "tipo": p["tipo"], "isin": p["isin"],
            "ultimo": ultimo, "preco": dias[ultimo][0],
            "liq": float(np.median(vols)) if vols else 0.0,
            "sessoes": len(com_negocio), "possiveis": len(possiveis), "estreia": primeiro,
        })
    out.sort(key=lambda x: -x["liq"])
    info = {"pregoes": len(ordem), "ultimo_pregao": ordem[-1] if ordem else None, "papeis_no_arquivo": len(por_ticker)}
    return out, info, por_ticker


def historico(papeis: list[dict], anos: list[int], hoje: date, cache: str, atual: dict, avisos: list[str]) -> dict[str, dict[str, float]]:
    """Fechamentos diários (sem ajuste) de cada papel do universo em todos os anos pedidos."""
    apenas = {p["ticker"] for p in papeis}
    series: dict[str, dict[str, float]] = {tk: {} for tk in apenas}
    for tk in apenas:
        if tk in atual:
            series[tk].update({d: v[0] for d, v in atual[tk]["dias"].items()})
    for ano in anos:
        if ano >= hoje.year:
            continue
        por_ticker: dict[str, dict] = {}
        try:
            _ler_cotahist(_baixar_cotahist(ano, cache, atual=False), por_ticker, set(), apenas)
        except Exception as e:  # noqa: BLE001
            avisos.append(f"COTAHIST {ano}: {e}")
            continue
        for tk, p in por_ticker.items():
            series[tk].update({d: v[0] for d, v in p["dias"].items()})
        log(f"  COTAHIST {ano}: {len(por_ticker)} papéis do universo")
    return series


# --------------------------------------------------------------------------- eventos societários (B3) e rendimentos de FII (CVM)

def _ler_json(arq: str):
    try:
        with open(arq, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _eventos_stock(lista) -> list[dict]:
    out = []
    for ev in lista or []:
        f = _num_br(ev.get("factor"))
        d = _data_br(ev.get("lastDatePrior"))
        lbl = (ev.get("label") or "").upper()
        if f is None or not d:
            continue
        # multiplicador do número de ações: desdobramento/bonificação vêm em %, 100 dobra; o grupamento vem como razão, 0,01 reduz a 1/100
        m = f if "GRUPAMENTO" in lbl else 1 + f / 100.0
        if m <= 0 or abs(m - 1) < 1e-9:
            continue
        out.append({"isin": ev.get("isinCode") or ev.get("assetIssued"), "data_com": d, "m": m, "tipo": lbl})
    return out


def eventos_empresa(emissor: str, cache_dir: str, hoje: date) -> dict | None:
    """Para um código de emissor (PETR, VALE...): nome de pregão, desdobramentos/grupamentos/bonificações por ISIN e
    dividendos/JCP por tipo de ação (histórico completo), pela API de empresas listadas da B3. Cache de 7 dias."""
    arq = os.path.join(cache_dir, f"eventos_{emissor}.json")
    g = _ler_json(arq)
    if g and g.get("versao") == EVENTOS_VERSAO and (date.today() - date.fromisoformat(g.get("atualizado", "2000-01-01"))).days < 7:
        return g
    try:
        sup = _b3_json(B3_EMPRESAS, "GetListedSupplementCompany", {"issuingCompany": emissor, "language": "pt-br"})
    except Exception as e:  # noqa: BLE001
        return g if g else {"erro": str(e)[:200]}
    sup = sup[0] if isinstance(sup, list) and sup else (sup if isinstance(sup, dict) else None)
    if not sup:
        out = {"versao": EVENTOS_VERSAO, "atualizado": hoje.isoformat(), "nome": None, "stock": [], "cash": []}
        with open(arq, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False)
        return out
    nome = (sup.get("tradingName") or "").strip()
    stock = _eventos_stock(sup.get("stockDividends"))
    cash: list | None = []
    if nome:
        # a API aceita no máximo ~120 registros por página (com 500 devolve vazio) e não encontra nomes com barra
        # ("AMBEV S/A" só responde como "AMBEV SA"); espaços não atrapalham
        nomes = [nome]
        limpo = re.sub(r"[^A-Z0-9 ]", "", nome.upper()).strip()
        if limpo and limpo != nome:
            nomes.append(limpo)
        for tentativa, nm in enumerate(nomes):
            cash = []
            pagina = 1
            erro = False
            while pagina <= 40:
                try:
                    time.sleep(PAUSA_B3)
                    r = _b3_json(B3_EMPRESAS, "GetListedCashDividends", {"language": "pt-br", "pageNumber": pagina, "pageSize": CASH_PAGINA, "tradingName": nm})
                except Exception:  # noqa: BLE001
                    erro = True
                    break
                for ev in (r or {}).get("results") or []:
                    v = _num_br(ev.get("valueCash"))
                    por = _num_br(ev.get("quotedPerShares")) or 1
                    d = _data_br(ev.get("lastDatePriorEx"))
                    if v is None or not d or v <= 0:
                        continue
                    cash.append({"tipo_acao": (ev.get("typeStock") or "").strip().upper(), "data_com": d, "valor": v / (por or 1),
                                 "fecho_com": _num_br(ev.get("closingPricePriorExDate")), "evento": ev.get("corporateAction")})
                tp = ((r or {}).get("page") or {}).get("totalPages") or 1
                if pagina >= tp:
                    break
                pagina += 1
            if erro:
                if g:
                    return g
                cash = None
                break
            if cash:
                break
    out = {"versao": EVENTOS_VERSAO, "atualizado": hoje.isoformat(), "nome": nome, "stock": stock, "cash": cash}
    with open(arq, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    return out


def eventos_fii(codigo: str, cache_dir: str, hoje: date) -> dict | None:
    """Desdobramentos e grupamentos de um FII (código de 4 letras) pela API de fundos listados da B3. Cache de 7 dias."""
    arq = os.path.join(cache_dir, f"eventos_fii_{codigo}.json")
    g = _ler_json(arq)
    if g and (date.today() - date.fromisoformat(g.get("atualizado", "2000-01-01"))).days < 7:
        return g
    try:
        sup = _b3_json(B3_FUNDOS, "GetListedSupplementFunds", {"cnpj": "", "identifierFund": codigo, "typeFund": 7})
    except Exception as e:  # noqa: BLE001
        return g if g else {"erro": str(e)[:200]}
    out = {"atualizado": hoje.isoformat(), "stock": _eventos_stock((sup or {}).get("stockDividends") if isinstance(sup, dict) else None)}
    with open(arq, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    return out


def rendimentos_fii(anos: list[int], hoje: date, cache: str, avisos: list[str]) -> tuple[dict[str, str], dict[str, dict[str, float]]]:
    """Informe mensal de FII da CVM: (ISIN -> CNPJ) e (CNPJ -> {AAAA-MM: dividend yield do mês, fração})."""
    isin_cnpj: dict[str, str] = {}
    dy: dict[str, dict[str, float]] = {}
    os.makedirs(cache, exist_ok=True)
    for ano in anos:
        arq = os.path.join(cache, f"inf_mensal_fii_{ano}.zip")
        try:
            if ano < hoje.year and os.path.exists(arq) and os.path.getsize(arq) > 10_000:
                raw = open(arq, "rb").read()
            else:
                raw = fx.http_get(CVM_FII.format(ano=ano), tentativas=3, timeout=180)
                if raw[:2] != b"PK":
                    raise RuntimeError("não é ZIP")
                open(arq, "wb").write(raw)
        except Exception as e:  # noqa: BLE001
            avisos.append(f"informe mensal de FII {ano}: {e}")
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for n in z.namelist():
                low = n.lower()
                if "geral" not in low and "complemento" not in low:
                    continue
                with z.open(n) as fh:
                    txt = io.TextIOWrapper(fh, encoding="latin-1", newline=None)
                    hdr = next(txt).rstrip("\r\n").split(";")
                    hdr = [h.strip() for h in hdr]
                    ic = hdr.index("CNPJ_Fundo_Classe") if "CNPJ_Fundo_Classe" in hdr else (hdr.index("CNPJ_Fundo") if "CNPJ_Fundo" in hdr else None)
                    if ic is None:
                        continue
                    if "geral" in low:
                        if "Codigo_ISIN" not in hdr:
                            continue
                        ii = hdr.index("Codigo_ISIN")
                        for linha in txt:
                            c = linha.rstrip("\r\n").split(";")
                            if len(c) > max(ic, ii) and c[ii].strip():
                                isin_cnpj[c[ii].strip()] = re.sub(r"\D", "", c[ic])
                    else:
                        if "Percentual_Dividend_Yield_Mes" not in hdr or "Data_Referencia" not in hdr:
                            continue
                        idt, idy = hdr.index("Data_Referencia"), hdr.index("Percentual_Dividend_Yield_Mes")
                        for linha in txt:
                            c = linha.rstrip("\r\n").split(";")
                            if len(c) <= max(ic, idt, idy):
                                continue
                            try:
                                v = float(c[idy]) if c[idy].strip() else None
                            except ValueError:
                                v = None
                            if v is None or v < 0 or v > 0.2:
                                continue
                            # a versão mais recente do informe prevalece (as linhas vêm em ordem; a última ganha)
                            dy.setdefault(re.sub(r"\D", "", c[ic]), {})[c[idt][:7]] = v
    return isin_cnpj, dy


# --------------------------------------------------------------------------- ajustes

def _detectar_splits(serie: dict[str, float]) -> list[tuple[str, float]]:
    """Saltos de preço de razão inteira entre pregões consecutivos (desdobramento ou grupamento), para papéis sem evento
    oficial (BDRs). Devolve [(último dia com o preço antigo, multiplicador de quantidade)]."""
    dias = sorted(serie)
    out = []
    for a, b in zip(dias, dias[1:]):
        p0, p1 = serie[a], serie[b]
        if p0 <= 0 or p1 <= 0:
            continue
        r = p0 / p1
        for n in RAZOES_SPLIT:
            if abs(r / n - 1) < 0.04:
                out.append((a, float(n)))
                break
            if abs(r * n - 1) < 0.04:
                out.append((a, 1.0 / n))
                break
    return out


def ajustar(serie: dict[str, float], splits: list[tuple[str, float]], proventos: list[tuple[str, float, float | None]],
            dy_mensal: dict[str, float] | None) -> tuple[dict[str, float], dict[str, float], dict]:
    """serie: fechamentos sem ajuste. splits: [(data_com, m)]: os preços até a data com (inclusive) são divididos por m.
    proventos: [(data_com, valor por ação, fecho na data com ou None)]. dy_mensal: {AAAA-MM: fração} (FII).
    Devolve (qp, q, info)."""
    dias = sorted(serie)
    if not dias:
        return {}, {}, {}
    arr = np.array([serie[d] for d in dias], dtype=float)
    idx = {d: i for i, d in enumerate(dias)}

    def ate(data_com: str) -> int:
        return bisect.bisect_right(dias, data_com) - 1

    fator_split = np.ones(len(dias))
    n_splits = 0
    for data_com, m in splits:
        i = ate(data_com)
        if i < 0 or i >= len(dias) - 1:
            continue
        fator_split[: i + 1] /= m
        n_splits += 1
    qp = arr * fator_split
    fator_div = np.ones(len(dias))
    n_prov = 0
    for data_com, valor, fecho in proventos:
        i = ate(data_com)
        if i < 0 or valor <= 0:
            continue
        # o provento é por ação na data com; a série qp está na base de ações de hoje, então o valor leva o mesmo ajuste
        v = valor * fator_split[i]
        base = qp[i]
        if fecho and fecho > 0 and abs(arr[i] / fecho - 1) < 0.5:
            base = fecho * fator_split[i]
        if base <= 0 or v >= base:
            continue
        fator_div[: i + 1] *= 1 - v / base
        n_prov += 1
    if dy_mensal:
        # FII: rendimento mensal como fração do preço, aplicado no último pregão de cada mês informado
        ult_do_mes: dict[str, int] = {}
        for i, d in enumerate(dias):
            ult_do_mes[d[:7]] = i
        for ym, v in dy_mensal.items():
            i = ult_do_mes.get(ym)
            if i is None or v <= 0 or v >= 0.5 or i >= len(dias) - 1:
                continue
            fator_div[: i + 1] *= 1 - v
            n_prov += 1
    q = qp * fator_div
    info = {"splits": n_splits, "proventos": n_prov}
    return {d: float(qp[i]) for d, i in idx.items()}, {d: float(q[i]) for d, i in idx.items()}, info


# --------------------------------------------------------------------------- montagem

def _nome_bonito(nomres: str, especi: str, longo: str | None) -> str:
    base = (longo or "").strip()
    if base:
        base = re.sub(r"\s+(S\.?A\.?|SA|LTDA\.?|INC\.?|CORP\.?|PLC|N\.?V\.?)$", "", base, flags=re.I).strip(" -.")
    if not base:
        base = nomres.title().replace("Sa ", "SA ").strip()
    suf = {"ON": "ON", "PN": "PN", "PNA": "PNA", "PNB": "PNB", "PNC": "PNC", "PND": "PND", "UNT": "UNT"}.get(especi, "")
    if especi.startswith("CI") and not re.search(r"\bFII\b|imobili", base, re.I):
        suf = "FII"
    return (base + (" " + suf if suf else "")).strip()


def carregar_acoes(datas: list[date], hoje: date, offline: str | None, cache: str, avisos: list[str]) -> tuple[list[dict], dict]:
    """Devolve (papéis, info). Cada papel: ticker, nome, tipo (acao|bdr|fii), especi, bm, liq, preco, fonte, ajuste,
    q e qp (np.array no calendário: com e sem proventos reinvestidos)."""
    if offline:
        return _sinteticas(datas), {"pregoes": len(datas), "ultimo_pregao": datas[-1].isoformat(), "papeis_no_arquivo": 13, "fonte": "sintético"}
    pasta = os.path.join(cache, "acoes")
    os.makedirs(pasta, exist_ok=True)
    papeis, info, atual = universo(hoje, cache, avisos)
    log(f"  COTAHIST: {info['papeis_no_arquivo']} papéis no arquivo, {len(papeis)} com liquidez (último pregão {info['ultimo_pregao']})")
    anos = list(range(datas[0].year, hoje.year + 1))
    series = historico(papeis, anos, hoje, cache, atual, avisos)
    # rendimentos dos FIIs (CVM) e eventos societários (B3)
    isin_cnpj: dict[str, str] = {}
    dy_fii: dict[str, dict[str, float]] = {}
    if any(p["tipo"] == "fii" for p in papeis):
        try:
            isin_cnpj, dy_fii = rendimentos_fii(anos, hoje, os.path.join(cache, "fii"), avisos)
            log(f"  FII: {len(isin_cnpj)} ISINs e {len(dy_fii)} fundos com dividend yield mensal na CVM")
        except Exception as e:  # noqa: BLE001
            avisos.append(f"rendimentos dos FIIs (CVM): {e}")
    t0 = time.time()
    emissores: dict[str, dict | None] = {}
    fiis: dict[str, dict | None] = {}
    out = []
    n_ok = n_sem_evento = 0
    for k, p in enumerate(papeis):
        serie = series.get(p["ticker"]) or {}
        if len(serie) < SESSOES_MIN:
            continue
        splits: list[tuple[str, float]] = []
        proventos: list[tuple[str, float, float | None]] = []
        dy = None
        ajuste = "completo"
        cod = p["ticker"][:4]
        if p["tipo"] == "acao":
            if cod not in emissores:
                time.sleep(PAUSA_B3)
                emissores[cod] = eventos_empresa(cod, pasta, hoje)
            ev = emissores[cod] or {}
            if ev.get("erro") or ev.get("cash") is None:
                ajuste = "sem proventos"
                n_sem_evento += 1
            for s in ev.get("stock") or []:
                if not p["isin"] or s.get("isin") == p["isin"]:
                    splits.append((s["data_com"], s["m"]))
            cash = ev.get("cash") or []
            if p["especi"] == "UNT":
                # units (1 ON + n PN) não aparecem na API; aplico o rendimento percentual da ON (ou da PN) sobre o preço da unit
                base_tipo = "ON" if any(((c.get("tipo_acao") or "").split() or [""])[0] == "ON" for c in cash) else "PN"
                dias_serie = sorted(serie)
                for c in cash:
                    ta = ((c.get("tipo_acao") or "").split() or [""])[0]
                    fecho = c.get("fecho_com")
                    if ta != base_tipo or not fecho or fecho <= 0:
                        continue
                    i = bisect.bisect_right(dias_serie, c["data_com"]) - 1
                    if i < 0:
                        continue
                    preco_unit = serie[dias_serie[i]]
                    proventos.append((c["data_com"], c["valor"] / fecho * preco_unit, preco_unit))
            else:
                for c in cash:
                    ta = ((c.get("tipo_acao") or "").split() or [""])[0]
                    if ta == p["especi"] or not ta:
                        proventos.append((c["data_com"], c["valor"], c.get("fecho_com")))
            if not ev.get("stock") and not cash:
                splits = _detectar_splits(serie)
        elif p["tipo"] == "fii":
            if cod not in fiis:
                time.sleep(PAUSA_B3)
                fiis[cod] = eventos_fii(cod, pasta, hoje)
            ev = fiis[cod] or {}
            for s in ev.get("stock") or []:
                if not p["isin"] or s.get("isin") == p["isin"]:
                    splits.append((s["data_com"], s["m"]))
            if not splits:
                splits = _detectar_splits(serie)
            cnpj = isin_cnpj.get(p["isin"])
            dy = dy_fii.get(cnpj) if cnpj else None
            if not dy:
                ajuste = "sem proventos"
                n_sem_evento += 1
        else:  # BDR: sem fonte aberta de proventos
            splits = _detectar_splits(serie)
            ajuste = "sem proventos"
        qp_d, q_d, inf = ajustar(serie, splits, proventos, dy)
        q = fx.alinhar(q_d, datas)
        if np.isnan(q).all():
            continue
        out.append({**{k2: v for k2, v in p.items() if k2 != "isin"}, "nome_longo": None, "fonte": "B3 COTAHIST",
                    "nome": _nome_bonito(p["nome"], p["especi"], None), "ajuste": ajuste, "estreia": min(serie),
                    "n_splits": inf.get("splits", 0), "n_proventos": inf.get("proventos", 0),
                    "bm": "sp500brl" if p["tipo"] == "bdr" else "ifix" if p["tipo"] == "fii" else "ibov",
                    "q": q, "qp": fx.alinhar(qp_d, datas)})
        n_ok += 1
        if (k + 1) % 100 == 0:
            log(f"  {k + 1} de {len(papeis)} papéis ({int(time.time() - t0)}s)")
    log(f"  séries montadas: {n_ok} papéis, {len(emissores)} emissores e {len(fiis)} FIIs consultados na B3 ({int(time.time() - t0)}s); {n_sem_evento} sem proventos")
    if n_sem_evento:
        avisos.append(f"ações: {n_sem_evento} papéis sem proventos na série (BDRs, ou sem resposta da B3/CVM)")
    info["fonte"] = "B3 COTAHIST + eventos B3 + CVM (FII)"
    return out, info


def _sinteticas(datas: list[date]) -> list[dict]:
    """Base de teste: papéis fictícios com passeio aleatório, para exercitar o site sem rede."""
    base = [("PETR4", "Petrobras PN", "PN", "acao", 0.18, 0.30, 38.0), ("VALE3", "Vale ON", "ON", "acao", 0.05, 0.28, 60.0),
            ("ITUB4", "Itaú Unibanco PN", "PN", "acao", 0.22, 0.22, 34.0), ("WEGE3", "WEG ON", "ON", "acao", 0.15, 0.26, 45.0),
            ("BBDC4", "Bradesco PN", "PN", "acao", -0.02, 0.27, 14.0), ("TAEE11", "Taesa UNT", "UNT", "acao", 0.12, 0.17, 36.0),
            ("MGLU3", "Magazine Luiza ON", "ON", "acao", -0.30, 0.65, 8.0), ("PRIO3", "Prio ON", "ON", "acao", 0.25, 0.35, 42.0),
            ("AAPL34", "Apple", "DRN", "bdr", 0.20, 0.25, 85.0), ("MSFT34", "Microsoft", "DRN", "bdr", 0.24, 0.24, 110.0),
            ("NVDC34", "NVIDIA", "DRN", "bdr", 0.60, 0.50, 30.0), ("HGLG11", "CSHG Logística FII", "CI", "fii", 0.11, 0.12, 160.0),
            ("KNCR11", "Kinea Rendimentos FII", "CI", "fii", 0.13, 0.05, 102.0)]
    out = []
    for i, (tk, nome, esp, tipo, drift, vol, p0) in enumerate(base):
        ds = datas if i != 7 else datas[len(datas) // 2:]  # um papel com estreia recente
        serie = fx.sintetico(ds, 100 + i, drift, vol, p0)
        # série só de preço: a ajustada descontada de um provento de ~0,5% ao mês (FII ~0,9%)
        dy = 0.009 if tipo == "fii" else 0.005
        precos = {}
        fator = 1.0
        dias = sorted(serie)
        for k, d in enumerate(dias):
            if k and d[:7] != dias[k - 1][:7]:
                fator /= 1 + dy
            precos[d] = serie[d] * fator
        out.append({"ticker": tk, "nome": nome, "nome_longo": nome, "especi": esp, "tipo": tipo, "bm": "sp500brl" if tipo == "bdr" else "ifix" if tipo == "fii" else "ibov",
                    "liq": float(5e8 / (i + 1)), "preco": serie[max(serie)], "ultimo": max(serie), "sessoes": len(ds), "possiveis": len(ds),
                    "estreia": min(serie), "fonte": "sintético", "ajuste": "completo" if tipo != "bdr" else "sem proventos", "n_splits": 0, "n_proventos": 0,
                    "q": fx.alinhar(serie, datas), "qp": fx.alinhar(precos, datas)})
    return out


def premio_sobre(janelas_ativo: dict, janelas_bench: dict) -> tuple[float | None, int | None]:
    """Excesso anualizado do papel sobre o benchmark (p.p. ao ano), na maior janela fechada disponível (36, 24, 12 meses)."""
    for w in (36, 24, 12):
        ja = (janelas_ativo or {}).get(str(w))
        jb = (janelas_bench or {}).get(str(w))
        if ja and jb and ja.get("ret") is not None and jb.get("ret") is not None:
            anos = w / 12.0
            aa = (1 + ja["ret"]) ** (1 / anos) - 1
            ab = (1 + jb["ret"]) ** (1 / anos) - 1
            return round((aa - ab) * 100, 2), w
    return None, None
