"""Ações e BDRs negociados na B3.

Universo: o arquivo anual de cotações históricas da B3 (COTAHIST, oficial), filtrado ao mercado à vista em lote padrão:
ações (ON, PN, UNT) e BDRs (DRN, DR1, DR2, DR3, DRE). Entram os papéis com negócios em pelo menos LIQ_MIN dos pregões dos
últimos 12 meses; os ilíquidos ficam com preço parado por semanas e distorcem a comparação.

Preços: cotação ajustada do Yahoo Finance (dividendos e desdobramentos incorporados, comparável à cota de um fundo), uma
chamada por papel, com cache em disco: se o Yahoo falhar numa execução, fica a série da execução anterior.
"""
from __future__ import annotations

import io
import json
import math
import os
import random
import re
import time
import urllib.error
import urllib.parse
import zipfile
from datetime import date, datetime, timedelta

import numpy as np

import fontes_extras as fx

COTAHIST_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP"
LIQ_MIN = 0.60          # fração mínima dos pregões com negócio (últimos 12 meses)
SESSOES_MIN = 20        # pregões mínimos com negócio
PREGOES_12M = 252
PAUSA_YAHOO = 0.15      # segundos entre chamadas
FALHAS_SEGUIDAS_MAX = 25  # a partir daí o Yahoo é dado como fora do ar e o resto usa só o cache
ESPECIES_ACAO = ("ON", "PN", "PNA", "PNB", "PNC", "PND", "PNE", "PNF", "UNT")
ESPECIES_BDR = ("DRN", "DR1", "DR2", "DR3", "DRE")

log = fx.log


# --------------------------------------------------------------------------- COTAHIST

