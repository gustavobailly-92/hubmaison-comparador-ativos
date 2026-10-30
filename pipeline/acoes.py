"""Ações, BDRs e fundos imobiliários negociados na B3, só com fontes oficiais e abertas.

Universo e preços: os arquivos anuais de cotações históricas da B3 (COTAHIST), mercado à vista: ações em lote padrão
(CODBDI 02: ON, PN, UNT), BDRs (espécies DRN, DR1, DR2, DR3, DRE; CODBDI 34/35/36 desde out/2022, 02 antes) e cotas de fundos imobiliários (CODBDI 12). Entram os papéis com negócios em
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
import unicodedata
import zipfile
from datetime import date

import numpy as np

import fontes_extras as fx
import fundamentos as fd

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
CODBDI_BDR = ("34", "35", "36")   # no COTAHIST os BDRs vêm nestes códigos desde outubro de 2022 (antes, em lote padrão 02): 34 não patrocinado, 35 patrocinado, 36 ETF
CASH_PAGINA = 100       # proventos em dinheiro por página na API da B3 (acima de ~120 a API devolve vazio)
EVENTOS_VERSAO = 4      # formato do cache de eventos; muda quando a leitura da API muda (invalida caches antigos); 4 = setor/subsetor/segmento da B3
FII_VERSAO = 2          # cache dos FIIs na B3; 2 = segmento de atuação
# a API da B3 troca as vírgulas da classificação setorial por ponto ("Petróleo. Gás e Biocombustíveis"); estas abreviações
# terminam em ponto de verdade e não podem virar vírgula
_ABREV_B3 = {"máq", "maq", "equip", "soc", "serv", "méd", "med", "hospit", "mat", "transp", "ind", "com", "prod", "const", "adm", "part", "distrib", "s", "a"}
# segmento dos FIIs: nomes da B3 e do informe da CVM traduzidos para os rótulos do site
SEG_FII = {"titulos e val. mob.": "Recebíveis (papel)", "titulos e valores mobiliarios": "Recebíveis (papel)", "lajes corporativas": "Lajes corporativas",
           "escritorios": "Lajes corporativas", "logistica": "Logística", "shoppings": "Shoppings", "shopping": "Shoppings", "hibrido": "Híbrido",
           "fundo de fundos": "Fundo de fundos", "residencial": "Residencial", "hotel": "Hotel", "hospital": "Hospital", "varejo": "Renda urbana",
           "educacional": "Educacional", "agencias de bancos": "Agências bancárias", "fundo de desenvolvimento": "Desenvolvimento", "desenvolvimento": "Desenvolvimento",
           "agronegocio": "Agronegócio", "fiagro": "Agronegócio", "infraestrutura": "Infraestrutura"}
# pistas no nome do fundo quando a CVM classifica como "Multicategoria" ou "Outros" (ordem importa: a primeira que casar vale)
_PISTAS_FII = [(r"\b(CRI|RECEB|CREDITO|CRÉDITO|HIGH YIELD|HIGH GRADE|PAPEL|CDI\b|IPCA\b|JURO)", "Recebíveis (papel)"), (r"\b(FOF|FUNDO DE FUNDOS|FDO DE FDOS|FDO DE FUNDOS|COTAS DE)", "Fundo de fundos"),
               (r"\b(FIAGRO|AGRO|AGRIC)", "Agronegócio"), (r"\bLOG", "Logística"), (r"\b(SHOPPING|MALL)", "Shoppings"), (r"RENDA URBANA|VAREJO", "Renda urbana"),
               (r"RESIDENCIAL|HABITA|MORADIA", "Residencial"), (r"DESENV", "Desenvolvimento"), (r"HOTE", "Hotel"), (r"HOSPITAL|SAUDE|SAÚDE", "Hospital"),
               (r"CORPORAT|OFFICE|LAJE|ESCRIT|TORRE|EDIF", "Lajes corporativas"), (r"INFRA", "Infraestrutura"), (r"EDUCA", "Educacional"), (r"HIBRID|HÍBRID|MULTI", "Híbrido")]


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()


def _classificacao_b3(txt: str | None) -> tuple[str | None, str | None, str | None]:
    """"Setor / Subsetor / Segmento" da API de empresas da B3, com as vírgulas restauradas."""
    if not txt:
        return None, None, None
    partes = []
    for parte in str(txt).split("/"):
        toks = parte.split(". ")
        out = toks[0]
        for t in toks[1:]:
            ult = out.rstrip().split(" ")[-1].lower()
            out = out.rstrip() + (". " if ult in _ABREV_B3 else ", ") + t.lstrip()
        partes.append(out.strip() or None)
    while len(partes) < 3:
        partes.append(None)
    return partes[0], partes[1], partes[2]


TIJOLO = {"Logística", "Shoppings", "Lajes corporativas", "Residencial", "Hospital", "Hotel", "Renda urbana", "Educacional", "Agências bancárias"}


def _seg_declarado(seg: str | None) -> str | None:
    """Segmento declarado (B3 ou CVM) traduzido; None para as categorias genéricas (Multicategoria, Outros)."""
    if not seg:
        return None
    chave = _sem_acento(seg).strip().lower()
    if chave in SEG_FII:
        return SEG_FII[chave]
    return None if chave in ("multicategoria", "outros", "outro", "") else seg.strip()


def _segmento_fii(seg_b3: str | None, seg_cvm: str | None, nome: str | None, comp: dict | None = None) -> tuple[str | None, str]:
    """Segmento do FII e a fonte. A carteira do informe mensal (ativo e passivo) decide a natureza: recebíveis (CRI, LCI, LIG),
    fundo de fundos (cotas de FII), tijolo (imóveis e sociedades imobiliárias; desenvolvimento quando em construção ou à venda)
    ou híbrido; no tijolo, o tipo de imóvel vem do segmento declarado (B3/CVM) ou do nome. Sem carteira, vale o declarado e o nome."""
    nm = _sem_acento(nome or "").upper()
    if re.search(r"\b(FIAGRO|AGRO|AGRIC)", nm):
        return "Agronegócio", "nome"
    declarado = _seg_declarado(seg_b3) or _seg_declarado(seg_cvm)
    fonte_decl = "b3" if _seg_declarado(seg_b3) else "cvm"
    pista = next((rotulo for rx, rotulo in _PISTAS_FII if re.search(rx, nm)), None)
    ti = (comp or {}).get("ti") or 0.0
    if ti > 0:
        papel, fof, tijolo, desenv = (comp.get(k, 0.0) / ti for k in ("papel", "fof", "tijolo", "desenv"))
        if papel >= 0.5:
            return "Recebíveis (papel)", "carteira"
        if fof >= 0.5:
            return "Fundo de fundos", "carteira"
        if tijolo >= 0.5:
            if desenv >= 0.5:
                return "Desenvolvimento", "carteira"
            if declarado in TIJOLO:
                return declarado, fonte_decl
            if pista in TIJOLO:
                return pista, "nome"
            return "Híbrido", "carteira"
        if papel + fof + tijolo >= 0.5:
            return "Híbrido", "carteira"
        return declarado or pista or "Outros", fonte_decl if declarado else ("nome" if pista else "carteira")
    if declarado:
        return declarado, fonte_decl
    if pista:
        return pista, "nome"
    return ("Híbrido", "cvm") if seg_cvm else (None, "")
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
                elif esp in ESPECIES_BDR and (codbdi in CODBDI_BDR or codbdi == "02"):
                    tipo = "bdr"   # desde out/2022: 34 = BDR não patrocinado, 35 = patrocinado (DR1/DR2/DR3), 36 = BDR de ETF; antes vinham em lote padrão (02)
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
    # código CVM (liga a empresa às demonstrações ITR/DFP) e número de ações (valor de mercado)
    try:
        cvm = int(re.sub(r"\D", "", str(sup.get("codeCVM") or ""))) or None
    except ValueError:
        cvm = None
    acoes = {k: _num_br(sup.get(j)) for k, j in (("on", "numberCommonShares"), ("pn", "numberPreferredShares"), ("total", "totalNumberShares"))}
    # classificação setorial da B3 (setor / subsetor / segmento) pelo detalhe da companhia
    setor = subsetor = seg = None
    if cvm:
        try:
            time.sleep(PAUSA_B3)
            det = _b3_json(B3_EMPRESAS, "GetDetail", {"codeCVM": str(cvm), "language": "pt-br"})
            setor, subsetor, seg = _classificacao_b3((det or {}).get("industryClassification") if isinstance(det, dict) else None)
        except Exception:  # noqa: BLE001
            pass
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
    out = {"versao": EVENTOS_VERSAO, "atualizado": hoje.isoformat(), "nome": nome, "stock": stock, "cash": cash, "cvm": cvm, "acoes": acoes,
           "setor": setor, "subsetor": subsetor, "seg": seg}
    with open(arq, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    return out


def eventos_fii(codigo: str, cache_dir: str, hoje: date) -> dict | None:
    """Desdobramentos e grupamentos de um FII (código de 4 letras) pela API de fundos listados da B3. Cache de 7 dias."""
    arq = os.path.join(cache_dir, f"eventos_fii_{codigo}.json")
    g = _ler_json(arq)
    if g and g.get("versao") == FII_VERSAO and (date.today() - date.fromisoformat(g.get("atualizado", "2000-01-01"))).days < 7:
        return g
    try:
        sup = _b3_json(B3_FUNDOS, "GetListedSupplementFunds", {"cnpj": "", "identifierFund": codigo, "typeFund": 7})
    except Exception as e:  # noqa: BLE001
        return g if g else {"erro": str(e)[:200]}
    out = {"versao": FII_VERSAO, "atualizado": hoje.isoformat(), "stock": _eventos_stock((sup or {}).get("stockDividends") if isinstance(sup, dict) else None)}
    out["seg"], out["seg_api"] = _segmento_fii_b3(codigo)
    with open(arq, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    return out


B3_FUNDOS_NOVO = "https://sistemaswebb3-listados.b3.com.br/fundsListedProxy/Search/"
_SEG_API_OK: dict[str, int] = {}


def _achar_chave(obj, chaves: tuple[str, ...]):
    """Procura, em qualquer nível de um JSON, a primeira chave da lista com valor textual."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in chaves and isinstance(v, str) and v.strip():
                return v.strip()
        for v in obj.values():
            r = _achar_chave(v, chaves)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _achar_chave(v, chaves)
            if r:
                return r
    return None


