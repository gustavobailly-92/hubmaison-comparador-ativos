# Comparador de Ativos · Maison Hub

Comparador de fundos de investimento com o CDI, publicado em **hubmaison.com/comparadordeativos**.
Os dados vêm dos dados abertos da CVM (informe diário e cadastro de fundos) e do Banco Central (CDI, série SGS 12),
e são regenerados **toda segunda-feira às 06:00 (Brasília)** por este repositório.

## Como funciona

```
pipeline/build_data.py   baixa CVM + BCB, calcula as métricas e grava dist/data/
site/index.html          a página (autocontida), lê dist/data/ ou o GitHub Pages deste repositório
.github/workflows/       agendamento semanal + publicação no GitHub Pages
```

Saída do pipeline (`dist/data/`):

| Arquivo | Conteúdo |
|---|---|
| `meta.json` | calendário de dias úteis, índice acumulado do CDI, semanas, data de referência |
| `index.json` | índice de busca: um registro compacto por fundo (CNPJ, nome, classe, gestor, PL, cotistas, 12 meses) |
| `fundos/<cnpj>.json` | cotas diárias, patrimônio e cotistas semanais, métricas por janela (12/24/36/48 meses), retornos mensais |
| `status.json` | contagens e avisos da execução |

Métricas por janela: rentabilidade acumulada, CDI no mesmo período e % do CDI, volatilidade anualizada,
índice de Sharpe (retorno anualizado menos CDI, dividido pela volatilidade), drawdown máximo e atual,
consistência (% de meses fechados acima do CDI), meses positivos, melhor e pior mês.

Universo publicado: fundos em funcionamento normal, não exclusivos, com pelo menos 10 cotistas e informe recente.

## Rodar localmente

```bash
pip install pandas numpy
python pipeline/build_data.py --out dist/data --cache cache      # ~15 min na primeira vez
cp -r site/. dist/ && cd dist && python -m http.server 8000      # http://localhost:8000
```

Para testar sem internet, há uma base sintética no mesmo formato da CVM:

```bash
python pipeline/gerar_base_teste.py /tmp/base_teste
python pipeline/build_data.py --offline /tmp/base_teste --out dist/data
```

## Publicação

- **Dados**: GitHub Pages deste repositório (`https://gustavobailly-92.github.io/hubmaison-comparador-ativos/`), regravado a cada execução.
- **Página**: o mesmo `site/index.html` vai para a Hostinger em `hubmaison.com/comparadordeativos/index.html`.
  Fora do GitHub Pages a página lê os dados pela URL absoluta acima (constante `REPO_DATA` no início do script).

Para forçar uma atualização fora do horário: aba **Actions** → "Atualizar dados e publicar" → **Run workflow**.
