#!/usr/bin/env python3
"""Ferramenta de apoio: cria/atualiza os arquivos no GitHub, liga o Pages e acompanha as execuções.
Uso: GH_TOKEN=... python gh.py setup|dispatch|runs|jobs [run_id]|status|log|pages
"""
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error

OWNER = os.environ.get("GH_OWNER", "gustavobailly-92")
REPO = os.environ.get("GH_REPO", "hubmaison-comparador-ativos")
TOKEN = os.environ["GH_TOKEN"]
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ARQUIVOS = [  # ordem: workflow por último, para o push dele já encontrar tudo no lugar
    ".gitignore", "README.md", "pipeline/build_data.py", "pipeline/gerar_base_teste.py", "pipeline/gh.py",
    "site/index.html", ".github/workflows/atualizar.yml",
]


def api(method, path, body=None, raw=False):
    url = path if path.startswith("http") else "https://api.github.com" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "maison-hub-setup",
        **({"Content-Type": "application/json"} if data else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read()
            return (txt if raw else (json.loads(txt) if txt else {})), r.status
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")
        return ({"_erro": txt, "_status": e.code} if not raw else txt), e.code


def default_branch():
    r, st = api("GET", f"/repos/{OWNER}/{REPO}")
    return r.get("default_branch", "main") if st == 200 else "main"


def put_file(path, content: bytes, msg, branch=None):
    r, st = api("GET", f"/repos/{OWNER}/{REPO}/contents/{path}" + (f"?ref={branch}" if branch else ""))
    body = {"message": msg, "content": base64.b64encode(content).decode()}
    if branch:
        body["branch"] = branch
    if st == 200 and "sha" in r:
        if base64.b64decode(r.get("content", "").encode()) == content:
            print(f"  = {path} (sem mudança)")
            return
        body["sha"] = r["sha"]
    r, st = api("PUT", f"/repos/{OWNER}/{REPO}/contents/{path}", body)
    print(f"  {'+' if st == 201 else '~' if st == 200 else '!'} {path} [{st}]" + (f" {r.get('_erro','')[:200]}" if st >= 300 else ""))


def setup():
    r, st = api("GET", f"/repos/{OWNER}/{REPO}")
    if st == 404:
        print("repositório não existe; tentando criar…")
        r, st = api("POST", "/user/repos", {"name": REPO, "private": False, "auto_init": False,
                                             "description": "Comparador de Fundos do Maison Hub: dados abertos da CVM e CDI do BCB, atualizados toda semana"})
        print(" ", st, r.get("html_url") or r.get("_erro", "")[:300])
        if st >= 300:
            sys.exit(1)
    else:
        print("repositório:", r.get("html_url"), "| default_branch:", r.get("default_branch"), "| vazio:", r.get("size") == 0)
    branch = default_branch()
    for p in ARQUIVOS:
        content = open(os.path.join(RAIZ, p), "rb").read()
        if p.endswith("atualizar.yml") and branch != "main":
            content = content.replace(b"branches: [main]", f"branches: [{branch}]".encode())
        put_file(p, content, f"Comparador de Fundos: {p}")
        time.sleep(0.6)
    pages()


def pages():
    r, st = api("GET", f"/repos/{OWNER}/{REPO}/pages")
    if st == 404:
        r, st = api("POST", f"/repos/{OWNER}/{REPO}/pages", {"build_type": "workflow"})
        print("pages criado:", st, r.get("html_url") or r.get("_erro", "")[:300])
    elif st == 200:
        print("pages:", r.get("html_url"), "| build_type:", r.get("build_type"), "| status:", r.get("status"))
        if r.get("build_type") != "workflow":
            r2, st2 = api("PUT", f"/repos/{OWNER}/{REPO}/pages", {"build_type": "workflow"})
            print("  ajustado para workflow:", st2)
    else:
        print("pages:", st, r.get("_erro", "")[:300])


def dispatch():
    r, st = api("POST", f"/repos/{OWNER}/{REPO}/actions/workflows/atualizar.yml/dispatches", {"ref": default_branch()})
    print("dispatch:", st, r.get("_erro", "")[:300] if st >= 300 else "ok")


def runs():
    r, st = api("GET", f"/repos/{OWNER}/{REPO}/actions/runs?per_page=6")
    for w in r.get("workflow_runs", []):
        print(f"{w['id']}  {w['status']:<12} {str(w['conclusion']):<10} {w['event']:<18} {w['created_at']}  {w['name']}")


def jobs(run_id=None):
    if not run_id:
        r, st = api("GET", f"/repos/{OWNER}/{REPO}/actions/runs?per_page=1")
        run_id = r["workflow_runs"][0]["id"]
    r, st = api("GET", f"/repos/{OWNER}/{REPO}/actions/runs/{run_id}/jobs")
    for j in r.get("jobs", []):
        print(f"[{j['status']}/{j['conclusion']}] {j['name']}  {j.get('started_at')} → {j.get('completed_at')}")
        for s in j.get("steps", []):
            print(f"    {s['number']:>2} {s['status']:<11} {str(s['conclusion']):<9} {s['name']}")


def conteudo(path):
    r, st = api("GET", f"/repos/{OWNER}/{REPO}/contents/{path}")
    if st != 200:
        return None
    return base64.b64decode(r["content"]).decode("utf-8", errors="replace")


def status():
    print(conteudo("status/ultima-execucao.json") or "sem status registrado ainda")


def log():
    print(conteudo("status/log.txt") or "sem log registrado ainda")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "runs"
    {"setup": setup, "dispatch": dispatch, "runs": runs, "jobs": lambda: jobs(sys.argv[2] if len(sys.argv) > 2 else None),
     "status": status, "log": log, "pages": pages}[cmd]()