def _segmento_fii_b3(codigo: str) -> tuple[str | None, str]:
    """Segmento de atuação do FII pelo detalhe do fundo na B3: tenta a API antiga (fundsCall) e a nova (fundsListedProxy);
    devolve (segmento, api que respondeu)."""
    candidatos = (
        ("antiga", B3_FUNDOS, "GetDetailFundSIG", {"typeFund": 7, "identifierFund": codigo, "language": "pt-br"}),
        ("nova", B3_FUNDOS_NOVO, "GetDetailFund", {"language": "pt-br", "typeFund": "FII", "identifierFund": codigo}),
    )
    for nome, base, metodo, payload in candidatos:
        if _SEG_API_OK.get(nome, 0) <= -5:   # cinco falhas seguidas: a API não existe mais, não insiste
            continue
        try:
            time.sleep(PAUSA_B3)
            det = _b3_json(base, metodo, payload, tentativas=1)
            seg = _achar_chave(det, ("segment", "segmento", "classification", "classificacao"))
            if seg:
                _SEG_API_OK[nome] = max(1, _SEG_API_OK.get(nome, 0) + 1)
                return seg, nome
            _SEG_API_OK[nome] = min(0, _SEG_API_OK.get(nome, 0)) - 1
        except Exception:  # noqa: BLE001
            _SEG_API_OK[nome] = min(0, _SEG_API_OK.get(nome, 0)) - 1
    return None, ""


