#!/usr/bin/env python3
"""
Fontes extras do Comparador de Ativos: benchmarks (BCB + Yahoo/Stooq), Tesouro Direto (Tesouro Transparente)
e a lista de fundos da plataforma XP (planilha "Guia de Fundos", extraída para xp_fundos.csv).

Todas as funções são tolerantes: uma fonte que falhar vira aviso, nunca derruba a execução.
"""
from __future__ import annotations

import base64
import csv
import http.cookiejar
import io
import shutil
import json
import math
import os
import random
import re
import time
import urllib.error
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

def json_com_retentativa(url: str, tentativas: int = 6, espera: int = 25):
    """A API do BCB às vezes devolve uma página HTML (manutenção ou limite de acesso) em vez de JSON: insiste com pausa."""
    ultimo = None
    for i in range(tentativas):
        try:
            raw = http_get(url, tentativas=2, timeout=90, headers={"Accept": "application/json"})
            return json.loads(raw.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            ultimo = e
            log(f"  {url.split('?')[0].split('/')[-2] if '/dados' in url else url[:60]}: resposta inválida ({str(e)[:80]}); nova tentativa em {espera}s")
            time.sleep(espera)
    raise RuntimeError(f"{url}: {ultimo}")


def sgs(codigo: int, inicio: date, fim: date) -> dict[str, float]:
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"
           f"&dataInicial={inicio.strftime('%d/%m/%Y')}&dataFinal={fim.strftime('%d/%m/%Y')}")
    dados = json_com_retentativa(url)
    out = {}
    for d in dados:
        try:
            dt = datetime.strptime(d["data"], "%d/%m/%Y").date().isoformat()
            out[dt] = float(str(d["valor"]).replace(",", "."))
        except Exception:  # noqa: BLE001
            continue
    return out


# --------------------------------------------------------------------------- índices e ETFs (Yahoo, Stooq, FRED, BCB, Nasdaq)

STOOQ = {"^BVSP": "^bvp", "^GSPC": "^spx", "^NDX": "^ndx", "URTH": "urth.us", "GLD": "gld.us", "AIQ": "aiq.us",
         "BRL=X": "usdbrl", "QQQ": "qqq.us", "SPY": "spy.us"}
FRED = {"^GSPC": "SP500", "^NDX": "NASDAQ100", "^DJI": "DJIA"}
SGS_INDICE = {"^BVSP": 7}  # Ibovespa, fechamento diário em pontos
NASDAQ = {"URTH": ("URTH", "etf"), "GLD": ("GLD", "etf"), "AIQ": ("AIQ", "etf"), "QQQ": ("QQQ", "etf"), "SPY": ("SPY", "etf"),
          "^NDX": ("NDX", "index"), "^GSPC": ("SPY", "etf")}  # a API da Nasdaq não tem o SPX; o ETF SPY acompanha o índice de preço
_MIN_PONTOS = 100


