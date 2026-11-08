#!/usr/bin/env bash
# Gera os carrosséis do dia de ponta a ponta e grava na pasta da branch posts. Feito para o GitHub Actions
# (workflow "Gerar posts de resultados" na main), para a tarefa agendada não precisar rodar código: ela só lê o resultado.
#
# Uso: bash post/gerar.sh PASTA_RESULTADOS PASTA_POSTS PASTA_DE_TRABALHO AAAA-MM-DD [TICKER ...]
#   Sem tickers: as entregas novas que selecionar.py devolve (últimas 36 horas, sem as que já têm pasta em posts).
#   Com tickers: refaz esses (por exemplo depois de corrigir o nome em nomes.csv), menos os já publicados.
# Em cada pasta AAAA-MM-DD/TICKER-PERIODO/ ficam 01.jpg ... , legenda.txt e avisos.txt (logo ausente, nome não
# revisado, checagens de checagem.py). Não faz commit: isso fica para quem chama.
set -euo pipefail
AQUI=$(cd "$(dirname "$0")" && pwd)
DADOS=${1:?pasta da branch resultados}; POSTS=${2:?pasta da branch posts}; W=${3:?pasta de trabalho}; DIA=${4:?data AAAA-MM-DD}
shift 4
mkdir -p "$W"
DADOS=$(cd "$DADOS" && pwd); POSTS=$(cd "$POSTS" && pwd); W=$(cd "$W" && pwd)   # o render abre file:// e precisa de caminho absoluto
bash "$AQUI/preparar.sh" "$W/w"

if [ $# -eq 0 ]; then
  python3 -I "$AQUI/selecionar.py" "$DADOS/index.json" --posts "$POSTS" > "$W/selecao.json"
  cat "$W/selecao.json"
  mapfile -t TICKERS < <(python3 -I -c 'import json,sys; [print(t["ticker"]) for t in json.load(open(sys.argv[1]))["tickers"]]' "$W/selecao.json")
else
  TICKERS=("$@")
fi
[ ${#TICKERS[@]} -eq 0 ] && { echo "nada a gerar"; exit 0; }

for T in "${TICKERS[@]}"; do
  J="$DADOS/$T.json"
  [ -f "$J" ] || { echo "sem $J"; continue; }
  # nome usual (nomes.csv, pelo código de 4 letras); sem ele, fica o nome curto da B3 e vai para os avisos
  python3 -I - "$J" "$AQUI/nomes.csv" "$W/$T.json" > "$W/$T.nome" <<'EOF'
import csv, json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
nomes = {r["codigo"]: r["nome"] for r in csv.DictReader(open(sys.argv[2], encoding="utf-8"), delimiter=";")}
cod = d["ticker"][:4]
if cod in nomes:
    d["empresa"] = nomes[cod]
else:
    print(f"nome não revisado: \"{d['empresa']}\" é o nome curto da B3; pôr o nome usual em post/nomes.csv ({cod}) e refazer")
json.dump(d, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False)
EOF
  PER=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["periodo"])' "$W/$T.json")
  CHAVE="$T-$PER"
  # refazer: apaga a versão anterior ainda não publicada
  for OLD in "$POSTS"/*/"$CHAVE"; do
    [ -d "$OLD" ] || continue
    if [ -f "$OLD/publicado.json" ]; then echo "$CHAVE já publicado em $OLD: não refaço"; continue 2; fi
    rm -rf "$OLD"
  done
  MAISON_WORK="$W/w" node "$AQUI/empresa.mjs" "$W/$T.json" "$W/saida/$CHAVE" | tee "$W/$T.render"
  python3 -I "$AQUI/para_posts.py" "$W/saida/$CHAVE" "$POSTS" "$DIA" "$CHAVE"
  { cat "$W/$T.nome"; grep '^aviso' "$W/$T.render" || true; python3 -I "$AQUI/checagem.py" "$W/$T.json"; } \
    | sed '/^$/d' > "$POSTS/$DIA/$CHAVE/avisos.txt"
  echo "== $CHAVE"; cat "$POSTS/$DIA/$CHAVE/avisos.txt"
done