_COLS_PAPEL = ("CRI", "CRI_CRA", "Letras_Hipotecarias", "LCI", "LCI_LCA", "LIG")
_COLS_TIJOLO = ("Direitos_Bens_Imoveis", "Acoes_Sociedades_Atividades_FII", "Cotas_Sociedades_Atividades_FII")
_COLS_DESENV = ("Terrenos", "Imoveis_Renda_Construcao", "Imoveis_Venda_Acabados", "Imoveis_Venda_Construcao")


def _ler_carteira_fii(z: zipfile.ZipFile, nome: str, seg_cvm: dict[str, dict]) -> None:
    """Informe mensal, ativo e passivo: composição da carteira (recebíveis, cotas de FII, imóveis e imóveis em desenvolvimento
    sobre o total investido) do mês mais recente de cada fundo, em seg_cvm[cnpj]["comp"]."""
    with z.open(nome) as fh:
        txt = io.TextIOWrapper(fh, encoding="latin-1", newline=None)
        hdr = [h.strip() for h in next(txt).rstrip("\r\n").split(";")]
        ic = next((hdr.index(h) for h in ("CNPJ_Fundo_Classe", "CNPJ_Fundo") if h in hdr), None)
        if ic is None or "Total_Investido" not in hdr or "Data_Referencia" not in hdr:
            return
        idt, iti = hdr.index("Data_Referencia"), hdr.index("Total_Investido")
        grupos = {k: [hdr.index(c) for c in cols if c in hdr] for k, cols in (("papel", _COLS_PAPEL), ("fof", ("FII",)), ("tijolo", _COLS_TIJOLO), ("desenv", _COLS_DESENV))}

        def num(c, i):
            try:
                return float(c[i]) if i < len(c) and c[i].strip() else 0.0
            except ValueError:
                return 0.0
        for linha in txt:
            c = linha.rstrip("\r\n").split(";")
            if len(c) <= max(ic, idt, iti):
                continue
            cnpj = re.sub(r"\D", "", c[ic])
            ref = c[idt][:7]
            atual = seg_cvm.setdefault(cnpj, {})
            if ref < atual.get("ref_comp", ""):
                continue
            comp = {"ti": num(c, iti)}
            for k, idx in grupos.items():
                comp[k] = sum(num(c, i) for i in idx)
            atual["ref_comp"] = ref
            atual["comp"] = comp