def _ler_cotahist(raw: bytes, por_ticker: dict, pregoes: set) -> None:
    """Lê um ZIP anual da B3 (registros de 245 posições) e acumula, por papel, os pregões com negócio."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        nome = next((n for n in z.namelist() if n.upper().endswith(".TXT")), None)
        if not nome:
            raise RuntimeError("ZIP sem o TXT de cotações")
        with z.open(nome) as fh:
            for linha in io.TextIOWrapper(fh, encoding="latin-1", newline=None):
                if not linha.startswith("01") or linha[24:27] != "010" or linha[10:12] != "02":
                    continue
                especi = linha[39:49].split()
                esp = especi[0] if especi else ""
                if esp in ESPECIES_ACAO:
                    tipo = "acao"
                elif esp in ESPECIES_BDR:
                    tipo = "bdr"
                else:
                    continue
                ticker = linha[12:24].strip()
                if not re.fullmatch(r"[A-Z0-9]{4}\d{1,2}", ticker):
                    continue
                d = linha[2:10]
                dia = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
                try:
                    ult = int(linha[108:121]) / 100.0
                    vol = int(linha[170:188]) / 100.0
                    neg = int(linha[147:152])
                except ValueError:
                    continue
                if ult <= 0 or neg <= 0:
                    continue
                pregoes.add(dia)
                p = por_ticker.get(ticker)
                if p is None:
                    p = por_ticker[ticker] = {"ticker": ticker, "nome": linha[27:39].strip(), "especi": esp, "tipo": tipo, "dias": {}}
                p["dias"][dia] = (ult, vol)


def _baixar_cotahist(ano: int, cache: str, atual: bool) -> bytes:
    """O arquivo do ano corrente é baixado a cada execução (muda todo dia); os anos fechados ficam em cache."""
    os.makedirs(cache, exist_ok=True)
    arq = os.path.join(cache, f"COTAHIST_A{ano}.ZIP")
    if not atual and os.path.exists(arq) and os.path.getsize(arq) > 1_000_000:
        with open(arq, "rb") as fh:
            return fh.read()
    raw = fx.http_get(COTAHIST_URL.format(ano=ano), tentativas=3, timeout=300,
                      headers={"Accept": "application/zip,application/octet-stream,*/*", "Referer": "https://www.b3.com.br/"})
    if len(raw) < 100_000 or raw[:2] != b"PK":
        raise RuntimeError(f"COTAHIST {ano}: resposta inesperada ({len(raw)} bytes)")
    if not atual:
        with open(arq, "wb") as fh:
            fh.write(raw)
    return raw


def universo(hoje: date, cache: str, avisos: list[str]) -> tuple[list[dict], dict]:
    """Papéis em negociação com liquidez mínima; devolve (lista, info) com a contagem e a data do último pregão."""
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
    pos = {d: i for i, d in enumerate(ordem)}
    out = []
    for p in por_ticker.values():
        dias = p["dias"]
        if not dias:
            continue
        primeiro = min(dias)
        # pregões possíveis desde a estreia do papel, dentro da janela de 12 meses
        possiveis = [d for d in janela if d >= primeiro]
        com_negocio = [d for d in possiveis if d in dias]
        if len(possiveis) == 0 or len(com_negocio) < SESSOES_MIN or len(com_negocio) / len(possiveis) < LIQ_MIN:
            continue
        ultimo = max(dias)
        vols = sorted(dias[d][1] for d in com_negocio)
        out.append({
            "ticker": p["ticker"], "nome": p["nome"], "especi": p["especi"], "tipo": p["tipo"],
            "ultimo": ultimo, "preco": dias[ultimo][0],
            "liq": float(np.median(vols)) if vols else 0.0,
            "sessoes": len(com_negocio), "possiveis": len(possiveis), "estreia": primeiro,
        })
    out.sort(key=lambda x: -x["liq"])
    info = {"pregoes": len(ordem), "ultimo_pregao": ordem[-1] if ordem else None, "papeis_no_arquivo": len(por_ticker)}
    return out, info


# --------------------------------------------------------------------------- Yahoo (cotação ajustada)

def _yahoo_adj(symbol: str, anos: int = 6) -> tuple[dict[str, float], dict]:
    """Série 'AAAA-MM-DD' -> cotação ajustada, mais os metadados (nome longo, moeda)."""
    p1 = int(time.time()) - anos * 365 * 86400
    p2 = int(time.time()) + 86400
    base = f"/v8/finance/chart/{urllib.parse.quote(symbol)}?period1={p1}&period2={p2}&interval=1d&events=div%2Csplits"
    erros = []
    for modo in ("simples", "crumb"):
        for host in ("query2", "query1"):
            try:
                if modo == "simples":
                    raw = fx.http_get(f"https://{host}.finance.yahoo.com{base}", tentativas=1, timeout=60,
                                      headers={"Accept": "application/json,text/plain,*/*"})
                else:
                    opener, crumb = fx._yahoo_sessao()
                    raw = fx._get(opener, f"https://{host}.finance.yahoo.com{base}&crumb={urllib.parse.quote(crumb)}",
                                  headers={"Accept": "application/json,text/plain,*/*"})
                j = json.loads(raw.decode("utf-8"))
                chart = j.get("chart") or {}
                if not chart.get("result"):
                    raise RuntimeError(str(chart.get("error"))[:200])
                res = chart["result"][0]
                meta = res.get("meta") or {}
                off = int(meta.get("gmtoffset") or 0)
                ts = res.get("timestamp") or []
                ind = res.get("indicators") or {}
                adj = ((ind.get("adjclose") or [{}])[0].get("adjclose")) or []
                clo = ((ind.get("quote") or [{}])[0].get("close")) or []
                vals = adj if len(adj) == len(ts) and any(v is not None for v in adj) else clo
                out = {}
                for t, c in zip(ts, vals):
                    if c is None or not math.isfinite(c) or c <= 0:
                        continue
                    out[(datetime.utcfromtimestamp(t + off)).date().isoformat()] = float(c)
                if len(out) < 30:
                    raise RuntimeError(f"só {len(out)} pontos")
                return out, {"nome_longo": meta.get("longName") or meta.get("shortName"), "moeda": meta.get("currency"),
                             "ajustada": vals is adj}
            except Exception as e:  # noqa: BLE001
                erros.append(f"{modo}/{host}: {fx._erro(e)}")
                if isinstance(e, urllib.error.HTTPError):
                    if e.code == 404:
                        raise RuntimeError("não existe no Yahoo") from None
                    if e.code in (401, 403, 429):
                        fx._YAHOO["crumb"] = None
                        if e.code == 429:
                            raise RuntimeError("429 " + "; ".join(erros)[:300]) from None
    raise RuntimeError("; ".join(erros)[:400])


def _ler_cache(arq: str) -> dict | None:
    try:
        with open(arq, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def precos(papeis: list[dict], cache: str, avisos: list[str], hoje: date) -> dict[str, dict]:
    """ticker -> {serie, meta, fonte}. Chama o Yahoo papel a papel; cai no cache quando a chamada falha."""
    pasta = os.path.join(cache, "acoes")
    os.makedirs(pasta, exist_ok=True)
    out: dict[str, dict] = {}
    falhas_seguidas = 0
    yahoo_fora = False
    n_yahoo = n_cache = n_sem = 0
    t0 = time.time()
    for i, p in enumerate(papeis):
        tk = p["ticker"]
        arq = os.path.join(pasta, f"{tk}.json")
        guardado = _ler_cache(arq)
        serie = None
        if not yahoo_fora:
            for tentativa in range(3):
                try:
                    serie, meta = _yahoo_adj(f"{tk}.SA")
                    break
                except Exception as e:  # noqa: BLE001
                    msg = str(e)
                    if msg.startswith("429") and tentativa < 2:
                        time.sleep(20 * (tentativa + 1))
                        continue
                    if "não existe" in msg:
                        falhas_seguidas = 0
                    else:
                        falhas_seguidas += 1
                    if i < 5 or falhas_seguidas in (1, 5, FALHAS_SEGUIDAS_MAX):
                        log(f"  {tk}: Yahoo falhou ({msg[:160]})")
                    break
            time.sleep(PAUSA_YAHOO)
        if serie:
            falhas_seguidas = 0
            n_yahoo += 1
            out[tk] = {"serie": serie, "meta": meta, "fonte": "Yahoo"}
            with open(arq, "w", encoding="utf-8") as fh:
                json.dump({"atualizado": hoje.isoformat(), "meta": meta, "serie": serie}, fh, separators=(",", ":"))
        elif guardado and guardado.get("serie"):
            n_cache += 1
            out[tk] = {"serie": guardado["serie"], "meta": guardado.get("meta") or {}, "fonte": "cache " + str(guardado.get("atualizado", ""))[:10]}
        else:
            n_sem += 1
        if falhas_seguidas >= FALHAS_SEGUIDAS_MAX and not yahoo_fora:
            yahoo_fora = True
            avisos.append(f"Yahoo fora do ar após {FALHAS_SEGUIDAS_MAX} falhas seguidas (papel {i + 1} de {len(papeis)}); o restante usa o cache")
        if (i + 1) % 100 == 0:
            log(f"  {i + 1} de {len(papeis)} papéis ({n_yahoo} Yahoo, {n_cache} cache, {n_sem} sem série; {int(time.time() - t0)}s)")
    log(f"  preços: {n_yahoo} do Yahoo, {n_cache} do cache, {n_sem} sem série ({int(time.time() - t0)}s)")
    if n_cache:
        avisos.append(f"ações: {n_cache} papéis com a série da execução anterior (Yahoo indisponível para eles)")
    if n_sem:
        avisos.append(f"ações: {n_sem} papéis sem série de preços (fora do comparador nesta execução)")
    return out


# --------------------------------------------------------------------------- montagem

def _nome_bonito(nomres: str, especi: str, longo: str | None) -> str:
    base = (longo or "").strip()
    if base:
        base = re.sub(r"\s+(S\.?A\.?|SA|LTDA\.?|INC\.?|CORP\.?|PLC|N\.?V\.?)$", "", base, flags=re.I).strip(" -.")
    if not base:
        base = nomres.title().replace("Sa ", "SA ").strip()
    suf = {"ON": "ON", "PN": "PN", "PNA": "PNA", "PNB": "PNB", "PNC": "PNC", "PND": "PND", "UNT": "UNT"}.get(especi, "")
    return (base + (" " + suf if suf else "")).strip()


def carregar_acoes(datas: list[date], hoje: date, offline: str | None, cache: str, avisos: list[str]) -> tuple[list[dict], dict]:
    """Devolve (papéis, info). Cada papel: ticker, nome, nome_longo, tipo (acao|bdr), especi, bm, liq, preco, fonte, q (np.array no calendário)."""
    if offline:
        return _sinteticas(datas), {"pregoes": len(datas), "ultimo_pregao": datas[-1].isoformat(), "papeis_no_arquivo": 11, "fonte": "sintético"}
    papeis, info = universo(hoje, cache, avisos)
    log(f"  COTAHIST: {info['papeis_no_arquivo']} papéis no arquivo, {len(papeis)} com liquidez (último pregão {info['ultimo_pregao']})")
    series = precos(papeis, cache, avisos, hoje)
    out = []
    for p in papeis:
        s = series.get(p["ticker"])
        if not s:
            continue
        q = fx.alinhar(s["serie"], datas)
        # antes da primeira cotação a série fica vazia (alinhar só preenche para a frente)
        if np.isnan(q).all():
            continue
        out.append({**p, "nome_longo": (s["meta"] or {}).get("nome_longo"), "fonte": s["fonte"],
                    "nome": _nome_bonito(p["nome"], p["especi"], (s["meta"] or {}).get("nome_longo")),
                    "bm": "sp500brl" if p["tipo"] == "bdr" else "ibov", "q": q})
    info["fonte"] = "B3 COTAHIST + Yahoo"
    return out, info


def _sinteticas(datas: list[date]) -> list[dict]:
    """Base de teste: papéis fictícios com passeio aleatório, para exercitar o site sem rede."""
    base = [("PETR4", "Petrobras PN", "PN", "acao", 0.18, 0.30, 38.0), ("VALE3", "Vale ON", "ON", "acao", 0.05, 0.28, 60.0),
            ("ITUB4", "Itaú Unibanco PN", "PN", "acao", 0.22, 0.22, 34.0), ("WEGE3", "WEG ON", "ON", "acao", 0.15, 0.26, 45.0),
            ("BBDC4", "Bradesco PN", "PN", "acao", -0.02, 0.27, 14.0), ("TAEE11", "Taesa UNT", "UNT", "acao", 0.12, 0.17, 36.0),
            ("MGLU3", "Magazine Luiza ON", "ON", "acao", -0.30, 0.65, 8.0), ("PRIO3", "Prio ON", "ON", "acao", 0.25, 0.35, 42.0),
            ("AAPL34", "Apple", "DRN", "bdr", 0.20, 0.25, 85.0), ("MSFT34", "Microsoft", "DRN", "bdr", 0.24, 0.24, 110.0),
            ("NVDC34", "NVIDIA", "DRN", "bdr", 0.60, 0.50, 30.0)]
    out = []
    for i, (tk, nome, esp, tipo, drift, vol, p0) in enumerate(base):
        ds = datas if i != 7 else datas[len(datas) // 2:]  # um papel com estreia recente
        serie = fx.sintetico(ds, 100 + i, drift, vol, p0)
        out.append({"ticker": tk, "nome": nome, "nome_longo": nome, "especi": esp, "tipo": tipo, "bm": "sp500brl" if tipo == "bdr" else "ibov",
                    "liq": float(5e8 / (i + 1)), "preco": serie[max(serie)], "ultimo": max(serie), "sessoes": len(ds), "possiveis": len(ds),
                    "estreia": min(serie), "fonte": "sintético", "q": fx.alinhar(serie, datas)})
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
