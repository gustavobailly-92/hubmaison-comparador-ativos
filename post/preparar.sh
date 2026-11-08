#!/usr/bin/env bash
# Prepara a pasta de trabalho do carrossel de resultados: estilos, fontes Montserrat (npm), marcas da Maison (da skill
# maison, que precisa estar instalada na conta) e a biblioteca de logos das empresas.
# Uso: bash post/preparar.sh /caminho/da/pasta
set -euo pipefail
AQUI=$(cd "$(dirname "$0")" && pwd)
W=${1:?informe a pasta de trabalho}
mkdir -p "$W/assets" "$W/fonts" "$W/logos"
cp "$AQUI/styles.css" "$W/"
python3 -I "$AQUI/placa.py" "$AQUI/logos" "$W/logos"

if [ ! -f "$W/fonts/montserrat-latin-700-normal.woff2" ]; then
  (cd "$W" && { [ -f package.json ] || npm init -y >/dev/null; } && npm install --silent @fontsource/montserrat@5.0.19 >/dev/null)
  cp "$W"/node_modules/@fontsource/montserrat/files/montserrat-latin-{200,300,400,500,600,700}-normal.woff2 "$W/fonts/"
fi

L=$(find / -path "*maison/assets/logos/invest-xp/cor-negativo.png" 2>/dev/null | head -1 || true)
if [ -z "$L" ]; then echo "ERRO: logos da Maison não encontrados (a skill maison precisa estar instalada)"; exit 1; fi
L=$(dirname "$L")/..
python3 - "$L" "$W/assets" <<'EOF'
import sys
from PIL import Image
import numpy as np
L, A = sys.argv[1], sys.argv[2]
Image.open(f"{L}/seguros/horizontal-negativo.png").convert("RGBA").crop((0, 0, 823, 560)).save(f"{A}/symbol.png")
Image.open(f"{L}/invest-xp/cor-negativo.png").convert("RGBA").save(f"{A}/invest-xp.png")
n = np.random.default_rng(7).normal(128, 40, (256, 256)).clip(0, 255).astype("uint8")
Image.fromarray(np.dstack([n, n, n, np.full((256, 256), 230, "uint8")]), "RGBA").save(f"{A}/grain.png")
EOF
echo "pasta pronta: $W"