def rendimentos_fii(anos: list[int], hoje: date, cache: str, avisos: list[str]) -> tuple[dict[str, str], dict[str, dict[str, float]], dict[str, dict[str, float]], dict[str, dict]]:
    """Informe mensal de FII da CVM: (ISIN -> CNPJ), (CNPJ -> {AAAA-MM: dividend yield do mês, fração}),
    (CNPJ -> {AAAA-MM: valor patrimonial da cota}, pelo campo do informe ou por patrimônio líquido ÷ cotas emitidas) e
    (CNPJ -> segmento de atuação e nome do fundo, do informe mais recente)."""
    isin_cnpj: dict[str, str] = {}
    dy: dict[str, dict[str, float]] = {}
    vp: dict[str, dict[str, float]] = {}
    seg_cvm: dict[str, dict] = {}   # CNPJ -> {"seg": Segmento_Atuacao, "nome": nome do fundo} do informe mais recente
    col_vp_usada = None
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
                if "ativo_passivo" in low:
                    _ler_carteira_fii(z, n, seg_cvm)
                    continue
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
                        iseg = hdr.index("Segmento_Atuacao") if "Segmento_Atuacao" in hdr else None
                        inm = next((hdr.index(h) for h in ("Nome_Fundo_Classe", "Nome_Fundo") if h in hdr), None)
                        idt = hdr.index("Data_Referencia") if "Data_Referencia" in hdr else None
                        for linha in txt:
                            c = linha.rstrip("\r\n").split(";")
                            if len(c) > max(ic, ii) and c[ii].strip():
                                cnpj = re.sub(r"\D", "", c[ic])
                                isin_cnpj[c[ii].strip()] = cnpj
                                if iseg is not None and len(c) > iseg:
                                    ref = c[idt][:7] if idt is not None and len(c) > idt else ""
                                    if ref >= seg_cvm.get(cnpj, {}).get("ref", ""):
                                        # update, não atribuição: a carteira (ativo_passivo, lida antes no mesmo ZIP) fica no mesmo dicionário
                                        seg_cvm.setdefault(cnpj, {}).update({"ref": ref, "seg": c[iseg].strip(), "nome": c[inm].strip() if inm is not None and len(c) > inm else ""})
                    else:
                        if "Percentual_Dividend_Yield_Mes" not in hdr or "Data_Referencia" not in hdr:
                            continue
                        idt, idy = hdr.index("Data_Referencia"), hdr.index("Percentual_Dividend_Yield_Mes")
                        # valor patrimonial da cota: o campo próprio do informe ou patrimônio líquido ÷ cotas emitidas
                        ivp = next((hdr.index(h) for h in hdr if re.match(r"valor_patrim\w*_cota", h, re.I)), None)
                        ipl = next((hdr.index(h) for h in hdr if re.match(r"patrimonio_liquido$", h, re.I)), None)
                        ict = next((hdr.index(h) for h in hdr if re.match(r"cotas_emitidas$", h, re.I)), None)
                        if col_vp_usada is None:
                            col_vp_usada = hdr[ivp] if ivp is not None else (f"{hdr[ipl]}/{hdr[ict]}" if ipl is not None and ict is not None else "nenhuma")
                        for linha in txt:
                            c = linha.rstrip("\r\n").split(";")
                            if len(c) <= max(ic, idt, idy):
                                continue
                            cnpj = re.sub(r"\D", "", c[ic])
                            mes = c[idt][:7]
                            try:
                                v = float(c[idy]) if c[idy].strip() else None
                            except ValueError:
                                v = None
                            # a versão mais recente do informe prevalece (as linhas vêm em ordem; a última ganha)
                            if v is not None and 0 <= v <= 0.2:
                                dy.setdefault(cnpj, {})[mes] = v
                            pv = None
                            try:
                                if ivp is not None and len(c) > ivp and c[ivp].strip():
                                    pv = float(c[ivp])
                                elif ipl is not None and ict is not None and len(c) > max(ipl, ict) and c[ipl].strip() and c[ict].strip():
                                    n_cotas = float(c[ict])
                                    pv = float(c[ipl]) / n_cotas if n_cotas > 0 else None
                            except ValueError:
                                pv = None
                            if pv is not None and pv > 0:
                                vp.setdefault(cnpj, {})[mes] = pv
    if col_vp_usada is not None:
        log(f"  FII: valor patrimonial da cota pela coluna {col_vp_usada}")
    return isin_cnpj, dy, vp, seg_cvm