def _erro(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        try:
            corpo = e.read(200).decode("utf-8", errors="replace").replace("\n", " ")
        except Exception:  # noqa: BLE001
            corpo = ""
        return f"HTTP {e.code} {corpo[:120]}".strip()
    return str(e)[:200]


def _opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def _get(opener, url: str, headers: dict | None = None, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9", **(headers or {})})
    with opener.open(req, timeout=timeout) as r:
        return r.read()


_YAHOO: dict = {"opener": None, "crumb": None}


def _yahoo_sessao():
    """Cookie de consentimento + crumb, como o yfinance faz; sem isso o Yahoo devolve 401/429 fora do navegador."""
    if _YAHOO["crumb"]:
        return _YAHOO["opener"], _YAHOO["crumb"]
    opener = _opener()
    try:
        _get(opener, "https://fc.yahoo.com/", timeout=30)
    except Exception:  # noqa: BLE001  (404 esperado; os cookies vêm assim mesmo)
        pass
    crumb = _get(opener, "https://query2.finance.yahoo.com/v1/test/getcrumb", headers={"Accept": "text/plain"}, timeout=30).decode("utf-8", errors="replace").strip()
    if not crumb or "<" in crumb or len(crumb) > 40:
        raise RuntimeError("crumb inválido")
    _YAHOO.update(opener=opener, crumb=crumb)
    return opener, crumb


def _yahoo_parse(raw: bytes, symbol: str) -> dict[str, float]:
    j = json.loads(raw.decode("utf-8"))
    chart = j.get("chart") or {}
    if not chart.get("result"):
        raise RuntimeError(str(chart.get("error"))[:200])
    res = chart["result"][0]
    ts = res.get("timestamp") or []
    closes = ((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    out = {}
    for t, c in zip(ts, closes):
        if c is None or not math.isfinite(c):
            continue
        out[datetime.utcfromtimestamp(t).date().isoformat()] = float(c)
    if len(out) < _MIN_PONTOS:
        raise RuntimeError(f"yahoo {symbol}: só {len(out)} pontos")
    return out


def yahoo(symbol: str, anos: int = 25) -> dict[str, float]:
    p1 = int(time.time()) - anos * 365 * 86400
    p2 = int(time.time()) + 86400
    base = f"/v8/finance/chart/{urllib.parse.quote(symbol)}?period1={p1}&period2={p2}&interval=1d&events=history"
    erros = []
    # 1) chamada simples (funciona em muitos ambientes); 2) com cookie + crumb
    for modo in ("simples", "crumb"):
        for host in ("query2", "query1"):
            try:
                if modo == "simples":
                    raw = http_get(f"https://{host}.finance.yahoo.com{base}", tentativas=1, timeout=60, headers={"Accept": "application/json,text/plain,*/*"})
                else:
                    opener, crumb = _yahoo_sessao()
                    raw = _get(opener, f"https://{host}.finance.yahoo.com{base}&crumb={urllib.parse.quote(crumb)}", headers={"Accept": "application/json,text/plain,*/*"})
                return _yahoo_parse(raw, symbol)
            except Exception as e:  # noqa: BLE001
                erros.append(f"{modo}/{host}: {_erro(e)}")
                if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 429):
                    _YAHOO["crumb"] = None
                    if e.code == 429:
                        raise RuntimeError("; ".join(erros)[:400])  # bloqueio por IP: não insiste
    raise RuntimeError("; ".join(erros)[:400])


def stooq(symbol: str) -> dict[str, float]:
    s = STOOQ.get(symbol, symbol.lower())
    erros = []
    for host in ("stooq.com", "stooq.pl"):
        try:
            raw = http_get(f"https://{host}/q/d/l/?s={urllib.parse.quote(s)}&i=d", tentativas=1, timeout=60,
                           headers={"Referer": f"https://{host}/q/d/?s={urllib.parse.quote(s)}", "Accept": "text/csv,text/plain,*/*"}).decode("utf-8", errors="replace")
            out = {}
            for row in csv.DictReader(io.StringIO(raw)):
                try:
                    out[row["Date"]] = float(row["Close"])
                except Exception:  # noqa: BLE001
                    continue
            if len(out) >= _MIN_PONTOS:
                return out
            erros.append(f"{host}: {len(out)} pontos, resposta '{raw[:80].strip()}'")
        except Exception as e:  # noqa: BLE001
            erros.append(f"{host}: {_erro(e)}")
    raise RuntimeError("; ".join(erros)[:400])


def fred(symbol: str) -> dict[str, float]:
    sid = FRED.get(symbol)
    if not sid:
        raise RuntimeError("sem série no FRED")
    raw = http_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", tentativas=1, timeout=150, headers={"Accept": "text/csv,*/*"}).decode("utf-8", errors="replace")
    out = {}
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            d = row.get("observation_date") or row.get("DATE")
            out[d] = float(row[sid])
        except Exception:  # noqa: BLE001
            continue
    if len(out) < _MIN_PONTOS:
        raise RuntimeError(f"fred {sid}: só {len(out)} pontos, resposta '{raw[:80].strip()}'")
    return out


def sgs_indice(symbol: str) -> dict[str, float]:
    cod = SGS_INDICE.get(symbol)
    if not cod:
        raise RuntimeError("sem série no BCB")
    hoje = date.today()
    out = {}
    # a API do SGS limita séries diárias a 10 anos por chamada
    for k in range(2):
        fim = hoje - timedelta(days=3650 * k)
        ini = fim - timedelta(days=3649)
        try:
            out.update(sgs(cod, ini, fim))
        except Exception as e:  # noqa: BLE001
            if k == 0:
                raise RuntimeError(f"sgs {cod}: {_erro(e)}")
    out = {d: v for d, v in out.items() if v and v > 0}
    if len(out) < _MIN_PONTOS:
        raise RuntimeError(f"sgs {cod}: só {len(out)} pontos")
    return out


def nasdaq_api(symbol: str) -> dict[str, float]:
    sym, cls = NASDAQ.get(symbol, (None, None))
    if not sym:
        raise RuntimeError("sem símbolo na API da Nasdaq")
    hoje = date.today()
    url = (f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(sym)}/historical?assetclass={cls}"
           f"&fromdate={(hoje - timedelta(days=365 * 25)).isoformat()}&todate={hoje.isoformat()}&limit=10000")
    raw = http_get(url, tentativas=2, timeout=90, headers={"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})
    j = json.loads(raw.decode("utf-8", errors="replace"))
    rows = (((j.get("data") or {}).get("tradesTable") or {}).get("rows")) or []
    out = {}
    for r in rows:
        try:
            d = datetime.strptime(r["date"], "%m/%d/%Y").date().isoformat()
            out[d] = float(str(r["close"]).replace("$", "").replace(",", ""))
        except Exception:  # noqa: BLE001
            continue
    if len(out) < _MIN_PONTOS:
        raise RuntimeError(f"nasdaq {symbol}: só {len(out)} pontos ({str(j.get('status'))[:120]})")
    return out


B3_INDICES = {"^BVSP": "IBOV", "IFIX": "IFIX", "IDIV": "IDIV", "SMLL": "SMLL"}


def b3_ibov(symbol: str) -> dict[str, float]:
    """Fechamentos diários de um índice da B3 (estatísticas históricas), um pedido por ano."""
    idx = B3_INDICES.get(symbol)
    if not idx:
        raise RuntimeError("índice não está na B3")
    out = {}
    ano_atual = date.today().year
    erro = None
    for ano in range(ano_atual - 24, ano_atual + 1):
        payload = base64.b64encode(json.dumps({"index": idx, "language": "pt-br", "year": str(ano)}, separators=(",", ":")).encode()).decode()
        try:
            raw = http_get(f"https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/{payload}",
                           tentativas=2, timeout=60, headers={"Accept": "application/json, text/plain, */*", "Referer": "https://www.b3.com.br/"})
            j = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception as e:  # noqa: BLE001
            erro = _erro(e)
            continue
        for row in (j.get("results") or []):
            d = row.get("day")
            for m in range(1, 13):
                v = row.get(f"rateValue{m}")
                if not v:
                    continue
                try:
                    out[f"{ano:04d}-{m:02d}-{int(d):02d}"] = float(str(v).replace(".", "").replace(",", "."))
                except Exception:  # noqa: BLE001
                    continue
    if len(out) < _MIN_PONTOS:
        raise RuntimeError(f"b3: só {len(out)} pontos ({erro})")
    return out


def coinbase(symbol: str) -> dict[str, float]:
    """Fechamento diário de criptoativos em dólar pela API pública da Coinbase Exchange (sem chave, 300 velas por chamada)."""
    produtos = {"BTC-USD": "BTC-USD", "ETH-USD": "ETH-USD"}
    if symbol not in produtos:
        raise RuntimeError("sem série na Coinbase")
    out: dict[str, float] = {}
    ini = date(2016, 1, 1)
    hoje = date.today()
    while ini <= hoje:
        fim = min(ini + timedelta(days=290), hoje)
        url = (f"https://api.exchange.coinbase.com/products/{produtos[symbol]}/candles?granularity=86400"
               f"&start={ini.isoformat()}T00:00:00Z&end={fim.isoformat()}T23:59:59Z")
        raw = http_get(url, tentativas=2, timeout=60, headers={"Accept": "application/json"})
        j = json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(j, list):
            raise RuntimeError(f"coinbase: resposta inesperada ({str(j)[:120]})")
        for vela in j:  # [tempo, mínima, máxima, abertura, fechamento, volume]
            try:
                out[datetime.utcfromtimestamp(int(vela[0])).date().isoformat()] = float(vela[4])
            except Exception:  # noqa: BLE001
                continue
        ini = fim + timedelta(days=1)
        time.sleep(0.4)
    if len(out) < _MIN_PONTOS:
        raise RuntimeError(f"coinbase {symbol}: só {len(out)} pontos")
    return out


def coingecko(symbol: str) -> dict[str, float]:
    """Preço diário de criptoativos (CoinGecko, sem chave: a API pública limita a 365 dias)."""
    moedas = {"BTC-BRL": ("bitcoin", "brl"), "ETH-BRL": ("ethereum", "brl"), "BTC-USD": ("bitcoin", "usd")}
    if symbol not in moedas:
        raise RuntimeError("sem série no CoinGecko")
    cid, vs = moedas[symbol]
    raw = http_get(f"https://api.coingecko.com/api/v3/coins/{cid}/market_chart?vs_currency={vs}&days=365&interval=daily", tentativas=2, timeout=90,
                   headers={"Accept": "application/json"})
    j = json.loads(raw.decode("utf-8", errors="replace"))
    out = {}
    for t, v in j.get("prices") or []:
        try:
            out[datetime.utcfromtimestamp(t / 1000).date().isoformat()] = float(v)
        except Exception:  # noqa: BLE001
            continue
    if len(out) < _MIN_PONTOS:
        raise RuntimeError(f"coingecko {cid}: só {len(out)} pontos ({str(j)[:120]})")
    return out


def anbima_ima_hoje() -> dict[str, tuple[str, float]]:
    """Lê o resultado diário público do IMA (ima_completo.txt): índice -> (data AAAA-MM-DD, número índice)."""
    raw = http_get("https://www.anbima.com.br/informacoes/ima/arqs/ima_completo.txt", tentativas=2, timeout=60)
    txt = raw.decode("latin-1", errors="replace")
    out: dict[str, tuple[str, float]] = {}
    for linha in txt.splitlines():
        campos = linha.split("@")
        if len(campos) < 4 or not re.match(r"\d{2}/\d{2}/\d{4}$", campos[1].strip()):
            continue
        d, m, y = campos[1].strip().split("/")
        nome = campos[2].strip()
        try:
            val = float(campos[3].strip().replace(".", "").replace(",", "."))
        except ValueError:
            continue
        if nome and val > 0:
            out[nome] = (f"{y}-{m}-{d}", val)
    if not out:
        raise RuntimeError("ima_completo.txt sem linhas reconhecíveis")
    return out


FONTES_POR_SIMBOLO = {
    "^BVSP": ((b3_ibov, "B3"), (yahoo, "Yahoo"), (stooq, "Stooq"), (sgs_indice, "BCB SGS 7")),
    "^GSPC": ((nasdaq_api, "Nasdaq (ETF SPY)"), (yahoo, "Yahoo"), (stooq, "Stooq"), (fred, "FRED")),  # o FRED não responde de dentro do Actions
    "^NDX": ((nasdaq_api, "Nasdaq"), (fred, "FRED"), (yahoo, "Yahoo"), (stooq, "Stooq")),
    "IFIX": ((b3_ibov, "B3"),),
    "BTC-USD": ((coinbase, "Coinbase"), (coingecko, "CoinGecko")),
}
FONTES_PADRAO = ((nasdaq_api, "Nasdaq"), (yahoo, "Yahoo"), (stooq, "Stooq"))
_MAX_ATRASO_DIAS = 15


FONTE_USADA: dict[str, str] = {}


def serie_mercado(symbol: str, avisos: list[str]) -> dict[str, float] | None:
    for fn, nome in FONTES_POR_SIMBOLO.get(symbol, FONTES_PADRAO):
        try:
            s = fn(symbol)
            if (date.today() - date.fromisoformat(max(s))).days > _MAX_ATRASO_DIAS:
                raise RuntimeError(f"série desatualizada (último dado em {max(s)})")
            log(f"  {symbol}: {len(s)} pontos via {nome} ({min(s)} a {max(s)})")
            FONTE_USADA[symbol] = nome
            return s
        except Exception as e:  # noqa: BLE001
            log(f"  {symbol}: {nome} falhou ({str(e)[:400]})")
    avisos.append(f"benchmark {symbol} indisponível (todas as fontes falharam)")
    return None


# --------------------------------------------------------------------------- benchmarks

BENCH_DEF = [
    # id, nome, símbolo, moeda, descrição curta
    ("ibov", "Ibovespa", "^BVSP", "BRL", "Índice da B3, em pontos"),
    ("sp500", "S&P 500 (US$)", "^GSPC", "USD", "Índice em dólar"),
    ("sp500brl", "S&P 500 (R$)", "^GSPC", "BRL*", "Índice convertido pelo dólar PTAX"),
    ("nasdaq", "Nasdaq 100 (US$)", "^NDX", "USD", "Índice em dólar"),
    ("nasdaqbrl", "Nasdaq 100 (R$)", "^NDX", "BRL*", "Índice convertido pelo dólar PTAX"),
    ("msci", "MSCI World (US$)", "URTH", "USD", "Pelo ETF iShares URTH, em dólar"),
    ("mscibrl", "MSCI World (R$)", "URTH", "BRL*", "ETF URTH convertido pelo dólar PTAX"),
    ("ifix", "IFIX", "IFIX", "BRL", "Índice de fundos imobiliários da B3"),
    ("ouro", "Ouro (US$)", "GLD", "USD", "Pelo ETF SPDR Gold Shares (GLD), em dólar"),
    ("ourobrl", "Ouro (R$)", "GLD", "BRL*", "ETF GLD convertido pelo dólar PTAX"),
    ("btc", "Bitcoin (R$)", "BTC-USD", "BRL*", "Fechamento diário em dólar (Coinbase) convertido pelo dólar PTAX"),
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
                   "GLD": sintetico(datas, 5, 0.09, 0.14, 180), "AIQ": sintetico(datas, 6, 0.14, 0.24, 30),
                   "IFIX": sintetico(datas, 8, 0.06, 0.10, 3000), "BTC-USD": sintetico(datas, 9, 0.30, 0.60, 30000)}
        ptax = sintetico(datas, 7, 0.03, 0.14, 5.2)
        ipca_m = {d.strftime("%Y-%m"): 0.0038 for d in datas}
        poup_m = {d.strftime("%Y-%m"): 0.0062 for d in datas}
    else:
        mercado = {}
        for sym in ["^BVSP", "^GSPC", "^NDX", "URTH", "GLD", "AIQ", "IFIX", "BTC-USD"]:
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
        # IPCA + 6% a.a.: referência de juro real, capitalizada por dia útil sobre o IPCA
        n = len(datas)
        add("ipca6", "IPCA + 6%", "BRL", "BCB SGS 433 + 6% a.a.", "IPCA mais juro real de 6% ao ano, capitalizado por dia útil (referência para renda fixa atrelada à inflação)", q * np.power(1.06, np.arange(n) / 252.0))
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
        usada = FONTE_USADA.get(sym, "")
        fonte = {"Yahoo": "Yahoo Finance", "Stooq": "Stooq", "FRED": "FRED (Fed de St. Louis)", "BCB SGS 7": "BCB SGS 7", "Nasdaq": "Nasdaq", "B3": "B3", "Nasdaq (ETF SPY)": "Nasdaq (ETF SPY)", "CoinGecko": "CoinGecko", "Coinbase": "Coinbase"}.get(usada, usada or "Yahoo Finance")
        if usada == "Nasdaq (ETF SPY)":
            desc = "Pelo ETF SPY (preço, sem dividendos), em dólar" if moeda == "USD" else "ETF SPY convertido pelo dólar PTAX"
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
        if FONTE_USADA.get(sym) == "Nasdaq (ETF SPY)":
            nome = "S&P 500 (ETF SPY)"
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
        lista = [("Tesouro IPCA+", date(2029, 5, 15), 7.9), ("Tesouro IPCA+", date(2035, 5, 15), 7.6), ("Tesouro IPCA+", date(2040, 5, 15), 7.5), ("Tesouro IPCA+", date(2045, 5, 15), 7.4), ("Tesouro IPCA+", date(2050, 5, 15), 7.3),
                 ("Tesouro IPCA+ com Juros Semestrais", date(2030, 8, 15), 7.7), ("Tesouro IPCA+ com Juros Semestrais", date(2035, 5, 15), 7.5), ("Tesouro IPCA+ com Juros Semestrais", date(2040, 8, 15), 7.4), ("Tesouro IPCA+ com Juros Semestrais", date(2045, 5, 15), 7.4), ("Tesouro IPCA+ com Juros Semestrais", date(2050, 8, 15), 7.3), ("Tesouro IPCA+ com Juros Semestrais", date(2055, 5, 15), 7.3),
                 ("Tesouro Prefixado", date(2027, 1, 1), 14.2), ("Tesouro Prefixado", date(2029, 1, 1), 13.9), ("Tesouro Prefixado", date(2032, 1, 1), 13.7), ("Tesouro Prefixado com Juros Semestrais", date(2035, 1, 1), 13.6),
                 ("Tesouro Selic", date(2029, 3, 1), 0.05), ("Tesouro Selic", date(2031, 3, 1), 0.1),
                 ("Tesouro Renda+ Aposentadoria Extra", date(2045, 12, 15), 7.4), ("Tesouro Renda+ Aposentadoria Extra", date(2065, 12, 15), 7.3), ("Tesouro Educa+", date(2035, 12, 15), 7.4)]
        for i, (tipo, venc, taxa) in enumerate(lista):
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
                "gestor": (r.get("gestor") or "").strip(),
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


# --------------------------------------------------------------------------- ícones das gestoras (favicons com o fundo branco removido)

LOGO_FONTES = {
    "g": lambda d: f"https://www.google.com/s2/favicons?domain={d}&sz=64",
    "www": lambda d: f"https://www.google.com/s2/favicons?domain=www.{d}&sz=64",
    "v2": lambda d: f"https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://www.{d}&size=128",
}


def slug_site(site: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (site or "").lower()).strip("_")


def processar_logo(raw: bytes, tamanho: int = 64) -> bytes | None:
    """Converte o favicon em PNG quadrado com fundo transparente: pixels quase brancos ligados à borda viram transparentes
    (os brancos internos, dentro das letras, ficam). Devolve None quando a imagem é pequena demais ou ilegível."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        im = Image.open(io.BytesIO(raw))
        if getattr(im, "n_frames", 1) > 1:  # .ico com vários tamanhos: pega o maior
            melhor = None
            for k in range(im.n_frames):
                im.seek(k)
                if melhor is None or im.size[0] > melhor.size[0]:
                    melhor = im.copy()
            im = melhor
        im = im.convert("RGBA")
    except Exception:
        return None
    if min(im.size) < 24:
        return None
    w, h = im.size
    px = im.load()
    # remoção do fundo: busca em largura a partir das bordas pelos pixels quase brancos (ou já transparentes)
    def fundo(p):
        r, g, b, a = p
        return a < 20 or (r > 232 and g > 232 and b > 232 and max(r, g, b) - min(r, g, b) < 18)
    visit = bytearray(w * h)
    fila = []
    for x in range(w):
        for y in (0, h - 1):
            if fundo(px[x, y]):
                fila.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if fundo(px[x, y]):
                fila.append((x, y))
    while fila:
        x, y = fila.pop()
        i = y * w + x
        if visit[i]:
            continue
        visit[i] = 1
        r, g, b, a = px[x, y]
        px[x, y] = (r, g, b, 0)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not visit[ny * w + nx] and fundo(px[nx, ny]):
                fila.append((nx, ny))
    # recorta a área útil, enquadra num quadrado com margem e redimensiona
    bbox = im.getchannel("A").getbbox()
    if not bbox:
        return None
    im = im.crop(bbox)
    lado = max(im.size)
    quadro = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    quadro.paste(im, ((lado - im.size[0]) // 2, (lado - im.size[1]) // 2))
    quadro = quadro.resize((tamanho, tamanho), Image.LANCZOS)
    out = io.BytesIO()
    quadro.save(out, format="PNG", optimize=True)
    return out.getvalue()


def baixar_logos(gestoras: list[dict], out_dir: str, cache_dir: str, log=print, dias_cache: int = 30) -> int:
    """Baixa o favicon de cada gestora com `logo` definido, remove o fundo e grava <out_dir>/<slug>.png.
    Marca g["logo_proc"] = True nas que deram certo. O resultado fica em cache por `dias_cache` dias."""
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        log("  ícones das gestoras: Pillow ausente, pulando (pip install pillow)")
        return 0
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)
    ok = 0
    motivos: dict[str, int] = {}
    for g in gestoras:
        modo, site = g.get("logo"), g.get("site")
        if not modo or not site or modo not in LOGO_FONTES:
            continue
        slug = slug_site(site)
        alvo = os.path.join(out_dir, slug + ".png")
        cache = os.path.join(cache_dir, slug + ".png")
        falha = os.path.join(cache_dir, slug + ".sem-icone")
        agora = time.time()
        if os.path.exists(cache) and agora - os.path.getmtime(cache) < dias_cache * 86400:
            shutil.copyfile(cache, alvo)
            g["logo_proc"] = True
            ok += 1
            continue
        if os.path.exists(falha) and agora - os.path.getmtime(falha) < dias_cache * 86400:
            continue
        png = None
        try:
            raw = http_get(LOGO_FONTES[modo](site), tentativas=2, timeout=30)
            png = processar_logo(raw)
            if not png:
                motivos["imagem pequena ou ilegível"] = motivos.get("imagem pequena ou ilegível", 0) + 1
        except Exception as e:
            chave = type(e).__name__ + ": " + str(e)[:60]
            motivos[chave] = motivos.get(chave, 0) + 1
        if png:
            with open(cache, "wb") as fh:
                fh.write(png)
            shutil.copyfile(cache, alvo)
            g["logo_proc"] = True
            ok += 1
        else:
            open(falha, "w").close()
    log(f"  ícones das gestoras: {ok} processados (fundo transparente)" + (
        "; sem ícone: " + ", ".join(f"{k} ×{v}" for k, v in sorted(motivos.items(), key=lambda kv: -kv[1])[:4]) if motivos else ""))
    return ok
