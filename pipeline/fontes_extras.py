#!/usr/bin/env python3
"""
Fontes extras do Comparador de Ativos: benchmarks (BCB + Yahoo/Stooq), Tesouro Direto (Tesouro Transparente)
e a lista de fundos da plataforma XP (planilha "Guia de Fundos", extraída para xp_fundos.csv).

Todas as funções são tolerantes: uma fonte que falhar vira aviso, nunca derruba a execução.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import random
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 MaisonHub/2.0"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def http_get(url: str, tentativas: int = 3, timeout: int = 120, headers: dict | None = None) -> bytes:
    ultimo = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            ultimo = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {ultimo}")


# --------------------------------------------------------------------------- utilidades de série

def alinhar(serie: dict[str, float], datas: list[date]) -> np.ndarray:
    """dict 'AAAA-MM-DD' -> valor  =>  array alinhado ao calendário, com o último valor conhecido (ffill)."""
    if not serie:
        return np.full(len(datas), np.nan)
    chaves = sorted(serie)
    vals = [serie[k] for k in chaves]
    out = np.full(len(datas), np.nan)
    j = -1
    n = len(chaves)
    for i, d in enumerate(datas):
        s = d.isoformat()
        while j + 1 < n and chaves[j + 1] <= s:
            j += 1
        if j >= 0:
            out[i] = vals[j]
    return out


def indice_mensal_para_diario(mensal: dict[str, float], datas: list[date], estender: bool = True):
    """Taxa mensal (fração) por 'AAAA-MM' -> índice diário acumulado ao longo dos dias úteis de cada mês.
    Se o mês corrente ainda não tem valor, repete o último conhecido (marcado em 'estimado')."""
    meses: dict[str, list[int]] = {}
    for i, d in enumerate(datas):
        meses.setdefault(d.strftime("%Y-%m"), []).append(i)
    idx = np.ones(len(datas))
    acum = 1.0
    ultimo = None
    estimados = []
    for ym in sorted(meses):
        r = mensal.get(ym)
        if r is None:
            if not estender or ultimo is None:
                r = 0.0
            else:
                r = ultimo
                estimados.append(ym)
        else:
            ultimo = r
        dias = meses[ym]
        f = (1 + r) ** (1 / len(dias))
        for i in dias:
            acum *= f
            idx[i] = acum
    return idx, estimados


def coup_dates_factor(datas: list[date], venc: date, cupom_aa: float) -> np.ndarray:
    """Fator de cupom por dia (1 + k no primeiro dia útil de cada data de cupom, 1 nos demais)."""
    k = (1 + cupom_aa) ** 0.5 - 1
    fator = np.ones(len(datas))
    if cupom_aa <= 0:
        return fator
    m1 = venc.month
    m2 = m1 + 6 if m1 <= 6 else m1 - 6
    dia = venc.day
    marcados = set()
    for i, d in enumerate(datas):
        for m in (m1, m2):
            try:
                alvo = date(d.year, m, dia)
            except ValueError:
                continue
            if d >= alvo and (d.year, m) not in marcados and alvo >= datas[0] and alvo <= venc:
                marcados.add((d.year, m))
                fator[i] = 1 + k
    return fator


# --------------------------------------------------------------------------- BCB SGS

def sgs(codigo: int, inicio: date, fim: date) -> dict[str, float]:
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"
           f"&dataInicial={inicio.strftime('%d/%m/%Y')}&dataFinal={fim.strftime('%d/%m/%Y')}")
    dados = json.loads(http_get(url).decode("utf-8"))
    out = {}
    for d in dados:
        try:
            dt = datetime.strptime(d["data"], "%d/%m/%Y").date().isoformat()
            out[dt] = float(str(d["valor"]).replace(",", "."))
        except Exception:  # noqa: BLE001
            continue
    return out


# --------------------------------------------------------------------------- Yahoo / Stooq

STOOQ = {"^BVSP": "^bvp", "^GSPC": "^spx", "^NDX": "^ndx", "URTH": "urth.us", "GLD": "gld.us", "AIQ": "aiq.us",
         "BRL=X": "usdbrl", "QQQ": "qqq.us", "SPY": "spy.us"}


def yahoo(symbol: str, anos: int = 25) -> dict[str, float]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range={anos}y&interval=1d"
    raw = http_get(url, headers={"Accept": "application/json"})
    j = json.loads(raw.decode("utf-8"))
    res = j["chart"]["result"][0]
    ts = res["timestamp"]
    closes = res["indicators"]["quote"][0]["close"]
    out = {}
    for t, c in zip(ts, closes):
        if c is None or not math.isfinite(c):
            continue
        out[datetime.utcfromtimestamp(t).date().isoformat()] = float(c)
    if len(out) < 100:
        raise RuntimeError(f"yahoo {symbol}: só {len(out)} pontos")
    return out


def stooq(symbol: str) -> dict[str, float]:
    s = STOOQ.get(symbol, symbol.lower())
    raw = http_get(f"https://stooq.com/q/d/l/?s={urllib.parse.quote(s)}&i=d").decode("utf-8", errors="replace")
    out = {}
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            out[row["Date"]] = float(row["Close"])
        except Exception:  # noqa: BLE001
            continue
    if len(out) < 100:
        raise RuntimeError(f"stooq {s}: só {len(out)} pontos")
    return out


def serie_mercado(symbol: str, avisos: list[str]) -> dict[str, float] | None:
    for fn, nome in ((yahoo, "Yahoo"), (stooq, "Stooq")):
        try:
            s = fn(symbol)
            log(f"  {symbol}: {len(s)} pontos via {nome} ({min(s)} a {max(s)})")
            return s
        except Exception as e:  # noqa: BLE001
            log(f"  {symbol}: {nome} falhou ({str(e)[:120]})")
    avisos.append(f"benchmark {symbol} indisponível (Yahoo e Stooq falharam)")
    return None


# --------------------------------------------------------------------------- benchmarks

BENCH_DEF = [
    # id, nome, símbolo, moeda, descrição curta
    ("ibov", "Ibovespa", "^BVSP", "BRL", "Índice da B3, em pontos"),
    ("sp500", "S&P 500 (US$)", "^GSPC", "USD", "Índice em dólar"),
    ("sp500brl", "S&P 500 (R$)", "^GSPC", "BRL*", "Índice convertido pelo dólar PTAX"),
    ("nasdaq", "Nasdaq 100 (US$)", "^NDX", "USD", "Índice em dólar"),
    ("msci", "MSCI World (US$)", "URTH", "USD", "Pelo ETF iShares URTH, em dólar"),
    ("mscibrl", "MSCI World (R$)", "URTH", "BRL*", "ETF URTH convertido pelo dólar PTAX"),
]
UNDERLYINGS = {"GLD": "SPDR Gold Shares (GLD)", "AIQ": "Global X Artificial Intelligence & Technology (AIQ)",
               "^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^BVSP": "Ibovespa", "URTH": "MSCI World (URTH)"}


def sintetico(datas: list[date], seed: int, drift: float, vol: float, ini: float = 100.0) -> dict[str, float]:
    rng = random.Random(seed)
    v = ini
    out = {}
    for d in datas:
        v *= math.exp(rng.gauss(drift / 252, vol / math.sqrt(252)))
        out[d.isoformat()] = v
    return out


def construir_benchmarks(datas: list[date], hoje: date, offline: str | None, avisos: list[str]):
    """Devolve (benchmarks, historicos): benchmarks = lista de dicts {id, nome, moeda, fonte, desc, q(np.array)};
    historicos = dict símbolo -> {datas:[...], precos:[...]} (longo, para cenários de COE)."""
    inicio = datas[0] - timedelta(days=40)
    bench = []
    hist = {}
    if offline:
        log("  benchmarks sintéticos (modo offline)")
        mercado = {"^BVSP": sintetico(datas, 1, 0.08, 0.22, 120000), "^GSPC": sintetico(datas, 2, 0.12, 0.16, 5000),
                   "^NDX": sintetico(datas, 3, 0.15, 0.22, 17000), "URTH": sintetico(datas, 4, 0.10, 0.15, 130),
                   "GLD": sintetico(datas, 5, 0.09, 0.14, 180), "AIQ": sintetico(datas, 6, 0.14, 0.24, 30)}
        ptax = sintetico(datas, 7, 0.03, 0.14, 5.2)
        ipca_m = {d.strftime("%Y-%m"): 0.0038 for d in datas}
        poup_m = {d.strftime("%Y-%m"): 0.0062 for d in datas}
    else:
        mercado = {}
        for sym in ["^BVSP", "^GSPC", "^NDX", "URTH", "GLD", "AIQ"]:
            s = serie_mercado(sym, avisos)
            if s:
                mercado[sym] = s
        try:
            ptax = sgs(1, inicio, hoje)
            log(f"  PTAX: {len(ptax)} dias")
        except Exception as e:  # noqa: BLE001
            avisos.append(f"PTAX (SGS 1) indisponível: {e}")
            ptax = mercado.get("BRL=X") or {}
        try:
            ipca_raw = sgs(433, inicio - timedelta(days=60), hoje)
            ipca_m = {k[:7]: v / 100.0 for k, v in ipca_raw.items()}
            log(f"  IPCA: {len(ipca_m)} meses (último {max(ipca_m)})")
        except Exception as e:  # noqa: BLE001
            avisos.append(f"IPCA (SGS 433) indisponível: {e}")
            ipca_m = {}
        try:
            poup_raw = sgs(195, inicio - timedelta(days=60), hoje)
            # 195 = rentabilidade do depósito feito na data (mensal); usa o primeiro dia de cada mês
            poup_m = {}
            for k in sorted(poup_raw):
                ym = k[:7]
                if ym not in poup_m:
                    poup_m[ym] = poup_raw[k] / 100.0
            log(f"  Poupança: {len(poup_m)} meses")
        except Exception as e:  # noqa: BLE001
            avisos.append(f"Poupança (SGS 195) indisponível: {e}")
            poup_m = {}

    ptax_al = alinhar(ptax, datas) if ptax else None

    def add(id_, nome, moeda, fonte, desc, q):
        if q is None or np.isnan(q).all():
            avisos.append(f"benchmark {nome} sem dados")
            return
        bench.append({"id": id_, "nome": nome, "moeda": moeda, "fonte": fonte, "desc": desc, "q": q})

    # IPCA e poupança (índices a partir de taxas mensais)
    if ipca_m:
        q, est = indice_mensal_para_diario(ipca_m, datas)
        add("ipca", "IPCA", "BRL", "BCB SGS 433", "Inflação oficial, distribuída pelos dias úteis do mês" + (f"; {', '.join(est)} estimado pelo mês anterior" if est else ""), q)
    if poup_m:
        q, est = indice_mensal_para_diario(poup_m, datas)
        add("poupanca", "Poupança", "BRL", "BCB SGS 195", "Rendimento da poupança (regra atual)", q)
    if ptax_al is not None:
        add("dolar", "Dólar (PTAX)", "BRL", "BCB SGS 1", "Dólar comercial de venda", ptax_al)
    for id_, nome, sym, moeda, desc in BENCH_DEF:
        s = mercado.get(sym)
        if not s:
            continue
        q = alinhar(s, datas)
        fonte = "Yahoo Finance"
        if moeda == "BRL*":
            if ptax_al is None:
                continue
            q = q * ptax_al
            moeda = "BRL"
            fonte += " + PTAX"
        add(id_, nome, moeda, fonte, desc, q)
    # históricos longos dos ativos-objeto (cenários de COE) e dos índices
    for sym, nome in UNDERLYINGS.items():
        s = mercado.get(sym)
        if not s:
            continue
        ks = sorted(s)
        # a cada dia (mantém tudo; ~20 anos = 5.000 pontos)
        hist[sym] = {"nome": nome, "datas": ks, "precos": [float(f"{s[k]:.6g}") for k in ks]}
    return bench, hist


# --------------------------------------------------------------------------- Tesouro Direto

TESOURO_CSV = ("https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/"
               "resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv")
CUPOM = {"Tesouro IPCA+ com Juros Semestrais": 0.06, "Tesouro Prefixado com Juros Semestrais": 0.10,
         "Tesouro IGPM+ com Juros Semestrais": 0.06}
INDEXADOR = {"Tesouro IPCA+": "IPCA", "Tesouro IPCA+ com Juros Semestrais": "IPCA", "Tesouro Prefixado": "PRE",
             "Tesouro Prefixado com Juros Semestrais": "PRE", "Tesouro Selic": "SELIC", "Tesouro IGPM+ com Juros Semestrais": "IGPM",
             "Tesouro Renda+ Aposentadoria Extra": "IPCA", "Tesouro Educa+": "IPCA"}


def slug(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def duration_mod(tipo: str, venc: date, base: date, taxa: float) -> float | None:
    """Duration modificada (anos) com cupom semestral quando houver; None para Renda+/Educa+ (fluxo em parcelas)."""
    if tipo.startswith("Tesouro Renda+") or tipo.startswith("Tesouro Educa+"):
        return None
    T = (venc - base).days / 365.25
    if T <= 0:
        return None
    c = CUPOM.get(tipo, 0.0)
    y = taxa / 100.0
    if c == 0:
        return T / (1 + y)
    # cupons semestrais contados a partir do vencimento para trás
    pv = 0.0
    tpv = 0.0
    t = T
    k = (1 + c) ** 0.5 - 1
    while t > 1e-6:
        cf = k + (1.0 if abs(t - T) < 1e-9 else 0.0)
        df = (1 + y) ** (-t)
        pv += cf * df
        tpv += t * cf * df
        t -= 0.5
    return (tpv / pv) / (1 + y) if pv > 0 else None


def carregar_tesouro(datas: list[date], hoje: date, offline: str | None, cache: str, avisos: list[str]):
    """Lista de títulos ativos com PU base alinhado ao calendário (retorno total aproximado nos títulos com cupom)."""
    if offline:
        log("  Tesouro sintético (modo offline)")
        titulos = []
        for i, (tipo, venc, taxa) in enumerate([("Tesouro IPCA+", date(2035, 5, 15), 7.6), ("Tesouro IPCA+ com Juros Semestrais", date(2040, 8, 15), 7.4),
                                                 ("Tesouro Prefixado", date(2029, 1, 1), 13.9), ("Tesouro Selic", date(2029, 3, 1), 0.05),
                                                 ("Tesouro Renda+ Aposentadoria Extra", date(2065, 12, 15), 7.3)]):
            s = sintetico(datas, 100 + i, 0.11, 0.03 + 0.02 * i, 1000 + 500 * i)
            tx = {d.isoformat(): taxa + math.sin(k / 40) * 0.6 for k, d in enumerate(datas)}
            titulos.append((tipo, venc, s, tx))
    else:
        p = os.path.join(cache, "PrecoTaxaTesouroDireto.csv")
        raw = http_get(TESOURO_CSV, timeout=300)
        open(p, "wb").write(raw)
        df = pd.read_csv(io.BytesIO(raw), sep=";", decimal=",", encoding="latin-1",
                         usecols=["Tipo Titulo", "Data Vencimento", "Data Base", "Taxa Compra Manha", "PU Base Manha"], dtype=str)
        df["Data Base"] = pd.to_datetime(df["Data Base"], dayfirst=True, errors="coerce")
        df["Data Vencimento"] = pd.to_datetime(df["Data Vencimento"], dayfirst=True, errors="coerce")
        df["PU"] = pd.to_numeric(df["PU Base Manha"].str.replace(".", "", regex=False).str.replace(",", "."), errors="coerce")
        df["Taxa"] = pd.to_numeric(df["Taxa Compra Manha"].str.replace(",", "."), errors="coerce")
        df = df.dropna(subset=["Data Base", "Data Vencimento", "PU"])
        df = df[df["Data Base"].dt.date >= datas[0] - timedelta(days=10)]
        ativos = df[df["Data Vencimento"].dt.date > hoje]
        log(f"  Tesouro: {len(df):,} linhas no período, {ativos.groupby(['Tipo Titulo', 'Data Vencimento']).ngroups} títulos ativos")
        titulos = []
        for (tipo, venc), g in ativos.groupby(["Tipo Titulo", "Data Vencimento"]):
            g = g.sort_values("Data Base")
            s = {d.date().isoformat(): float(v) for d, v in zip(g["Data Base"], g["PU"])}
            tx = {d.date().isoformat(): float(v) for d, v in zip(g["Data Base"], g["Taxa"]) if pd.notna(v)}
            titulos.append((tipo, venc.date(), s, tx))
    out = []
    for tipo, venc, s, tx in titulos:
        q = alinhar(s, datas)
        if np.isnan(q).all():
            continue
        # marca só os dias em que há informe (para não repetir preço em dia sem negociação)
        tem = np.array([d.isoformat() in s for d in datas])
        q_raw = np.where(tem, q, np.nan)
        # retorno total aproximado: reinveste o cupom semestral no dia do pagamento
        c = CUPOM.get(tipo, 0.0)
        if c > 0:
            fat = coup_dates_factor(datas, venc, c)
            acum = np.cumprod(fat)
            q_raw = q_raw * acum
        txa = alinhar(tx, datas)
        i_last = int(np.where(~np.isnan(txa))[0][-1]) if (~np.isnan(txa)).any() else None
        taxa_atual = float(txa[i_last]) if i_last is not None else None
        ano = venc.year
        nome = f"{tipo} {ano}"
        tid = slug(f"{tipo}-{ano}-{venc.month:02d}")
        vals = [v for v in tx.values() if v is not None and math.isfinite(v)]
        out.append({
            "id": tid, "nome": nome, "tipo": tipo, "indexador": INDEXADOR.get(tipo, ""), "venc": venc.isoformat(),
            "cupom": c, "taxa": taxa_atual, "duration": duration_mod(tipo, venc, hoje, taxa_atual) if taxa_atual is not None else None,
            "taxa_hist": {"min": min(vals), "mediana": float(np.median(vals)), "max": max(vals), "desde": min(tx) if tx else None} if vals else None,
            "q": q_raw, "taxa_serie": txa,
        })
    log(f"  Tesouro: {len(out)} títulos publicados")
    return out


# --------------------------------------------------------------------------- fundos XP

TIPO_XP = [
    ("Previdência", None),
    ("Renda Fixa", ["referenciado di", "crédito", "credito", "debêntures", "debentures", "renda fixa", "inflação/pré", "inflacao/pre"]),
    ("Multimercado", ["macro", "multiestratégia", "multiestrategia", "long short", "quantitativo"]),
    ("Ações", ["renda variável", "renda variavel", "long only", "long biased"]),
    ("Internacional", ["internacional"]),
    ("Cambial", ["cambial"]),
    ("Alternativos", ["alternativo", "fundo listado", "outros"]),
]


def tipo_xp(classe: str, origem: str) -> str:
    if origem == "previdencia":
        return "Previdência"
    c = (classe or "").lower()
    for tipo, chaves in TIPO_XP[1:]:
        if any(k in c for k in chaves):
            return tipo
    return "Outros"


def carregar_xp(caminho: str) -> dict[str, dict]:
    if not os.path.exists(caminho):
        return {}
    out = {}
    with open(caminho, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("status", "").strip().lower() == "status" or not r.get("cnpj"):
                continue
            cnpj = r["cnpj"]
            item = {
                "nome_xp": r.get("nome", ""), "origem": r.get("origem", ""), "classe": r.get("classe_xp", ""),
                "tipo": tipo_xp(r.get("classe_xp", ""), r.get("origem", "")), "cvm": r.get("cvm", ""),
                "risco": _num(r.get("risco")), "top": r.get("top") == "1", "estrelas": _num(r.get("estrelas")),
                "publico": r.get("publico", ""), "aplic_min": _num(r.get("aplic_min")), "status": r.get("status", ""),
                "benchmark": r.get("benchmark", ""), "pagina": r.get("pagina_xp", ""), "taxa_adm": _num(r.get("taxa_adm")),
                "taxa_perf": _num(r.get("taxa_perf")), "liquidez_dias": _num(r.get("liquidez_dias")),
            }
            # o mesmo CNPJ pode aparecer em fundos e previdência: prefere o registro de fundos
            if cnpj in out and out[cnpj]["origem"] == "fundos":
                continue
            out[cnpj] = item
    return out


def _num(v):
    try:
        if v is None or str(v).strip() in ("", "-"):
            return None
        return float(v)
    except Exception:  # noqa: BLE001
        return None