# --------------------------------------------------------------------------- ajustes

def _detectar_splits(serie: dict[str, float]) -> list[tuple[str, float]]:
    """Saltos de preço de razão inteira entre pregões consecutivos (desdobramento ou grupamento), para papéis sem evento
    oficial (BDRs mudam a razão com qualquer inteiro: o MSFT34 fez 24:1 em 2020). Aceita qualquer razão inteira de 2 a 200,
    com tolerância de 4%. Devolve [(último dia com o preço antigo, multiplicador de quantidade)]."""
    dias = sorted(serie)
    out = []
    for a, b in zip(dias, dias[1:]):
        p0, p1 = serie[a], serie[b]
        if p0 <= 0 or p1 <= 0:
            continue
        r = p0 / p1
        if r > 1.7:
            n = round(r)
            if 2 <= n <= 200 and abs(r / n - 1) < 0.04:
                out.append((a, float(n)))
        elif r < 1 / 1.7:
            n = round(1 / r)
            if 2 <= n <= 200 and abs(1 / (r * n) - 1) < 0.04:
                out.append((a, 1.0 / n))
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
        out = _sinteticas(datas)
        _fundamentos_sinteticos(out, hoje)
        return out, {"pregoes": len(datas), "ultimo_pregao": datas[-1].isoformat(), "papeis_no_arquivo": 13, "fonte": "sintético"}
    pasta = os.path.join(cache, "acoes")
    os.makedirs(pasta, exist_ok=True)
    papeis, info, atual = universo(hoje, cache, avisos)
    log(f"  COTAHIST: {info['papeis_no_arquivo']} papéis no arquivo, {len(papeis)} com liquidez (último pregão {info['ultimo_pregao']})")
    anos = list(range(datas[0].year, hoje.year + 1))
    series = historico(papeis, anos, hoje, cache, atual, avisos)
    # rendimentos dos FIIs (CVM) e eventos societários (B3)
    isin_cnpj: dict[str, str] = {}
    dy_fii: dict[str, dict[str, float]] = {}
    vp_fii: dict[str, dict[str, float]] = {}
    seg_cvm: dict[str, dict] = {}
    if any(p["tipo"] == "fii" for p in papeis):
        try:
            isin_cnpj, dy_fii, vp_fii, seg_cvm = rendimentos_fii(anos, hoje, os.path.join(cache, "fii"), avisos)
            log(f"  FII: {len(isin_cnpj)} ISINs e {len(dy_fii)} fundos com dividend yield mensal na CVM")
        except Exception as e:  # noqa: BLE001
            avisos.append(f"rendimentos dos FIIs (CVM): {e}")
    t0 = time.time()
    emissores: dict[str, dict | None] = {}
    fiis: dict[str, dict | None] = {}
    out = []
    n_ok = n_sem_evento = 0
    seg_fontes: dict[str, int] = {}
    for k, p in enumerate(papeis):
        serie = series.get(p["ticker"]) or {}
        if len(serie) < SESSOES_MIN:
            continue
        splits: list[tuple[str, float]] = []
        proventos: list[tuple[str, float, float | None]] = []
        dy = None
        ajuste = "completo"
        cod = p["ticker"][:4]
        setor = subsetor = seg = None
        if p["tipo"] == "acao":
            if cod not in emissores:
                time.sleep(PAUSA_B3)
                emissores[cod] = eventos_empresa(cod, pasta, hoje)
            ev = emissores[cod] or {}
            setor, subsetor, seg = ev.get("setor"), ev.get("subsetor"), ev.get("seg")
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
            p["_vp"] = vp_fii.get(cnpj) if cnpj else None
            sc = seg_cvm.get(cnpj) if cnpj else None
            setor, fonte_seg = _segmento_fii(ev.get("seg"), (sc or {}).get("seg"), (sc or {}).get("nome") or p["nome"], (sc or {}).get("comp"))
            if setor:
                seg_fontes[fonte_seg] = seg_fontes.get(fonte_seg, 0) + 1
        else:  # BDR: sem fonte aberta de proventos
            splits = _detectar_splits(serie)
            ajuste = "sem proventos"
        qp_d, q_d, inf = ajustar(serie, splits, proventos, dy)
        q = fx.alinhar(q_d, datas)
        if np.isnan(q).all():
            continue
        out.append({**{k2: v for k2, v in p.items() if k2 not in ("isin", "_vp")}, "nome_longo": None, "fonte": "B3 COTAHIST",
                    "nome": _nome_bonito(p["nome"], p["especi"], None), "ajuste": ajuste, "estreia": min(serie),
                    "n_splits": inf.get("splits", 0), "n_proventos": inf.get("proventos", 0),
                    "bm": "sp500brl" if p["tipo"] == "bdr" else "ifix" if p["tipo"] == "fii" else "ibov",
                    "setor": setor, "subsetor": subsetor, "seg": seg,
                    "q": q, "qp": fx.alinhar(qp_d, datas), "fund": _fund_fii(dy, p.get("_vp"), p["preco"], hoje) if p["tipo"] == "fii" else {}})
        n_ok += 1
        if (k + 1) % 100 == 0:
            log(f"  {k + 1} de {len(papeis)} papéis ({int(time.time() - t0)}s)")
    log(f"  séries montadas: {n_ok} papéis, {len(emissores)} emissores e {len(fiis)} FIIs consultados na B3 ({int(time.time() - t0)}s); {n_sem_evento} sem proventos")
    n_setor = sum(1 for p in out if p["tipo"] == "acao" and p.get("setor"))
    log(f"  setores: {n_setor} de {sum(1 for p in out if p['tipo'] == 'acao')} ações com classificação da B3; FIIs por fonte: {seg_fontes or 'nenhuma'}"
        + (f"; API de segmento da B3: {_SEG_API_OK}" if _SEG_API_OK else ""))
    if n_sem_evento:
        avisos.append(f"ações: {n_sem_evento} papéis sem proventos na série (BDRs, ou sem resposta da B3/CVM)")
    # fundamentos das companhias (ITR/DFP da CVM) e indicadores de valuation por papel
    try:
        aplicar_fundamentos(out, emissores, hoje, cache, avisos)
    except Exception as e:  # noqa: BLE001
        avisos.append(f"fundamentos (CVM): {e}")
    info["fonte"] = "B3 COTAHIST + eventos B3 + CVM (FII, ITR/DFP)"
    return out, info


