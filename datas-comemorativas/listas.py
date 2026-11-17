#!/usr/bin/env python3
"""Monta, para uma data comemorativa, a lista de clientes que recebem a mensagem individual.

Roda no computador do Gustavo, com um export CSV ou XLSX da Base XP do CRM Maison (ou do Positivador).
Nada sai do computador: o resultado é um CSV com nome, telefone, assessor e a mensagem já personalizada,
para o assessor enviar um a um (sem disparo em massa: CDC 54-C e LGPD).

Uso:
  python3 listas.py criancas clientes.csv
  python3 listas.py maes clientes.xlsx --data 2027-05-09
  python3 listas.py --todas clientes.csv          # resumo de quantos clientes cada data alcança

As colunas são reconhecidas pelo nome (sem acento, maiúsculas ou minúsculas). O que o script procura:
  nome          nome | cliente | nome do cliente
  telefone      telefone | celular | tel | whatsapp
  assessor      assessor | cod assessor | codass
  nascimento    data de nascimento | nascimento | dt nascimento
  sexo          sexo | genero
  profissao     profissao | ocupacao
  estado_civil  estado civil
  filhos        filhos | tem filhos   (sim/não ou número; campo a criar no CRM)
  netos         netos | tem netos     (sim/não ou número; campo a criar no CRM)
  status        status | situacao     (linhas "inativo" ou "encerrado" ficam de fora)
  pais_residencia  pais de residencia | pais | country   (para Thanksgiving, 4 de julho e 14 de julho)

Profissões e especialidades médicas usam a regra profissao:<regex> sobre a profissão cadastrada
(sem acento, minúsculas); a Mulher Empresária usa profissao_f:<regex>, que exige também sexo feminino.

Regra que não muda: nada é inferido. Sem o campo, a lista daquela regra sai vazia e o script diz o que falta.
Maternidade, paternidade e netos nunca saem da idade ou do sexo.
"""
import argparse, csv, datetime as dt, json, os, re, sys, unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
ALIAS = {
    "nome": ["nome", "cliente", "nome do cliente", "nome cliente"],
    "telefone": ["telefone", "celular", "tel", "whatsapp", "telefone celular"],
    "assessor": ["assessor", "cod assessor", "codass", "codigo assessor", "nome assessor"],
    "nascimento": ["data de nascimento", "nascimento", "dt nascimento", "data nascimento"],
    "sexo": ["sexo", "genero"],
    "profissao": ["profissao", "ocupacao"],
    "estado_civil": ["estado civil", "estadocivil"],
    "filhos": ["filhos", "tem filhos", "qtd filhos"],
    "netos": ["netos", "tem netos", "qtd netos"],
    "status": ["status", "situacao"],
    "pais_residencia": ["pais de residencia", "pais residencia", "pais", "country", "residencia"],
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def ler(caminho):
    if caminho.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        ws = load_workbook(caminho, read_only=True, data_only=True).active
        linhas = list(ws.iter_rows(values_only=True))
        cab, corpo = linhas[0], linhas[1:]
        return [dict(zip(cab, l)) for l in corpo]
    raw = open(caminho, "rb").read()
    txt = raw.decode("utf-8-sig") if raw[:3] == b"\xef\xbb\xbf" else raw.decode("utf-8", "replace")
    sep = ";" if txt.split("\n", 1)[0].count(";") > txt.split("\n", 1)[0].count(",") else ","
    return list(csv.DictReader(txt.splitlines(), delimiter=sep))


def mapear(cabecalho):
    m = {}
    nc = {norm(c): c for c in cabecalho if c is not None}
    for campo, nomes in ALIAS.items():
        for n in nomes:
            if n in nc:
                m[campo] = nc[n]; break
    return m


def data_br(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v if isinstance(v, dt.date) and not isinstance(v, dt.datetime) else v.date()
    v = str(v or "").strip()[:10]
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(v, f).date()
        except ValueError:
            pass
    return None


def idade(nasc, em):
    return em.year - nasc.year - ((em.month, em.day) < (nasc.month, nasc.day))


def sim(v):
    v = norm(v)
    return v in ("sim", "s", "yes", "x", "true", "1") or (v.isdigit() and int(v) > 0)


def regra_aplica(regra, r, m, em):
    """Devolve (entra, motivo_faltante). motivo_faltante != None quando falta campo para decidir."""
    g = lambda c: r.get(m[c]) if c in m else None
    if regra == "todos":
        return True, None
    if regra == "nenhuma":
        return False, None
    if regra.startswith("pais:"):
        if "pais_residencia" not in m: return False, "pais_residencia"
        return bool(re.search(regra[5:], norm(g("pais_residencia")))), None
    if regra == "sexo_f":
        if "sexo" not in m: return False, "sexo"
        return norm(g("sexo")).startswith("f"), None
    if regra.startswith(("profissao:", "profissao_f:")):  # profissões e especialidades: regex sobre a profissão cadastrada
        if "profissao" not in m: return False, "profissao"
        ok = bool(re.search(regra.split(":", 1)[1], norm(g("profissao"))))
        if regra.startswith("profissao_f:"):  # Dia da Mulher Empresária: profissão e sexo feminino
            if "sexo" not in m: return False, "sexo"
            ok = ok and norm(g("sexo")).startswith("f")
        return ok, None
    if regra == "profissao_aposentado":
        if "profissao" not in m: return False, "profissao"
        return "aposentad" in norm(g("profissao")), None
    if regra == "idade_60":
        if "nascimento" not in m: return False, "nascimento"
        n = data_br(g("nascimento"))
        return bool(n and idade(n, em) >= 60), None
    if regra == "casados":
        if "estado_civil" not in m: return False, "estado_civil"
        ec = norm(g("estado_civil"))
        return ec.startswith("casad") or "uniao estavel" in ec or "convivente" in ec, None
    if regra in ("maes", "pais"):
        if "filhos" not in m: return False, "filhos"
        if "sexo" not in m: return False, "sexo"
        alvo = "f" if regra == "maes" else "m"
        return sim(g("filhos")) and norm(g("sexo")).startswith(alvo), None
    if regra == "avos":
        if "netos" not in m: return False, "netos"
        return sim(g("netos")), None
    if regra == "criancas":
        # dois grupos: quem tem filhos marcados, e cadastros de menores já existentes (fala-se com o responsável)
        tem = "filhos" in m and sim(g("filhos"))
        menor = False
        if "nascimento" in m:
            n = data_br(g("nascimento"))
            menor = bool(n and idade(n, em) < 18)
        falta = None if ("filhos" in m or "nascimento" in m) else "filhos ou nascimento"
        return tem or menor, falta
    raise SystemExit(f"regra desconhecida: {regra}")


def personaliza(msg, r, m):
    nome = str(r.get(m.get("nome"), "") or "").strip().split(" ")[0].title() or "tudo bem"
    assessor = str(r.get(m.get("assessor"), "") or "").strip() or "Equipe"
    return msg.replace("{nome}", nome).replace("{assessor}", assessor)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?")
    ap.add_argument("arquivo")
    ap.add_argument("--data", help="data de referência para idade (padrão: próxima ocorrência)")
    ap.add_argument("--todas", action="store_true")
    a = ap.parse_args()

    cal = {d["slug"]: d for d in json.load(open(os.path.join(AQUI, "calendario.json"), encoding="utf-8"))["datas"]}
    linhas = ler(a.arquivo)
    if not linhas:
        raise SystemExit("arquivo vazio")
    m = mapear(linhas[0].keys())
    ativos = [r for r in linhas if not ("status" in m and re.search(r"inativ|encerrad|cancelad", norm(r.get(m["status"]))))]
    em = dt.date.fromisoformat(a.data) if a.data else dt.date.today()
    print(f"{len(linhas)} linhas, {len(ativos)} ativas. Colunas reconhecidas: {', '.join(f'{k}={v}' for k, v in m.items())}")
    if "nome" not in m or "telefone" not in m:
        print("ATENÇÃO: sem coluna de nome ou telefone a lista não serve para envio.")

    slugs = list(cal) if a.todas else [a.slug]
    for slug in slugs:
        e = cal[slug]
        regra = e["lista"]["regra"]
        entram, faltas = [], set()
        for r in ativos:
            ok, falta = regra_aplica(regra, r, m, em)
            if falta: faltas.add(falta)
            if ok: entram.append(r)
        aviso = f" | falta o campo: {', '.join(sorted(faltas))}" if faltas else ""
        print(f"{slug:<11} regra {regra:<20} {len(entram):>5} clientes{aviso}")
        if a.todas or not e.get("mensagem_cliente"):
            continue
        saida = os.path.join(AQUI, "listas", f"{em.isoformat()}-{slug}.csv")
        os.makedirs(os.path.dirname(saida), exist_ok=True)
        with open(saida, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["grupo", "nome", "telefone", "assessor", "mensagem"])
            for r in entram:
                msg, grupo = e["mensagem_cliente"], "cliente"
                if regra == "criancas" and "nascimento" in m:
                    n = data_br(r.get(m["nascimento"]))
                    if n and idade(n, em) < 18:
                        msg, grupo = e["mensagem_cliente_menor"], "cadastro de menor (falar com o responsável)"
                w.writerow([grupo, r.get(m.get("nome"), ""), r.get(m.get("telefone"), ""),
                            r.get(m.get("assessor"), ""), personaliza(msg, r, m)])
        print(f"   -> {saida}")


if __name__ == "__main__":
    main()
