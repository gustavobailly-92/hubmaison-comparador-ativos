"""Checagem leve do RAD da CVM: há ITR/DFP entregue hoje (ou ontem) que os resultados ainda não têm?

Roda no workflow "Checar entregas no RAD" (checar-rad.yml), disparado a cada 30 minutos à noite pela tarefa agendada.
Não baixa documento nenhum: só lista as entregas do dia no RAD (rad.listar, a mesma consulta do pipeline) e compara com o
index.json da branch resultados. Entrega nova é a de uma companhia que já está no index.json com período mais recente
que o do index, ou o mesmo período numa versão mais nova.

Para não disparar o pipeline inteiro à toa:
- com uma execução de "Atualizar dados e publicar" na fila ou rodando, não dispara (ela já vai pegar o que houver);
- entrega que uma execução já concluída teve a chance de pegar (começou pelo menos FOLGA_MIN minutos depois da entrega)
  não conta de novo: se o pipeline falhou nela, fica para a rodada das 08:40, que roda tudo.

Uso: python pipeline/checar_rad.py CAMINHO/index.json
Variáveis: GITHUB_TOKEN e GITHUB_REPOSITORY (para ler as execuções do atualizar.yml), GITHUB_OUTPUT e
GITHUB_STEP_SUMMARY (no Actions). Sai com disparar=true|false em GITHUB_OUTPUT.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rad  # noqa: E402

BRT = timezone(timedelta(hours=-3))
FOLGA_MIN = 20   # uma execução que começou até 20 min depois da entrega pode não ter visto o documento na lista do RAD
WORKFLOW = "atualizar.yml"
EM_CURSO = {"queued", "in_progress", "waiting", "requested", "pending"}


def execucoes() -> list[dict]:
    """Últimas execuções do atualizar.yml (mais recentes primeiro). Sem token, devolve [] e a checagem segue sem elas."""
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return []
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW}/runs?per_page=20",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())["workflow_runs"]


def novas(docs: list[dict], index: dict) -> list[dict]:
    """Entregas do RAD que o index.json ainda não reflete, uma por companhia e período (a versão mais nova)."""
    base: dict[int, tuple[str, int]] = {}
    for c in index["companhias"]:
        atual = (c.get("dt") or "", int(c.get("versao") or 0))
        if c.get("cvm") is not None and atual > base.get(c["cvm"], ("", -1)):
            base[c["cvm"]] = atual
    por_chave: dict[tuple[int, str], dict] = {}
    for d in docs:
        if d["cvm"] not in base or not d["ref"]:
            continue
        dt, ver = base[d["cvm"]]
        if (d["ref"], d["versao"]) <= (dt, ver):
            continue
        k = (d["cvm"], d["ref"])
        if k not in por_chave or d["versao"] > por_chave[k]["versao"]:
            por_chave[k] = d
    return sorted(por_chave.values(), key=lambda d: d["entrega"])


def _utc(entrega: str) -> datetime:
    """'AAAA-MM-DDTHH:MM' do RAD (hora de Brasília) em UTC. Sem hora, meia-noite (conta como tentada mais cedo)."""
    fmt = "%Y-%m-%dT%H:%M" if "T" in entrega else "%Y-%m-%d"
    return datetime.strptime(entrega, fmt).replace(tzinfo=BRT).astimezone(timezone.utc)


def main() -> None:
    index = json.load(open(sys.argv[1], encoding="utf-8"))
    hoje = datetime.now(BRT).date()
    docs: list[dict] = []
    s = rad._Sessao()
    for dia in (hoje - timedelta(days=1), hoje):   # um dia por consulta, como o pipeline
        docs += rad.listar(dia, dia, s)
    pend = novas(docs, index)

    runs = execucoes()
    em_curso = [r for r in runs if r["status"] in EM_CURSO]
    concluidas = [datetime.fromisoformat(r["run_started_at"].replace("Z", "+00:00"))
                  for r in runs if r["status"] == "completed" and r.get("run_started_at")]
    folga = timedelta(minutes=FOLGA_MIN)
    ja_tentadas = [d for d in pend if any(ini >= _utc(d["entrega"]) + folga for ini in concluidas)]
    a_disparar = [d for d in pend if d not in ja_tentadas]

    disparar = bool(a_disparar) and not em_curso
    if not a_disparar:
        motivo = "nenhuma entrega nova" if not pend else "as entregas novas já passaram por uma execução concluída"
    elif em_curso:
        motivo = (f"já há uma atualização em curso, execução {em_curso[0]['id']}; se ela não pegar estas entregas, "
                  "a próxima checagem dispara de novo")
    else:
        motivo = f"{len(a_disparar)} entrega(s) nova(s): disparar a atualização"

    linhas = [f"### Checagem do RAD ({datetime.now(BRT):%d/%m/%Y %H:%M})",
              f"- ITR/DFP no RAD ontem e hoje: {len(docs)}; das companhias acompanhadas, ainda fora dos resultados: {len(pend)}",
              f"- Decisão: **{'disparar' if disparar else 'não disparar'}** ({motivo})"]
    for d in pend:
        marca = " (já tentada)" if d in ja_tentadas else ""
        linhas.append(f"  - {d['empresa'][:40]} · {d['doc']} {d['ref']} v{d['versao']} · entregue {d['entrega'].replace('T', ' ')}{marca}")
    texto = "\n".join(linhas)
    print(texto)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8").write(texto + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8").write(f"disparar={'true' if disparar else 'false'}\n")


if __name__ == "__main__":
    main()