def _fund_fii(dy: dict | None, vp: dict | None, preco: float | None, hoje: date) -> dict:
    """FII: dividend yield de 12 meses (soma dos 12 últimos rendimentos mensais do informe) e P/VP (cotação ÷ valor
    patrimonial da cota do último informe)."""
    out: dict = {}
    if dy:
        meses = sorted(dy)[-12:]
        if len(meses) >= 6:
            out["dy12"] = round(sum(dy[m] for m in meses), 4)
            out["dy12_meses"] = len(meses)
    if vp and preco:
        m = max(vp)
        if vp[m] > 0:
            out["pvp"] = round(preco / vp[m], 2)
            out["vp"] = round(vp[m], 2)
            out["dt_fund"] = m
    return out


def aplicar_fundamentos(papeis: list[dict], emissores: dict[str, dict | None], hoje: date, cache: str, avisos: list[str], offline: bool = False) -> None:
    """Ações: P/VPA, EV/EBITDA e crescimentos de PL, EBITDA e receita (12/24/36 m) pelas demonstrações da CVM.
    Valor de mercado = ações ON × preço da ON + ações PN × preço da PN (número de ações pela B3); quando só uma classe
    é negociada, o total de ações vale pelo preço dela. BDRs e units sem ON/PN negociadas ficam sem indicadores."""
    por_cod: dict[str, list[dict]] = {}
    for p in papeis:
        if p["tipo"] == "acao":
            por_cod.setdefault(p["ticker"][:4], []).append(p)
    cvms = {}
    for cod in por_cod:
        ev = emissores.get(cod) or {}
        if ev.get("cvm"):
            cvms[cod] = int(ev["cvm"])
    if not cvms:
        return
    fund = fd.sintetico(set(cvms.values()), hoje) if offline else fd.carregar(set(cvms.values()), hoje, cache, avisos)
    n = 0
    for cod, lista in por_cod.items():
        cvm = cvms.get(cod)
        f = fund.get(cvm) if cvm else None
        if not f:
            continue
        ev = emissores.get(cod) or {}
        ac = ev.get("acoes") or {}
        p_on = next((p["preco"] for p in lista if p["especi"] == "ON"), None)
        p_pn = next((p["preco"] for p in lista if p["especi"].startswith("PN")), None)
        n_on, n_pn, n_tot = ac.get("on") or 0.0, ac.get("pn") or 0.0, ac.get("total") or 0.0
        mcap = None
        if p_on or p_pn:
            if n_on or n_pn:
                mcap = n_on * (p_on or p_pn) + n_pn * (p_pn or p_on)
            elif n_tot:
                mcap = n_tot * (p_on or p_pn)
        ind = fd.indicadores(f, mcap)
        if mcap:
            ind["mcap"] = round(mcap)
        for p in lista:
            p["fund"] = ind
            n += 1
    log(f"  fundamentos: {n} papéis com indicadores ({len(fund)} companhias)")


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
        setores = {"PETR4": ("Petróleo, Gás e Biocombustíveis", "Petróleo, Gás e Biocombustíveis", "Exploração, Refino e Distribuição"),
                   "VALE3": ("Materiais Básicos", "Mineração", "Minerais Metálicos"), "ITUB4": ("Financeiro", "Intermediários Financeiros", "Bancos"),
                   "WEGE3": ("Bens Industriais", "Máquinas e Equipamentos", "Motores, Compressores e Outros"), "BBDC4": ("Financeiro", "Intermediários Financeiros", "Bancos"),
                   "TAEE11": ("Utilidade Pública", "Energia Elétrica", "Energia Elétrica"), "MGLU3": ("Consumo Cíclico", "Comércio", "Eletrodomésticos"),
                   "PRIO3": ("Petróleo, Gás e Biocombustíveis", "Petróleo, Gás e Biocombustíveis", "Exploração, Refino e Distribuição"),
                   "HGLG11": ("Logística", None, None), "KNCR11": ("Recebíveis (papel)", None, None)}
        st = setores.get(tk, (None, None, None))
        out.append({"ticker": tk, "nome": nome, "nome_longo": nome, "especi": esp, "tipo": tipo, "bm": "sp500brl" if tipo == "bdr" else "ifix" if tipo == "fii" else "ibov",
                    "setor": st[0], "subsetor": st[1], "seg": st[2],
                    "liq": float(5e8 / (i + 1)), "preco": serie[max(serie)], "ultimo": max(serie), "sessoes": len(ds), "possiveis": len(ds),
                    "estreia": min(serie), "fonte": "sintético", "ajuste": "completo" if tipo != "bdr" else "sem proventos", "n_splits": 0, "n_proventos": 0,
                    "q": fx.alinhar(serie, datas), "qp": fx.alinhar(precos, datas)})
    return out


