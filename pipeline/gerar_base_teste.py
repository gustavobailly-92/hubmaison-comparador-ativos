#!/usr/bin/env python3
"""Gera uma base sintética no formato dos dados abertos da CVM e do SGS/BCB para testar o pipeline.
Uso: python gerar_base_teste.py pasta_destino [AAAA-MM-DD de referência]
"""
import io
import json
import os
import sys
import zipfile
from datetime import date, timedelta

import numpy as np
import pandas as pd

dest = sys.argv[1]
hoje = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2026, 9, 25)
os.makedirs(dest, exist_ok=True)
rng = np.random.default_rng(7)

inicio = date(2022, 6, 1)
feriados = {date(y, m, d) for y in range(2022, 2027) for (m, d) in [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)]}
dias = [d.date() for d in pd.bdate_range(inicio, hoje) if d.date() not in feriados]

FUNDOS = [
    # cnpj, nome, classe, exclusivo, sit, drift anual, vol anual, cotistas, pl, inicio (None = antes do período)
    ("11111111000101", "XP INVESTOR FI RENDA FIXA CREDITO PRIVADO LP", "Fundo de Renda Fixa", "N", "EM FUNCIONAMENTO NORMAL", 0.125, 0.006, 42000, 3.2e9, None),
    ("22222222000102", "KAPITALO ZETA FIC FIM", "Fundo Multimercado", "N", "EM FUNCIONAMENTO NORMAL", 0.15, 0.12, 18000, 1.1e9, None),
    ("33333333000103", "ABSOLUTE VERTEX FIC FIM", "Fundo Multimercado", "N", "EM FUNCIONAMENTO NORMAL", 0.11, 0.05, 9000, 4.5e9, None),
    ("44444444000104", "IBIUNA HEDGE FIC FIM", "Fundo Multimercado", "N", "EM FUNCIONAMENTO NORMAL", 0.09, 0.09, 12000, 2.2e9, None),
    ("55555555000105", "BTG PACTUAL ABSOLUTO INSTITUCIONAL FIC FIA", "Fundo de Ações", "N", "EM FUNCIONAMENTO NORMAL", 0.06, 0.22, 7000, 800e6, None),
    ("66666666000106", "TRIGONO FLAGSHIP SMALL CAPS FIC FIA", "Fundo de Ações", "N", "EM FUNCIONAMENTO NORMAL", 0.02, 0.28, 5500, 600e6, None),
    ("77777777000107", "ITAU PRIVILEGE RENDA FIXA REFERENCIADO DI FIC", "Fundo de Renda Fixa", "N", "EM FUNCIONAMENTO NORMAL", 0.112, 0.002, 150000, 12e9, None),
    ("88888888000108", "FAMILIA SILVA FIM EXCLUSIVO", "Fundo Multimercado", "S", "EM FUNCIONAMENTO NORMAL", 0.1, 0.05, 1, 50e6, None),
    ("99999999000109", "FUNDO ENCERRADO FIM", "Fundo Multimercado", "N", "CANCELADA", 0.1, 0.05, 30, 10e6, None),
    ("10101010000110", "MAISON NOVO FIC FIM", "Fundo Multimercado", "N", "EM FUNCIONAMENTO NORMAL", 0.14, 0.08, 900, 120e6, date(2025, 3, 10)),
    ("12121212000111", "GESTORA PEQUENA FIM", "Fundo Multimercado", "N", "EM FUNCIONAMENTO NORMAL", 0.1, 0.05, 4, 8e6, None),
    ("13131313000112", "SPX NIMITZ FEEDER FIC FIM", "Fundo Multimercado", "N", "EM FUNCIONAMENTO NORMAL", 0.13, 0.10, 30000, 9e9, None),
    ("14141414000113", "SO NO REGISTRO DE CLASSES FIF RF", "", "N", "EM FUNCIONAMENTO NORMAL", 0.11, 0.004, 2000, 300e6, None),
]

# CDI diário: ~13,15% a.a. até 2023, caindo para ~10,5%, subindo de novo em 2025 (só para variar)
cdi = []
for d in dias:
    if d < date(2023, 8, 1):
        aa = 0.1365
    elif d < date(2024, 6, 1):
        aa = 0.1215
    elif d < date(2025, 1, 1):
        aa = 0.1065
    elif d < date(2025, 7, 1):
        aa = 0.1315
    else:
        aa = 0.1465
    taxa_dia = (1 + aa) ** (1 / 252) - 1
    cdi.append({"data": d.strftime("%d/%m/%Y"), "valor": f"{taxa_dia * 100:.6f}"})
json.dump(cdi, open(os.path.join(dest, "cdi.json"), "w"))

# séries por fundo
series = {}
for cnpj, nome, classe, excl, sit, mu, sig, cot, pl, ini in FUNDOS:
    ds = [d for d in dias if ini is None or d >= ini]
    n = len(ds)
    r = rng.normal(mu / 252, sig / np.sqrt(252), n)
    q = 100 * np.cumprod(1 + r)
    cots = np.maximum(1, (cot * (0.7 + 0.3 * np.linspace(0, 1, n)) * (1 + rng.normal(0, 0.01, n).cumsum() / 20)).astype(int))
    pls = pl * (0.6 + 0.4 * np.linspace(0, 1, n)) * q / q[-1]
    series[cnpj] = (ds, q, pls, cots)

