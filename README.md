# Comparador de Ativos · Maison Hub

Comparador de fundos de investimento, títulos do Tesouro Direto, renda fixa e benchmarks, publicado em **hubmaison.com/comparadordeativos**.
Os dados vêm dos dados abertos da CVM (informe diário e cadastro de fundos), do Banco Central (CDI, IPCA, poupança e PTAX pelo SGS),
do Tesouro Transparente (preços e taxas do Tesouro Direto), da B3 (Ibovespa e IFIX), da Nasdaq (Nasdaq 100, S&P 500 via ETF SPY, MSCI World via URTH,
ouro via GLD e inteligência artificial via AIQ) e da Coinbase (bitcoin em dólar, convertido pela PTAX), com CoinGecko, Yahoo Finance, Stooq e FRED como reservas,
e são regenerados **de terça a sábado às 10:07 (Brasília)** por este repositório, logo após a publicação da CVM (08:00).
Os últimos 12 meses de informes da CVM são baixados de novo a cada execução, para absorver as retificações.

## Como funciona

```
pipeline/build_data.py     baixa CVM + BCB, calcula as métricas e grava dist/data/
pipeline/fontes_extras.py  benchmarks (BCB, B3, Nasdaq, Coinbase), Tesouro Direto e a lista de fundos da XP
pipeline/coes.json         catálogo dos COEs da prateleira da XP (termos lidos das lâminas e dos DIEs)
pipeline/xp_fundos.csv     fundos da plataforma XP (tipo, classe, risco, benchmark, taxas, liquidez)
site/index.html            a página (autocontida), lê dist/data/ ou o GitHub Pages deste repositório
.github/workflows/         agendamento de terça a sábado + publicação no GitHub Pages
```

Saída do pipeline (`dist/data/`):

| Arquivo | Conteúdo |
|---|---|
| `meta.json` | calendário de dias úteis, CDI acumulado e diário, semanas, data de referência, lista de benchmarks, títulos do Tesouro, históricos e tipos XP |
| `index.json` | índice de busca: um registro compacto por fundo (CNPJ, nome, classe, gestor, PL, cotistas, 12 meses, campos XP) |
| `fundos/<cnpj>.json` | cotas diárias, patrimônio e cotistas semanais, métricas por janela (12/24/36/48 meses), retornos mensais, dados XP |
| `bench/<id>.json` | benchmarks alinhados ao calendário: ipca, poupanca, dolar, ibov, ifix, sp500, sp500brl, nasdaq, nasdaqbrl, msci, mscibrl, ouro, ourobrl, btc |
| `tesouro/<id>.json` | títulos do Tesouro Direto: preço, taxa semanal, duration, histórico de taxa (mín., mediana, máx.) |
| `hist/<id>.json` | histórico longo dos ativos-objeto (GLD, AIQ, S&P 500, Nasdaq 100, Ibovespa, URTH) para cenários de COE |
| `coes.json` | cópia do catálogo de COEs (estrutura, ativo-objeto, participação, proteção, prazo, links da lâmina e do DIE) |
| `status.json` | contagens e avisos da execução |

Métricas por janela: rentabilidade acumulada, CDI no mesmo período e % do CDI, volatilidade anualizada,
índice de Sharpe (retorno anualizado menos CDI, dividido pela volatilidade), drawdown máximo e atual,
consistência (% de meses fechados acima do CDI), meses positivos, melhor e pior mês.

Universo publicado: fundos em funcionamento normal, não exclusivos, com pelo menos 10 cotistas e informe recente.

A página ainda calcula no navegador: séries sintéticas de renda fixa (% do CDI, prefixado, IPCA+), períodos personalizados e o período
máximo (desde a primeira cota do ativo mais recente da comparação), a aba **Perspectivas** (projeções lognormais com premissas de CDI,
IPCA, excesso de retorno e variação de taxa do Tesouro) e a análise dos COEs da prateleira da XP (payoff, histórico do ativo-objeto,
cenários e leitura de outras lâminas em PDF).

O catálogo `pipeline/coes.json` é mantido à mão: os COEs em oferta mudam a cada reserva e os termos vêm da lâmina (material publicitário)
e do DIE de cada um, disponíveis em "Detalhes do ativo" no Hub XP.

## Rodar localmente

```bash
pip install pandas numpy
python pipeline/build_data.py --out dist/data --cache cache      # ~15 min na primeira vez
cp -r site/. dist/ && cd dist && python -m http.server 8000      # http://localhost:8000
```

Para testar sem internet, há uma base sintética no mesmo formato da CVM (benchmarks e Tesouro também sintéticos):

```bash
python pipeline/gerar_base_teste.py /tmp/base_teste
python pipeline/build_data.py --offline /tmp/base_teste --out dist/data
```

## Publicação

- **Dados**: GitHub Pages deste repositório (`https://gustavobailly-92.github.io/hubmaison-comparador-ativos/`), regravado a cada execução.
- **Página**: o mesmo `site/index.html` vai para a Hostinger em `hubmaison.com/comparadordeativos/index.html`.
  Fora do GitHub Pages a página lê os dados pela URL absoluta acima (constante `REPO_DATA` no início do script).

Para forçar uma atualização fora do horário: aba **Actions** → "Atualizar dados e publicar" → **Run workflow**.
O resultado de cada execução fica em `status/ultima-execucao.json` e `status/log.txt`.