def _fundamentos_sinteticos(papeis: list[dict], hoje: date) -> None:
    """Base de teste: indicadores fictícios pelo mesmo caminho da base real (emissores sintéticos + fundamentos.sintetico)."""
    emissores: dict[str, dict] = {}
    for k, p in enumerate(papeis):
        if p["tipo"] == "acao":
            cod = p["ticker"][:4]
            n = 4.0e7 * (1 + k % 4)   # ~R$ 2 bi a 8 bi de valor de mercado: P/VPA entre 1 e 4 com os PLs sintéticos
            emissores.setdefault(cod, {"cvm": 9000 + len(emissores), "acoes": {"on": n, "pn": 0.7 * n if p["especi"].startswith("PN") else 0.0, "total": n}})
        elif p["tipo"] == "fii":
            m0 = date(hoje.year, hoje.month, 1)
            meses = []
            for i in range(12):
                y, m = divmod(m0.month - 1 - i, 12)
                meses.append(f"{m0.year + y:04d}-{m + 1:02d}")
            dy = {m: 0.0085 + 0.0005 * (i % 3) for i, m in enumerate(meses)}
            vp = {meses[0]: p["preco"] * (0.92 if k % 2 else 1.06)}
            p["fund"] = _fund_fii(dy, vp, p["preco"], hoje)
    # units sintéticas (TAEE11) não têm ON/PN negociadas: ficam com valor de mercado pelo total de ações
    for cod, ev in emissores.items():
        if cod == "TAEE":
            ev["acoes"] = {"on": 0.0, "pn": 0.0, "total": 1.0e9}
    aplicar_fundamentos(papeis, emissores, hoje, "", [], offline=True)


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
