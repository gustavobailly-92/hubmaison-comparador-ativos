#!/usr/bin/env python3
"""
Comparador de Fundos · Maison Hub
Pipeline de dados: dados abertos da CVM (informe diário + cadastro) e CDI do Banco Central (SGS 12).

Saída (pasta --out, padrão dist/data):
  meta.json          calendário de dias úteis, índice do CDI, semanas, data de referência
  index.json         índice de busca (um registro compacto por fundo)
  fundos/<cnpj>.json série de cotas, patrimônio e cotistas + métricas por janela
  status.json        contagens e avisos da execução

Uso:
  python build_data.py                      # baixa tudo da CVM/BCB e gera dist/data
  python build_data.py --meses 50           # quantos meses de informe diário processar
  python build_data.py --offline caminho/   # usa arquivos locais (testes): cad_fi.csv, cdi.json, inf_diario_fi_AAAAMM.zip
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sys
import time
import zipfile
import unicodedata
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fontes_extras as fx  # noqa: E402

CVM_INF = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/"
CVM_CAD = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv"
CVM_REG = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
BCB_CDI = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"

JANELAS = (12, 24, 36, 48)          # meses
MIN_COTISTAS = 10                   # fundos com menos cotistas ficam fora da busca
# fundos de previdência (FIEs dos planos PGBL/VGBL) têm a seguradora como único cotista: ficam fora da regra acima
RE_PREVIDENCIA = re.compile(r"PREV|\bFIE\b|VGBL|PGBL|APOSENTADORIA", re.I)


def eh_previdencia(nome: str) -> bool:
    return bool(nome) and bool(RE_PREVIDENCIA.search(nome))
DIAS_TOLERANCIA = 7                 # dias úteis sem informe até considerar o fundo "parado"

# --------------------------------------------------------------------------- utilidades

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def norm_col(c: str) -> str:
    c = unicodedata.normalize("NFKD", str(c)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", c.lower())


def find_col(cols, *candidatos) -> str | None:
    """Encontra a coluna pelo nome normalizado (aceita variantes antigas e da RCVM 175)."""
    normed = {norm_col(c): c for c in cols}
    for cand in candidatos:
        k = norm_col(cand)
        if k in normed:
            return normed[k]
    return None


def cnpj_digits(v) -> str:
    return re.sub(r"\D", "", str(v))


def encoding_de(raw: bytes) -> str:
    """Os arquivos da CVM são ISO-8859-1; se um dia virarem UTF-8, o decode estrito detecta."""
    try:
        raw.decode("utf-8")
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "latin-1"


def http_get(url: str, tentativas: int = 4, timeout: int = 180) -> bytes:
    import urllib.request
    ultimo = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MaisonHub-Comparador/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            ultimo = e
            espera = 5 * (i + 1)
            log(f"  falha ao baixar {url} ({e}); nova tentativa em {espera}s")
            time.sleep(espera)
    raise RuntimeError(f"não consegui baixar {url}: {ultimo}")


SIGLAS = {
    "FI", "FIC", "FICFI", "FIM", "FIA", "FIRF", "FIF", "FII", "FIDC", "FIP", "FMP", "FGTS", "ETF",
    "CDI", "IPCA", "IBOV", "IBOVESPA", "IMA", "IMA-B", "IRF-M", "SELIC", "LP", "CP", "RF", "MM",
    "XP", "BTG", "BB", "CEF", "S/A", "S.A.", "SA", "LTDA", "DTVM", "CCTVM", "CTVM", "CVM", "ANBIMA",
    "ESG", "IE", "BDR", "FOF", "USD", "BRL", "EUA", "II", "III", "IV", "VI", "VII", "VIII", "IX",
    "XI", "XII", "PGBL", "VGBL", "PREV", "RPPS", "EFPC", "RV", "CRI", "CRA", "LCI", "LCA", "DI",
    "NTN", "NTN-B", "LFT", "LTN", "TR", "IGP-M", "IGPM", "INPC", "JGP", "SPX", "ARX", "AZ", "SFI",
    "FIE", "FIQ", "FIRF", "FIDS", "ICVM", "RCVM", "IBX", "IDIV", "SMLL", "S&P", "MSCI", "IPO", "ETFS",
}
# palavras curtas que não são siglas (ficam em minúsculas ou com inicial maiúscula)
CURTAS = {
    "DE", "DA", "DO", "DAS", "DOS", "E", "EM", "A", "O", "AS", "OS", "COM", "PARA", "POR", "NO", "NA",
    "NOS", "NAS", "UM", "UMA", "AO", "AOS", "SO", "OU", "SE", "ATE", "SUL", "RIO", "SAO", "MAR", "SER",
    "LUZ", "BEM", "MAIS", "OURO", "OF", "AND", "THE", "FOR", "ONE", "TWO", "NEW", "TOP", "CAP", "PRO",
    "MAX", "PLUS", "SIM", "NAO", "VIA", "SOL", "PAZ", "REI", "LUA", "EGO", "ART", "ERA", "FIX", "KEY",
    "EQ", "AI", "GO", "MY", "BOX", "HUB", "LAB", "NET", "ONE", "SKY", "ZEN", "ACE", "BIG", "LOW", "CO",
}
MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "com", "para", "por", "no", "na", "nos", "nas", "of", "and", "the"}


def titulo(nome: str) -> str:
    """Deixa o nome legal legível: caixa alta vira Título, siglas ficam em caixa alta."""
    out = []
    for i, tok in enumerate(re.split(r"\s+", str(nome).strip())):
        if not tok:
            continue
        up = tok.upper()
        base = re.sub(r"[^A-Z0-9/.&\-]", "", up)
        if tok.lower() in MINUSCULAS and i > 0:
            out.append(tok.lower())
        elif base in SIGLAS:
            out.append(up)
        elif len(base) <= 3 and base.isalpha() and base not in CURTAS:
            out.append(up)
        elif re.match(r"^[A-Z]{1,4}[0-9]+[A-Z]*$|^[0-9]+[A-Z]{1,3}$", base):
            out.append(up)
        else:
            out.append(tok[:1].upper() + tok[1:].lower())
    return " ".join(out)


def r6(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), 6)


def rn(x, n):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


# --------------------------------------------------------------------------- cadastro

def carregar_cadastro(offline: str | None, cache: str) -> dict:
    """Retorna dict cnpj(dígitos) -> dados cadastrais, juntando cad_fi.csv e registro_fundo_classe.zip."""
    if offline:
        raw = open(os.path.join(offline, "cad_fi.csv"), "rb").read()
    else:
        raw = http_get(CVM_CAD)
        open(os.path.join(cache, "cad_fi.csv"), "wb").write(raw)
    df = pd.read_csv(io.BytesIO(raw), sep=";", encoding=encoding_de(raw[:2_000_000]), dtype=str, low_memory=False)
    cols = df.columns
    c_cnpj = find_col(cols, "CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO", "CNPJ_Classe", "CNPJ_Fundo")
    c_nome = find_col(cols, "DENOM_SOCIAL", "Denominacao_Social")
    c_sit = find_col(cols, "SIT", "Situacao")
    c_classe = find_col(cols, "CLASSE", "Classificacao")
    c_excl = find_col(cols, "FUNDO_EXCLUSIVO", "Exclusivo")
    c_cotas = find_col(cols, "FUNDO_COTAS", "Fundo_Cotas")
    c_gestor = find_col(cols, "GESTOR", "Gestor")
    c_admin = find_col(cols, "ADMIN", "Administrador")
    c_anbima = find_col(cols, "CLASSE_ANBIMA", "Classificacao_Anbima")
    c_txadm = find_col(cols, "TAXA_ADM", "Taxa_Administracao")
    c_txperf = find_col(cols, "TAXA_PERFM", "Taxa_Performance")
    c_publico = find_col(cols, "PUBLICO_ALVO", "Publico_Alvo")
    c_ini = find_col(cols, "DT_INI_ATIV", "Data_Inicio_Atividade", "DT_INI_CLASSE")
    c_condom = find_col(cols, "CONDOM", "Forma_Condominio")
    c_tp = find_col(cols, "TP_FUNDO_CLASSE", "TP_FUNDO", "Tipo_Fundo", "Tipo_Classe")
    if not c_cnpj or not c_nome:
        raise RuntimeError(f"cad_fi.csv sem colunas esperadas: {list(cols)[:12]}")
    log(f"cadastro: {len(df)} linhas; colunas cnpj={c_cnpj} nome={c_nome} sit={c_sit} classe={c_classe}")

    reg: dict[str, dict] = {}

    def get(row, c):
        v = row.get(c) if c else None
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        return str(v).strip()

    for row in df.to_dict("records"):
        cnpj = cnpj_digits(row[c_cnpj])
        if len(cnpj) != 14:
            continue
        sit = get(row, c_sit).upper()
        item = {
            "nome": get(row, c_nome),
            "sit": sit,
            "classe": get(row, c_classe),
            "exclusivo": get(row, c_excl).upper(),
            "cotas": get(row, c_cotas).upper(),
            "gestor": get(row, c_gestor),
            "adm": get(row, c_admin),
            "anbima": get(row, c_anbima),
            "taxa_adm": get(row, c_txadm),
            "taxa_perf": get(row, c_txperf),
            "publico": get(row, c_publico),
            "inicio": get(row, c_ini)[:10],
            "condom": get(row, c_condom),
            "tipo": get(row, c_tp),
        }
        atual = reg.get(cnpj)
        # Se o CNPJ aparece mais de uma vez, prefira o registro em funcionamento normal
        if atual is None or ("FUNCIONAMENTO NORMAL" in sit and "FUNCIONAMENTO NORMAL" not in atual["sit"]):
            reg[cnpj] = item

    # Complemento: registro de classes (RCVM 175) para CNPJs que não estão no cad_fi
    try:
        if offline:
            p = os.path.join(offline, "registro_fundo_classe.zip")
            rawz = open(p, "rb").read() if os.path.exists(p) else None
        else:
            rawz = http_get(CVM_REG)
        if rawz:
            z = zipfile.ZipFile(io.BytesIO(rawz))
            novos = 0
            # registro_fundo.csv: gestor e administrador ficam no nível do fundo (RCVM 175), ligados à classe por ID_Registro_Fundo
            fundo_info: dict[str, dict] = {}
            for name in z.namelist():
                if not name.lower().endswith("registro_fundo.csv"):
                    continue
                rawf = z.read(name)
                dff = pd.read_csv(io.BytesIO(rawf), sep=";", encoding=encoding_de(rawf[:2_000_000]), dtype=str, low_memory=False)
                cf = dff.columns
                f_id = find_col(cf, "ID_Registro_Fundo"); f_g = find_col(cf, "Gestor"); f_a = find_col(cf, "Administrador"); f_tp = find_col(cf, "Tipo_Fundo"); f_cnpj = find_col(cf, "CNPJ_Fundo")
                if f_id:
                    for row in dff.to_dict("records"):
                        fundo_info[str(row.get(f_id, "")).strip()] = {"gestor": get(row, f_g), "adm": get(row, f_a), "tipo": get(row, f_tp), "cnpj_fundo": cnpj_digits(row.get(f_cnpj, ""))}
                log(f"registro de fundos: {len(fundo_info):,} fundos com gestor/administrador")
            for name in z.namelist():
                if "classe" not in name.lower() or "subclasse" in name.lower() or not name.lower().endswith(".csv"):
                    continue
                rawc = z.read(name)
                dfc = pd.read_csv(io.BytesIO(rawc), sep=";", encoding=encoding_de(rawc[:2_000_000]), dtype=str, low_memory=False)
                cc = dfc.columns
                k_cnpj = find_col(cc, "CNPJ_Classe", "CNPJ_FUNDO_CLASSE", "CNPJ_Fundo")
                k_nome = find_col(cc, "Denominacao_Social", "DENOM_SOCIAL")
                k_sit = find_col(cc, "Situacao", "SIT")
                k_classe = find_col(cc, "Classificacao", "CLASSE")
                k_excl = find_col(cc, "Exclusivo", "FUNDO_EXCLUSIVO")
                k_anb = find_col(cc, "Classificacao_Anbima", "CLASSE_ANBIMA")
                k_pub = find_col(cc, "Publico_Alvo", "PUBLICO_ALVO")
                k_ini = find_col(cc, "Data_Inicio", "Data_Inicio_Atividade", "DT_INI_ATIV")
                k_idf = find_col(cc, "ID_Registro_Fundo")
                k_condom = find_col(cc, "Forma_Condominio")
                k_cotas = find_col(cc, "Classe_Cotas")
                if not k_cnpj or not k_nome:
                    continue
                for row in dfc.to_dict("records"):
                    cnpj = cnpj_digits(row[k_cnpj])
                    if len(cnpj) != 14:
                        continue
                    fi = fundo_info.get(str(row.get(k_idf, "")).strip(), {}) if k_idf else {}
                    if cnpj in reg:
                        # já veio do cad_fi: só completa gestor/administrador se estiverem vazios
                        if not reg[cnpj].get("gestor") and fi.get("gestor"):
                            reg[cnpj]["gestor"] = fi["gestor"]
                        if not reg[cnpj].get("adm") and fi.get("adm"):
                            reg[cnpj]["adm"] = fi["adm"]
                        continue
                    reg[cnpj] = {
                        "nome": get(row, k_nome), "sit": get(row, k_sit).upper(), "classe": get(row, k_classe),
                        "exclusivo": get(row, k_excl).upper(), "cotas": "S" if get(row, k_cotas).upper().startswith("S") else "",
                        "gestor": fi.get("gestor", ""), "adm": fi.get("adm", ""),
                        "anbima": get(row, k_anb), "taxa_adm": "", "taxa_perf": "", "publico": get(row, k_pub),
                        "inicio": get(row, k_ini)[:10], "condom": get(row, k_condom), "tipo": "CLASSE",
                    }
                    novos += 1
            log(f"registro de classes: {novos} CNPJs complementados")
    except Exception as e:  # noqa: BLE001
        log(f"aviso: registro_fundo_classe ignorado ({e})")

    log(f"cadastro consolidado: {len(reg)} CNPJs")
    return reg


# --------------------------------------------------------------------------- gestoras

def _norm_gestor(nome: str) -> str:
    s = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", s).strip()


def carregar_gestoras(caminho: str) -> list[dict]:
    try:
        return json.load(open(caminho, encoding="utf-8")).get("gestoras", [])
    except Exception as e:  # noqa: BLE001
        log(f"aviso: gestoras.json ignorado ({e})")
        return []


def casar_gestora(nome_legal: str, catalogo: list[dict]) -> dict | None:
    """Encontra a casa gestora no catálogo pelo nome legal da CVM (trechos em maiúsculas, sem acento)."""
    n = _norm_gestor(nome_legal)
    if not n:
        return None
    for g in catalogo:
        for m in g.get("match", []):
            if m in n:
                return g
    return None


def casar_gestora_xp(nome_xp: str, catalogo: list[dict]) -> dict | None:
    """Casa o nome de gestora da planilha XP (já curto, ex.: "SPX Gestão de Recursos") com o catálogo: pelo nome curto ou pelos trechos."""
    n = _norm_gestor(nome_xp)
    if not n:
        return None
    for g in catalogo:
        gn = _norm_gestor(g.get("nome", ""))
        if gn and (gn == n or gn in n or n in gn):
            return g
    return casar_gestora(nome_xp, catalogo)


def gestor_curto(nome_legal: str) -> str:
    """Nome curto derivado do nome legal quando não há catálogo: tira sufixos societários e termos genéricos."""
    n = titulo(nome_legal)
    n = re.sub(r"(?i)\b(S/?A\.?|S\.A\.?|LTDA\.?|EIRELI|DTVM|CTVM|CCVM)\b", "", n)
    n = re.sub(r"(?i)\b(Gestão|Gestao|Gestora|Gestor|Administradora|Administração|Administracao|Distribuidora|Corretora|De|Do|Da|Dos|Das|E|Em|Recursos|Investimentos|Investimento|Valores|Mobiliários|Mobiliarios|Títulos|Titulos|Carteiras?|Financeiros|Financeira|Terceiros|Consultoria|Asset|Management|Participações|Participacoes)\b", "", n)
    n = re.sub(r"\s*[\-–]\s*$", "", re.sub(r"\s+", " ", n)).strip(" -,.")
    return n or titulo(nome_legal)


# --------------------------------------------------------------------------- benchmark de referência de cada fundo

RE_NOME_INFLACAO = re.compile(r"IPCA|INFLA|IMA ?-? ?B|JURO REAL|JUROS REAIS|INDEX", re.I)
RE_NOME_ACOES = re.compile(r"\bACOES\b|\bIBOV|\bEQUIT|\bSMALL CAPS?\b|\bDIVIDEND", re.I)
RE_NOME_CAMBIO = re.compile(r"\bDOLAR\b|\bCAMBIAL\b|\bUSD\b", re.I)


def bench_do_fundo(xp: dict | None, classe_cvm: str, nome: str = "") -> str:
    """Escolhe o benchmark de comparação do fundo a partir do benchmark declarado na XP, do nome (IPCA, inflação, IMA-B...)
    ou da classe, entre os ids publicados."""
    b = _norm_gestor((xp or {}).get("benchmark", "")) if xp else ""
    tipo = _norm_gestor((xp or {}).get("tipo", "")) if xp else ""
    n = _norm_gestor(nome or "")
    if b and b != "-":
        if "CDI" in b or "SELIC" in b:
            return "cdi"
        if "IMA" in b:
            return "imab"
        if "IPCA" in b or "IGP" in b or "INPC" in b:
            return "ipca"
        if "IFIX" in b:
            return "ifix"
        if "MSCI" in b:
            return "mscibrl"
        if "S&P" in b or "SP500" in b or "NASDAQ" in b:
            return "sp500brl"
        if any(k in b for k in ("IBOV", "IBX", "IDIV", "SMLL", "IVBX", "BOVESPA", "ACOES")):
            return "ibov"
        if "DOLAR" in b or "PTAX" in b or "CAMBIO" in b:
            return "dolar"
    if "ACOES" in tipo or "ACOES" in _norm_gestor(classe_cvm):
        return "ibov"
    if "CAMBIAL" in tipo:
        return "dolar"
    # sem benchmark declarado (fundo fora da planilha XP ou com "-"): o nome diz o índice (IPCA, inflação, IMA-B, juro real; dólar; ações)
    if n:
        if RE_NOME_INFLACAO.search(n):
            return "imab"
        if RE_NOME_CAMBIO.search(n):
            return "dolar"
        if RE_NOME_ACOES.search(n):
            return "ibov"
    return "cdi"


# --------------------------------------------------------------------------- índices ANBIMA (proxy + acumulação)

# id, nome, CNPJ do fundo passivo, nome do fundo, taxa de administração (fração a.a.), nome do índice no arquivo da ANBIMA
PROXIES_INDICE = [
    ("imab", "IMA-B", "10740658000193", "Caixa Brasil IMA-B Títulos Públicos", 0.0020, "IMA-B"),
    ("irfm", "IRF-M", "14508605000100", "Caixa Brasil IRF-M Títulos Públicos", 0.0020, "IRF-M"),
]


def ler_ima_csv(caminho: str) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    if not caminho or not os.path.exists(caminho):
        return out
    with open(caminho, encoding="utf-8") as fh:
        for linha in fh:
            partes = linha.strip().split(";")
            if len(partes) != 3 or partes[0] == "indice":
                continue
            try:
                out.setdefault(partes[0], {})[partes[1]] = float(partes[2])
            except ValueError:
                continue
    return out


def gravar_ima_csv(caminho: str, dados: dict[str, dict[str, float]]) -> None:
    if not caminho:
        return
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write("indice;data;numero_indice\n")
        for nome in sorted(dados):
            for d in sorted(dados[nome]):
                fh.write(f"{nome};{d};{dados[nome][d]:.6f}\n")


# --------------------------------------------------------------------------- CDI

def carregar_cdi(inicio: date, fim: date, offline: str | None) -> dict[str, float]:
    """Retorna dict 'AAAA-MM-DD' -> taxa diária em fração (ex.: 0.00041)."""
    if offline:
        dados = json.load(open(os.path.join(offline, "cdi.json"), encoding="utf-8"))
    else:
        url = (f"{BCB_CDI}?formato=json&dataInicial={inicio.strftime('%d/%m/%Y')}"
               f"&dataFinal={fim.strftime('%d/%m/%Y')}")
        dados = fx.json_com_retentativa(url, tentativas=6, espera=25)
    out = {}
    for d in dados:
        try:
            dt = datetime.strptime(d["data"], "%d/%m/%Y").date().isoformat()
            out[dt] = float(str(d["valor"]).replace(",", ".")) / 100.0
        except Exception:  # noqa: BLE001
            continue
    log(f"CDI: {len(out)} dias ({min(out) if out else '-'} a {max(out) if out else '-'})")
    return out


# --------------------------------------------------------------------------- informes diários

def meses_alvo(n_meses: int, hoje: date) -> list[str]:
    ms = []
    y, m = hoje.year, hoje.month
    for _ in range(n_meses):
        ms.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return sorted(ms)


def ler_informe(raw: bytes, cnpjs_ok: set[str]) -> pd.DataFrame | None:
    z = zipfile.ZipFile(io.BytesIO(raw))
    nomes = [n for n in z.namelist() if n.lower().endswith(".csv")]
    if not nomes:
        return None
    frames = []
    for n in nomes:
        with z.open(n) as fh:
            header = fh.readline().decode("latin-1").strip().split(";")
        c_cnpj = find_col(header, "CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO")
        c_dt = find_col(header, "DT_COMPTC")
        c_q = find_col(header, "VL_QUOTA")
        c_pl = find_col(header, "VL_PATRIM_LIQ")
        c_cot = find_col(header, "NR_COTST")
        c_sub = find_col(header, "ID_SUBCLASSE")
        if not (c_cnpj and c_dt and c_q):
            log(f"  aviso: {n} sem colunas esperadas: {header}")
            continue
        usecols = [c for c in (c_cnpj, c_dt, c_q, c_pl, c_cot, c_sub) if c]
        df = pd.read_csv(z.open(n), sep=";", encoding="latin-1", usecols=usecols,
                         dtype={c_cnpj: str, c_dt: str, c_sub: str} if c_sub else {c_cnpj: str, c_dt: str},
                         low_memory=False)
        df = df.rename(columns={c_cnpj: "cnpj", c_dt: "dt", c_q: "q", c_pl: "pl", c_cot: "cot"})
        if c_sub:
            df = df.rename(columns={c_sub: "sub"})
            df["sub"] = df["sub"].fillna("").astype(str).str.strip()
        else:
            df["sub"] = ""
        if "pl" not in df:
            df["pl"] = np.nan
        if "cot" not in df:
            df["cot"] = np.nan
        df["cnpj"] = df["cnpj"].astype(str).str.replace(r"\D", "", regex=True)
        df = df[df["cnpj"].isin(cnpjs_ok)]
        df["q"] = pd.to_numeric(df["q"], errors="coerce")
        df["pl"] = pd.to_numeric(df["pl"], errors="coerce")
        df["cot"] = pd.to_numeric(df["cot"], errors="coerce")
        df = df[df["q"].notna() & (df["q"] > 0)]
        # Uma linha por fundo e dia: sem subclasse tem prioridade; senão a primeira subclasse
        df["_s"] = (df["sub"] != "").astype(int)
        df = df.sort_values(["cnpj", "dt", "_s", "sub"]).drop_duplicates(["cnpj", "dt"], keep="first")
        frames.append(df[["cnpj", "dt", "q", "pl", "cot"]])
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def baixar_informes(meses: list[str], offline: str | None, cache: str, cnpjs_ok: set[str]):
    quotas, pls, cots = [], [], []
    recentes = set(meses[-12:])  # os últimos 12 meses são sempre baixados de novo (a CVM retifica M-2 a M-11)
    for ym in meses:
        fname = f"inf_diario_fi_{ym}.zip"
        if offline:
            p = os.path.join(offline, fname)
            if not os.path.exists(p):
                log(f"  {fname}: não existe no modo offline, pulando")
                continue
            raw = open(p, "rb").read()
        else:
            p = os.path.join(cache, fname)
            if os.path.exists(p) and ym not in recentes:
                raw = open(p, "rb").read()
            else:
                try:
                    raw = http_get(CVM_INF + fname)
                except Exception as e:  # noqa: BLE001
                    if ym == meses[-1]:
                        log(f"  {fname} ainda não publicado ({e}); seguindo sem ele")
                        continue
                    raise
                open(p, "wb").write(raw)
        t0 = time.time()
        df = ler_informe(raw, cnpjs_ok)
        if df is None or df.empty:
            log(f"  {fname}: vazio")
            continue
        quotas.append(df.pivot(index="cnpj", columns="dt", values="q"))
        pls.append(df.pivot(index="cnpj", columns="dt", values="pl").astype("float32"))
        cots.append(df.pivot(index="cnpj", columns="dt", values="cot").astype("float32"))
        log(f"  {fname}: {len(df):,} linhas, {df['cnpj'].nunique():,} fundos ({time.time()-t0:.1f}s)")
        del df
    if not quotas:
        raise RuntimeError("nenhum informe diário processado")
    Q = pd.concat(quotas, axis=1).sort_index(axis=1)
    PL = pd.concat(pls, axis=1).sort_index(axis=1).reindex(index=Q.index, columns=Q.columns)
    CT = pd.concat(cots, axis=1).sort_index(axis=1).reindex(index=Q.index, columns=Q.columns)
    # Se um mesmo dia apareceu em dois arquivos (não deveria), fica a última coluna
    Q = Q.loc[:, ~Q.columns.duplicated(keep="last")]
    PL = PL.loc[:, ~PL.columns.duplicated(keep="last")]
    CT = CT.loc[:, ~CT.columns.duplicated(keep="last")]
    return Q, PL, CT


# --------------------------------------------------------------------------- métricas

def ffill_1d(a: np.ndarray) -> np.ndarray:
    mask = np.isnan(a)
    idx = np.where(~mask, np.arange(len(a)), 0)
    np.maximum.accumulate(idx, out=idx)
    out = a[idx]
    out[mask & (idx == 0) & np.isnan(a[0])] = np.nan
    return out


def idx_ate(datas: list[date], alvo: date) -> int:
    """Último índice do calendário com data <= alvo (ou -1)."""
    import bisect
    return bisect.bisect_right(datas, alvo) - 1


def metricas_fundo(q: np.ndarray, datas: list[date], cdi_idx: np.ndarray, asof_i: int,
                   fim_mes_i: list[int], meses_lbl: list[str], mes_fechado: list[bool]) -> dict:
    """q: cotas alinhadas ao calendário (NaN onde não há informe); asof_i: índice da última cota."""
    validos = ~np.isnan(q)
    first_i = int(np.argmax(validos))
    qff = ffill_1d(q)
    asof = datas[asof_i]
    q1 = qff[asof_i]
    out = {}

    # retornos mensais (fundo e CDI) para consistência e tabela mensal; o mês corrente entra como parcial
    mensal = []  # (rótulo, ret fundo, ret cdi, índice do fim, parcial?)
    for k in range(1, len(fim_mes_i)):
        i0, i1 = fim_mes_i[k - 1], fim_mes_i[k]
        if i1 > asof_i:
            break
        if i0 < first_i or np.isnan(qff[i0]) or np.isnan(qff[i1]):
            continue
        parcial = (i1 == asof_i) and not mes_fechado[k]
        rf = qff[i1] / qff[i0] - 1
        rc = cdi_idx[i1] / cdi_idx[i0] - 1
        mensal.append((meses_lbl[k], rf, rc, i1, parcial))
    # asof no meio de um mês que ainda não é o último do calendário (fundo atrasado): mês parcial próprio
    ultimo_fm = [i for i in fim_mes_i if i <= asof_i]
    if ultimo_fm and ultimo_fm[-1] < asof_i and ultimo_fm[-1] >= first_i:
        i0 = ultimo_fm[-1]
        mensal.append((asof.strftime("%Y-%m"), qff[asof_i] / qff[i0] - 1, cdi_idx[asof_i] / cdi_idx[i0] - 1, asof_i, True))

    janelas = {}
    for W in JANELAS:
        anchor = (pd.Timestamp(asof) - pd.DateOffset(months=W)).date()
        a_i = idx_ate(datas, anchor)
        if a_i < 0 or datas[first_i] > anchor or np.isnan(qff[a_i]):
            janelas[str(W)] = None
            continue
        q0 = qff[a_i]
        ret = q1 / q0 - 1
        cdi_ret = cdi_idx[asof_i] / cdi_idx[a_i] - 1
        seg = q[a_i:asof_i + 1]
        v = seg[~np.isnan(seg)]
        rr = v[1:] / v[:-1] - 1 if len(v) > 2 else np.array([])
        anos = W / 12.0
        if len(rr) >= 10:
            vol = float(np.std(rr, ddof=1) * math.sqrt(len(rr) / anos))
        else:
            vol = float("nan")
        ann = (1 + ret) ** (1 / anos) - 1
        ann_cdi = (1 + cdi_ret) ** (1 / anos) - 1
        sharpe = (ann - ann_cdi) / vol if vol and vol > 1e-9 else float("nan")
        segff = qff[a_i:asof_i + 1]
        cm = np.maximum.accumulate(np.where(np.isnan(segff), -np.inf, segff))
        dd = segff / cm - 1
        mdd = float(np.nanmin(dd)) if len(dd) else float("nan")
        dd_atual = float(dd[-1]) if len(dd) else float("nan")
        # consistência: só meses fechados dentro da janela (fim de mês > âncora)
        ms = [m for m in mensal if m[3] > a_i and m[3] <= asof_i and not m[4]]
        n_m = len(ms)
        acima = sum(1 for m in ms if m[1] > m[2])
        positivos = sum(1 for m in ms if m[1] > 0)
        janelas[str(W)] = {
            "ret": r6(ret), "cdi": r6(cdi_ret),
            "pcdi": rn(ret / cdi_ret * 100, 1) if cdi_ret > 0 else None,
            "vol": rn(vol, 4), "sharpe": rn(sharpe, 2), "mdd": rn(mdd, 4), "dd": rn(dd_atual, 4),
            "cons": rn(acima / n_m, 3) if n_m else None,
            "pos": rn(positivos / n_m, 3) if n_m else None,
            "meses": n_m,
            "melhor": r6(max(m[1] for m in ms)) if ms else None,
            "pior": r6(min(m[1] for m in ms)) if ms else None,
        }
    # no mês e no ano
    extras = {}
    ano_ini = date(asof.year - 1, 12, 31)
    i_ano = idx_ate(datas, ano_ini)
    if i_ano >= first_i and i_ano >= 0 and not np.isnan(qff[i_ano]):
        extras["ano"] = {"ret": r6(q1 / qff[i_ano] - 1), "cdi": r6(cdi_idx[asof_i] / cdi_idx[i_ano] - 1)}
    mes_ini = (asof.replace(day=1) - timedelta(days=1))
    i_mes = idx_ate(datas, mes_ini)
    if i_mes >= first_i and i_mes >= 0 and not np.isnan(qff[i_mes]):
        extras["mes"] = {"ret": r6(q1 / qff[i_mes] - 1), "cdi": r6(cdi_idx[asof_i] / cdi_idx[i_mes] - 1)}
    out["janelas"] = janelas
    out["extras"] = extras
    out["mensal"] = [[m[0], r6(m[1]), r6(m[2])] + ([1] if m[4] else []) for m in mensal]
    out["first_i"] = first_i
    return out


# --------------------------------------------------------------------------- principal

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/data")
    ap.add_argument("--cache", default="cache")
    ap.add_argument("--meses", type=int, default=51, help="meses de informe diário (48 + folga)")
    ap.add_argument("--offline", default=None, help="pasta com arquivos locais em vez de baixar")
    ap.add_argument("--min-cotistas", type=int, default=MIN_COTISTAS)
    ap.add_argument("--hoje", default=None, help="AAAA-MM-DD (testes)")
    ap.add_argument("--ima-csv", default="status/ima.csv", help="acumulado diário dos índices ANBIMA (lido e regravado a cada execução)")
    ap.add_argument("--xp", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "xp_fundos.csv"),
                    help="lista de fundos da plataforma XP (extraída do Guia de Fundos)")
    ap.add_argument("--sem-extras", action="store_true", help="pula benchmarks e Tesouro (testes rápidos)")
    args = ap.parse_args()

    hoje = date.fromisoformat(args.hoje) if args.hoje else date.today()
    os.makedirs(args.out, exist_ok=True)
    for sub in ("fundos", "bench", "tesouro", "hist"):
        os.makedirs(os.path.join(args.out, sub), exist_ok=True)
    os.makedirs(args.cache, exist_ok=True)
    avisos: list[str] = []
    t_ini = time.time()

    log("1/5 cadastro de fundos")
    reg = carregar_cadastro(args.offline, args.cache)

    # fundos da plataforma XP: entram mesmo com poucos cotistas ou marcados como exclusivos
    # (os FIEs de previdência têm a seguradora como único cotista)
    xp_lista = fx.carregar_xp(args.xp)
    gestoras = carregar_gestoras(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gestoras.json"))
    log(f"  catálogo de gestoras: {len(gestoras)} casas")
    if not args.offline:
        try:
            fx.baixar_logos(gestoras, os.path.join(args.out, "logos"), os.path.join(args.cache, "logos"), log=log)
        except Exception as e:  # ícones são acessórios: nunca derrubam a execução
            log(f"  ícones das gestoras: falhou ({e})")
    xp_cnpjs = set(xp_lista)
    log(f"  lista XP: {len(xp_lista):,} CNPJs")

    # universo cadastral: em funcionamento (quando a situação é conhecida) e não exclusivo
    def elegivel(c, r):
        if r["exclusivo"].startswith("S") and c not in xp_cnpjs and not eh_previdencia(r.get("nome", "")):
            return False
        sit = r["sit"]
        if sit and "FUNCIONAMENTO NORMAL" not in sit:
            return False
        return True

    cnpjs_ok = {c for c, r in reg.items() if elegivel(c, r)}
    cnpjs_ok |= {c for c in xp_cnpjs if c not in reg}  # sem cadastro conhecido: tenta mesmo assim
    log(f"universo cadastral elegível: {len(cnpjs_ok):,} de {len(reg):,}")

    log("2/5 informes diários")
    meses = meses_alvo(args.meses, hoje)
    Q, PL, CT = baixar_informes(meses, args.offline, args.cache, cnpjs_ok)
    datas_str = list(Q.columns)
    datas = [date.fromisoformat(d[:10]) for d in datas_str]
    log(f"matriz: {Q.shape[0]:,} fundos x {Q.shape[1]:,} dias ({datas_str[0]} a {datas_str[-1]})")

    log("3/5 CDI")
    cdi = carregar_cdi(datas[0] - timedelta(days=10), hoje, args.offline)
    taxas = np.array([cdi.get(d.isoformat(), np.nan) for d in datas])
    faltando = int(np.isnan(taxas).sum())
    if faltando:
        avisos.append(f"CDI sem valor em {faltando} dias do calendário (tratados como 0)")
    taxas = np.nan_to_num(taxas, nan=0.0)
    cdi_idx = np.cumprod(1 + taxas)

    # data de referência global: último dia em que pelo menos 60% dos fundos "ativos" informaram
    contagem = Q.notna().sum(axis=0).values
    pico = contagem[-40:].max() if len(contagem) >= 40 else contagem.max()
    ref_i = len(datas) - 1
    while ref_i > 0 and contagem[ref_i] < 0.6 * pico:
        ref_i -= 1
    ref = datas[ref_i]
    log(f"data de referência: {ref} ({contagem[ref_i]:,} informes; pico recente {pico:,})")

    # fins de mês (último dia útil do calendário em cada mês)
    fim_mes_i, meses_lbl = [], []
    for i, d in enumerate(datas):
        lbl = d.strftime("%Y-%m")
        if not meses_lbl or meses_lbl[-1] != lbl:
            fim_mes_i.append(i)
            meses_lbl.append(lbl)
        else:
            fim_mes_i[-1] = i
    # um mês só é "fechado" se o último dia do calendário nele for o último dia útil do mês
    # (o último mês do calendário costuma estar em andamento)
    mes_fechado = []
    for i in fim_mes_i:
        if i < len(datas) - 1:
            mes_fechado.append(True)  # existe dia seguinte no calendário (já em outro mês)
        else:
            ultimo_util = (pd.Timestamp(datas[i]) + pd.offsets.BMonthEnd(0)).date()
            mes_fechado.append(datas[i] >= ultimo_util)

    # semanas (último índice de cada semana ISO) para as séries de patrimônio e cotistas
    semanas_i, chave = [], None
    for i, d in enumerate(datas):
        k = d.isocalendar()[:2]
        if k != chave:
            semanas_i.append(i)
            chave = k
        else:
            semanas_i[-1] = i

    log("4/5 métricas por fundo")
    Qv = Q.values
    PLv = PL.values
    CTv = CT.values
    cnpjs = list(Q.index)
    index_rows = []
    n_ok = n_parado = n_poucos = n_hist = n_xp = 0
    for r, cnpj in enumerate(cnpjs):
        q = Qv[r].astype(float)
        validos = ~np.isnan(q)
        if validos.sum() < 5:
            n_hist += 1
            continue
        idx_validos = np.where(validos)[0]
        last_i = int(idx_validos[-1])
        if last_i < ref_i - DIAS_TOLERANCIA:
            n_parado += 1
            continue
        # data de referência do fundo: última cota até a data de referência global
        ate_ref = idx_validos[idx_validos <= ref_i]
        if len(ate_ref) == 0:
            n_hist += 1
            continue
        asof_i = int(ate_ref[-1])
        ct = ffill_1d(CTv[r].astype(float))
        pl = ffill_1d(PLv[r].astype(float))
        cot_atual = ct[asof_i]
        pl_atual = pl[asof_i]
        info = reg.get(cnpj, {})
        if (not np.isnan(cot_atual) and cot_atual < args.min_cotistas and cnpj not in xp_cnpjs
                and not eh_previdencia(info.get("nome", ""))):
            n_poucos += 1
            continue
        m = metricas_fundo(q, datas, cdi_idx, asof_i, fim_mes_i, meses_lbl, mes_fechado)
        nome = titulo(info.get("nome") or xp_lista.get(cnpj, {}).get("nome_xp") or cnpj)
        first_i = m["first_i"]
        # série semanal de PL e cotistas a partir da primeira semana com dado
        w_ini = next((k for k, i in enumerate(semanas_i) if i >= first_i), None)
        if w_ini is None:
            w_ini = len(semanas_i) - 1
        pl_w = [None if np.isnan(pl[i]) else round(float(pl[i])) for i in semanas_i[w_ini:]]
        ct_w = [None if np.isnan(ct[i]) else int(ct[i]) for i in semanas_i[w_ini:]]
        # cotas diárias a partir do primeiro dado, com 7 algarismos significativos
        qs = [None if np.isnan(v) else float(f"{v:.7g}") for v in q[first_i:]]
        j12 = m["janelas"].get("12") or {}
        xp = xp_lista.get(cnpj)
        gl = info.get("gestor", "")
        g_xp = ((xp or {}).get("gestor") or "").strip()
        # fundos de previdência: a planilha XP traz o gestor estratégico (SPX, Ibiuna...), que é quem o cliente reconhece;
        # o gestor da CVM (muitas vezes a própria XP ou a seguradora) fica como nome legal na ficha
        if g_xp and (eh_previdencia(nome) or (xp or {}).get("origem") == "previdencia"):
            gcat = casar_gestora_xp(g_xp, gestoras) or (casar_gestora(gl, gestoras) if gl else None)
            g_curto = (gcat or {}).get("nome") or gestor_curto(g_xp)
        else:
            gcat = (casar_gestora(gl, gestoras) if gl else None) or (casar_gestora_xp(g_xp, gestoras) if g_xp else None)
            g_curto = (gcat or {}).get("nome") or (gestor_curto(gl) if gl else (gestor_curto(g_xp) if g_xp else ""))
        g_site = (gcat or {}).get("site") if gcat and gcat.get("logo") else None
        # "p": ícone processado pelo pipeline (fundo transparente) em data/logos/<slug>.png; senão o favicon direto
        g_logo = ("p" if gcat.get("logo_proc") else gcat.get("logo")) if gcat and gcat.get("logo") else None
        taxa_adm = info.get("taxa_adm", "") or ((xp or {}).get("taxa_adm") if xp and xp.get("taxa_adm") is not None else "")
        doc = {
            "cnpj": cnpj,
            "xp": xp,
            "gestor_curto": g_curto,
            "gestor_site": g_site,
            "gestor_logo": g_logo,
            "cnpj_fmt": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
            "nome": nome,
            "classe": info.get("classe", ""),
            "anbima": info.get("anbima", ""),
            "gestor": titulo(info.get("gestor", "")),
            "adm": titulo(info.get("adm", "")),
            "publico": info.get("publico", ""),
            "taxa_adm": taxa_adm,
            "taxa_perf": info.get("taxa_perf", "") or ((xp or {}).get("taxa_perf") if xp and xp.get("taxa_perf") is not None else ""),
            "inicio": info.get("inicio", ""),
            "cotas": info.get("cotas", ""),
            "ate": datas[asof_i].isoformat(),
            "pl": None if np.isnan(pl_atual) else round(float(pl_atual)),
            "cotistas": None if np.isnan(cot_atual) else int(cot_atual),
            "d0": first_i,
            "q": qs,
            "w0": w_ini,
            "plw": pl_w,
            "cotw": ct_w,
            "janelas": m["janelas"],
            "extras": m["extras"],
            "mensal": m["mensal"],
        }
        with open(os.path.join(args.out, "fundos", f"{cnpj}.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
        j24 = m["janelas"].get("24") or {}
        j36 = m["janelas"].get("36") or {}
        index_rows.append([
            cnpj, nome, info.get("classe", ""), g_curto,
            doc["pl"], doc["cotistas"],
            j12.get("ret"), j12.get("pcdi"), j12.get("sharpe"), j12.get("vol"),
            (xp or {}).get("tipo"), (xp or {}).get("classe"), (xp or {}).get("risco"),
            1 if (xp or {}).get("top") else 0, (xp or {}).get("estrelas"),
            j24.get("ret"), j36.get("ret"), g_site, g_logo, bench_do_fundo(xp, info.get("classe", ""), nome),
        ])
        if xp:
            n_xp += 1
        n_ok += 1
        if n_ok % 2000 == 0:
            log(f"  {n_ok:,} fundos gravados")

    # ------------------------------------------------------------------ benchmarks, históricos e Tesouro Direto
    def doc_serie(q: np.ndarray, extra: dict) -> dict | None:
        validos = ~np.isnan(q)
        if validos.sum() < 30:
            return None
        idx_v = np.where(validos)[0]
        ate_ref = idx_v[idx_v <= ref_i]
        if len(ate_ref) == 0:
            return None
        asof_i = int(ate_ref[-1])
        m = metricas_fundo(q, datas, cdi_idx, asof_i, fim_mes_i, meses_lbl, mes_fechado)
        first_i = m["first_i"]
        d = dict(extra)
        d.update({"ate": datas[asof_i].isoformat(), "d0": first_i,
                  "q": [None if np.isnan(v) else float(f"{v:.7g}") for v in q[first_i:]],
                  "janelas": m["janelas"], "extras": m["extras"], "mensal": m["mensal"]})
        return d

    bench_meta, tesouro_meta, hist_meta = [], [], []
    if not args.sem_extras:
        log("4b/5 benchmarks")
        try:
            bench, hist = fx.construir_benchmarks(datas, hoje, args.offline, avisos)
        except Exception as e:  # noqa: BLE001
            avisos.append(f"benchmarks falharam: {e}")
            bench, hist = [], {}
        # Índices ANBIMA sem fonte aberta com histórico: replicados por fundos passivos de títulos públicos (taxa devolvida),
        # emendados com o número oficial diário da ANBIMA acumulado em status/ima.csv (público, só o dia corrente).
        ima_csv = args.ima_csv
        ima_hist = ler_ima_csv(ima_csv)
        if not args.offline:
            try:
                hoje_ima = fx.anbima_ima_hoje()
                novos_ima = 0
                for nome_i, (d_i, v_i) in hoje_ima.items():
                    if d_i not in ima_hist.setdefault(nome_i, {}):
                        ima_hist[nome_i][d_i] = v_i
                        novos_ima += 1
                gravar_ima_csv(ima_csv, ima_hist)
                log(f"  ANBIMA IMA: {len(hoje_ima)} índices em {next(iter(hoje_ima.values()))[0]} ({novos_ima} novos; {sum(len(v) for v in ima_hist.values())} registros acumulados)")
            except Exception as e:  # noqa: BLE001
                avisos.append(f"ANBIMA IMA diário indisponível: {e}")
        for id_, nome_b, cnpj_p, nome_f, taxa_p, chave_anbima in PROXIES_INDICE:
            if args.offline and cnpj_p not in Q.index:
                cnpj_p = str(Q.index[0])  # base sintética: qualquer fundo serve para exercitar o caminho
            if cnpj_p not in Q.index:
                avisos.append(f"benchmark {nome_b}: fundo {nome_f} ({cnpj_p}) não está na matriz")
                continue
            qp = ffill_1d(Q.loc[cnpj_p].to_numpy(dtype=float))
            fator = (1.0 + taxa_p) ** (1.0 / 252.0)
            qg = np.full(len(qp), np.nan)
            base = None
            for i, v in enumerate(qp):
                if np.isnan(v):
                    continue
                if base is None:
                    qg[i] = 100.0
                else:
                    qg[i] = qg[base] * (v / qp[base]) * (fator ** (i - base))
                base = i
            desc = f"Replicado pelo fundo passivo {nome_f} (taxa de administração de {taxa_p * 100:.2f}% a.a. devolvida)"
            fonte = "CVM (fundo indexado)"
            ofi = ima_hist.get(chave_anbima) or {}
            if len(ofi) >= 20:
                # emenda: a partir do primeiro dia oficial disponível, segue o número da ANBIMA (escalado no dia da emenda)
                d_str = [d.isoformat() for d in datas]
                j0 = next((i for i, ds in enumerate(d_str) if ds in ofi and not np.isnan(qg[i])), None)
                if j0 is not None:
                    escala = qg[j0] / ofi[d_str[j0]]
                    ult = qg[j0]
                    for i in range(j0, len(d_str)):
                        if d_str[i] in ofi:
                            ult = ofi[d_str[i]] * escala
                        qg[i] = ult
                    desc += f"; número oficial da ANBIMA a partir de {d_str[j0]}"
                    fonte = "ANBIMA (oficial) + fundo indexado"
            bench.append({"id": id_, "nome": nome_b, "moeda": "BRL", "fonte": fonte, "desc": desc, "q": qg})
            log(f"  {nome_b}: proxy pelo fundo {nome_f}" + (" com emenda oficial" if len(ofi) >= 20 else ""))
        for b in bench:
            d = doc_serie(b["q"], {k: v for k, v in b.items() if k != "q"})
            if not d:
                avisos.append(f"benchmark {b['nome']} sem dados suficientes")
                continue
            with open(os.path.join(args.out, "bench", f"{b['id']}.json"), "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(",", ":"))
            j12 = d["janelas"].get("12") or {}
            bench_meta.append({"id": b["id"], "nome": b["nome"], "moeda": b["moeda"], "fonte": b["fonte"], "desc": b["desc"],
                               "ret12": j12.get("ret"), "ate": d["ate"]})
        for sym, h in hist.items():
            sid = fx.slug(sym)
            with open(os.path.join(args.out, "hist", f"{sid}.json"), "w", encoding="utf-8") as fh:
                json.dump({"simbolo": sym, **h}, fh, ensure_ascii=False, separators=(",", ":"))
            hist_meta.append({"id": sid, "simbolo": sym, "nome": h["nome"], "desde": h["datas"][0], "ate": h["datas"][-1], "n": len(h["datas"])})
        log(f"  {len(bench_meta)} benchmarks, {len(hist_meta)} históricos")

        log("4c/5 Tesouro Direto")
        try:
            titulos = fx.carregar_tesouro(datas, hoje, args.offline, args.cache, avisos)
        except Exception as e:  # noqa: BLE001
            avisos.append(f"Tesouro Direto falhou: {e}")
            titulos = []
        for t in titulos:
            txs = t.pop("taxa_serie")
            d = doc_serie(t["q"], {k: v for k, v in t.items() if k != "q"})
            if not d:
                continue
            # série semanal da taxa
            d["taxaw"] = [None if np.isnan(txs[i]) else round(float(txs[i]), 4) for i in semanas_i]
            with open(os.path.join(args.out, "tesouro", f"{t['id']}.json"), "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(",", ":"))
            j12 = d["janelas"].get("12") or {}
            tesouro_meta.append({"id": t["id"], "nome": t["nome"], "tipo": t["tipo"], "indexador": t["indexador"], "venc": t["venc"],
                                 "taxa": t["taxa"], "duration": None if t["duration"] is None else round(t["duration"], 2),
                                 "cupom": t["cupom"], "ret12": j12.get("ret"), "vol12": j12.get("vol"), "ate": d["ate"]})
        tesouro_meta.sort(key=lambda x: (x["tipo"], x["venc"]))

    log("5/5 índice e metadados")
    index_rows.sort(key=lambda x: -(x[4] or 0))
    with open(os.path.join(args.out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"colunas": ["cnpj", "nome", "classe", "gestor", "pl", "cotistas", "ret12", "pcdi12", "sharpe12", "vol12",
                               "xp_tipo", "xp_classe", "xp_risco", "xp_top", "xp_estrelas", "ret24", "ret36", "gestor_site", "gestor_logo", "bm"],
                   "fundos": index_rows}, fh, ensure_ascii=False, separators=(",", ":"))
    meta = {
        "referencia": ref.isoformat(),
        "gerado": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "calendario": [d.isoformat() for d in datas],
        "semanas": semanas_i,
        "fim_mes": fim_mes_i,
        "meses": meses_lbl,
        "cdi": [float(f"{v:.9g}") for v in cdi_idx],
        "cdi_taxa": [float(f"{v:.6g}") for v in taxas],
        "n_fundos": n_ok,
        "n_xp": n_xp,
        "benchmarks": bench_meta,
        "tesouro": tesouro_meta,
        "historicos": hist_meta,
        "xp_tipos": [t for t, _ in fx.TIPO_XP],
        "janelas": list(JANELAS),
        "min_cotistas": args.min_cotistas,
        "fontes": {
            "cvm_informe_diario": CVM_INF,
            "cvm_cadastro": CVM_CAD,
            "bcb_cdi": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados",
            "bcb_ipca": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados",
            "bcb_poupanca": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.195/dados",
            "bcb_ptax": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados",
            "tesouro_direto": fx.TESOURO_CSV,
            "indices": "B3 (Ibovespa, IFIX), Nasdaq (Nasdaq 100, SPY, URTH, GLD, AIQ), Coinbase (Bitcoin em dólar, convertido pela PTAX); reservas CoinGecko, Yahoo, Stooq e FRED",
        },
    }
    # expectativas do Focus (medianas anuais de Selic e IPCA) para as premissas do simulador; fica em cache por 1 dia
    if not args.offline:
        focus = None
        try:
            focus = fx.focus_expectativas()
        except Exception as e:
            log(f"  Focus: falhou ({e})")
        if focus:
            meta["focus"] = focus
            log(f"  Focus de {focus['data']}: Selic {focus['selic']} · IPCA {focus['ipca']} · câmbio {focus.get('cambio')}")
        else:
            log("  Focus: sem resposta da API do BCB; o simulador usa o CDI e o IPCA atuais")
    else:
        meta["focus"] = {"data": ref.isoformat(), "selic": {str(ref.year): 14.75, str(ref.year + 1): 12.25, str(ref.year + 2): 10.5, str(ref.year + 3): 10.0},
                         "ipca": {str(ref.year): 4.8, str(ref.year + 1): 4.3, str(ref.year + 2): 3.9, str(ref.year + 3): 3.75},
                         "cambio": {str(ref.year): 5.45, str(ref.year + 1): 5.5, str(ref.year + 2): 5.6, str(ref.year + 3): 5.7}}
    # estatísticas de 15 anos (CDI, IPCA 12 m, juro real de 10 anos) para os cenários do simulador
    if not args.sem_extras:
        try:
            h15 = fx.historico_15_anos(ref, args.offline, avisos)
            meta["hist15"] = h15
            res = " · ".join(f"{k} {v['min']}/{v['mediana']}/{v['max']} desde {v['desde'][:7]}" for k, v in h15.items() if isinstance(v, dict))
            log(f"  15 anos (mín/mediana/máx): {res}")
        except Exception as e:  # noqa: BLE001
            avisos.append(f"estatísticas de 15 anos falharam: {e}")
    # catálogo de COEs da XP (mantido à mão em pipeline/coes.json, a partir das lâminas e DIEs)
    coes_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coes.json")
    if os.path.exists(coes_src):
        with open(coes_src, encoding="utf-8") as fh:
            coes = json.load(fh)
        with open(os.path.join(args.out, "coes.json"), "w", encoding="utf-8") as fh:
            json.dump(coes, fh, ensure_ascii=False, separators=(",", ":"))
        meta["n_coes"] = len(coes.get("coes", []))
        meta["coes_capturado"] = coes.get("capturado")
        log(f"  COEs: {meta['n_coes']} estruturas do catálogo")
    with open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, separators=(",", ":"))
    status = {
        "referencia": ref.isoformat(), "gerado": meta["gerado"], "fundos_publicados": n_ok,
        "fundos_na_matriz": len(cnpjs), "fundos_xp": n_xp, "benchmarks": [b["id"] for b in bench_meta],
        "tesouro_titulos": len(tesouro_meta), "historicos": [h["simbolo"] for h in hist_meta], "descartados_parados": n_parado,
        "descartados_poucos_cotistas": n_poucos, "descartados_historico_curto": n_hist,
        "dias_calendario": len(datas), "meses_processados": meses, "avisos": avisos,
        "duracao_s": round(time.time() - t_ini),
    }
    with open(os.path.join(args.out, "status.json"), "w", encoding="utf-8") as fh:
        json.dump(status, fh, ensure_ascii=False, indent=2)
    log(f"concluído: {n_ok:,} fundos publicados em {status['duracao_s']}s "
        f"(parados {n_parado:,}, poucos cotistas {n_poucos:,}, histórico curto {n_hist:,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