# informes mensais
meses = sorted({d.strftime("%Y%m") for d in dias})
for ym in meses:
    novo = ym >= "202501"
    linhas = []
    for cnpj, nome, classe, excl, sit, mu, sig, cot, pl, ini in FUNDOS:
        ds, q, pls, cots = series[cnpj]
        cf = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
        for i, d in enumerate(ds):
            if d.strftime("%Y%m") != ym:
                continue
            # fundo encerrado para de informar em 2025-06
            if cnpj.startswith("9999") and d >= date(2025, 6, 1):
                continue
            # o feeder da SPX tem subclasses a partir de 2025 (linha da classe + duas subclasses)
            if novo:
                base = ["FIF" if not novo else "CLASSES - FIF", cf, "", d.isoformat(), f"{pls[i]:.2f}", f"{q[i]:.12f}", f"{pls[i]:.2f}", "0.00", "0.00", str(cots[i])]
                if cnpj.startswith("1313"):
                    linhas.append(["CLASSES - FIF", cf, "SUB-A", d.isoformat(), f"{pls[i]:.2f}", f"{q[i]*1.01:.12f}", f"{pls[i]*0.6:.2f}", "0.00", "0.00", str(cots[i] // 2)])
                    linhas.append(["CLASSES - FIF", cf, "SUB-B", d.isoformat(), f"{pls[i]:.2f}", f"{q[i]*0.99:.12f}", f"{pls[i]*0.4:.2f}", "0.00", "0.00", str(cots[i] // 2)])
                else:
                    linhas.append(base)
            else:
                linhas.append(["FI", cf, d.isoformat(), f"{pls[i]:.2f}", f"{q[i]:.12f}", f"{pls[i]:.2f}", "0.00", "0.00", str(cots[i])])
    header = (["TP_FUNDO_CLASSE", "CNPJ_FUNDO_CLASSE", "ID_SUBCLASSE", "DT_COMPTC", "VL_TOTAL", "VL_QUOTA", "VL_PATRIM_LIQ", "CAPTC_DIA", "RESG_DIA", "NR_COTST"]
              if novo else ["TP_FUNDO", "CNPJ_FUNDO", "DT_COMPTC", "VL_TOTAL", "VL_QUOTA", "VL_PATRIM_LIQ", "CAPTC_DIA", "RESG_DIA", "NR_COTST"])
    csv = ";".join(header) + "\n" + "\n".join(";".join(l) for l in linhas) + "\n"
    with zipfile.ZipFile(os.path.join(dest, f"inf_diario_fi_{ym}.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"inf_diario_fi_{ym}.csv", csv.encode("latin-1"))

# cadastro legado
cols = ["TP_FUNDO", "CNPJ_FUNDO", "DENOM_SOCIAL", "DT_REG", "DT_CONST", "CD_CVM", "DT_CANCEL", "SIT", "DT_INI_SIT", "DT_INI_ATIV",
        "CLASSE", "RENTAB_FUNDO", "CONDOM", "FUNDO_COTAS", "FUNDO_EXCLUSIVO", "TRIB_LPRAZO", "PUBLICO_ALVO", "TAXA_PERFM", "TAXA_ADM",
        "VL_PATRIM_LIQ", "DT_PATRIM_LIQ", "ADMIN", "GESTOR", "CLASSE_ANBIMA"]
rows = []
for cnpj, nome, classe, excl, sit, mu, sig, cot, pl, ini in FUNDOS:
    if cnpj.startswith("1414"):
        continue  # só no registro de classes
    cf = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    rows.append(["FI", cf, nome, "2015-01-01", "2015-01-01", "123", "", sit, "2015-01-01", (ini or date(2015, 1, 1)).isoformat(),
                 classe, "", "Aberto", "S" if "FIC" in nome else "N", excl, "N", "Investidores em geral", "20", "2.0",
                 f"{pl:.2f}", hoje.isoformat(), "BTG PACTUAL SERVIÇOS FINANCEIROS S.A. DTVM", nome.split(" ")[0] + " GESTÃO DE RECURSOS LTDA", "Multimercados Macro" if "FIM" in nome else "Renda Fixa Duração Baixa Grau de Investimento"])
pd.DataFrame(rows, columns=cols).to_csv(os.path.join(dest, "cad_fi.csv"), sep=";", index=False, encoding="latin-1")

# registro de classes (RCVM 175) com o fundo que falta no cad_fi
reg_cols = ["ID_Registro_Classe", "ID_Registro_Fundo", "CNPJ_Classe", "Codigo_CVM", "Data_Registro", "Data_Constituicao", "Data_Inicio",
            "Tipo_Classe", "Denominacao_Social", "Situacao", "Classificacao", "Classificacao_Anbima", "Exclusivo", "Publico_Alvo"]
reg_rows = [["1", "1", "14.141.414/0001-13", "999", "2025-01-01", "2025-01-01", "2020-05-05", "Classe de Cotas", "SO NO REGISTRO DE CLASSES FIF RF",
             "Em Funcionamento Normal", "Renda Fixa", "Renda Fixa Duração Baixa Soberano", "N", "Investidores em geral"]]
buf = io.StringIO()
pd.DataFrame(reg_rows, columns=reg_cols).to_csv(buf, sep=";", index=False)
with zipfile.ZipFile(os.path.join(dest, "registro_fundo_classe.zip"), "w") as z:
    z.writestr("registro_classe.csv", buf.getvalue().encode("latin-1"))
    z.writestr("registro_fundo.csv", "ID_Registro_Fundo;CNPJ_Fundo;Denominacao_Social\n".encode("latin-1"))

print(f"base sintética em {dest}: {len(meses)} meses, {len(dias)} dias úteis, {len(FUNDOS)} fundos")
