# Carrossel mensal do IPCA (@maison.invest)

Kit para o Claude Code publicar, todo mês, o carrossel do IPCA no Instagram da Maison Invest. O layout é fixo; só os dados mudam.

## Estrutura

```
dados/ipca-AAAA-MM.json       contrato de dados do mês (exemplos: ipca-2026-08.json, ipca-2026-10.json)
dados/projecoes-AAAA-MM.json  opcional: projeções de Reuters e Bloomberg, à mão (sem ele, usa o Focus mensal)
fetch_ipca.py                 monta o JSON do mês a partir do SIDRA e do Focus
template/ipca-carrossel.html  template único; desenha os 8 slides a partir do JSON
fonts/                        Montserrat (substituta da Gotham), embutida no render
logo-invest-xp-negativo.svg   lockup Maison Invest | XP, versão para fundo escuro
render.py                     valida o JSON e gera saida/AAAA-MM/NN-slide.png e .jpg
legenda.py                    escreve e valida a legenda a partir do JSON
hoje.py                       diz ao workflow se há IPCA novo para publicar
saida/AAAA-MM/legenda.txt     legenda do post
```

Rodar: `pip install playwright && playwright install chromium`, depois `python3 render.py dados/ipca-AAAA-MM.json` (ou `--chrome /caminho/do/chrome` para usar o Chrome instalado).

## Os slides (1080 x 1350, formato 4:5 do feed)

Sem contador de página (o Instagram já mostra). Rodapés citam só a instituição ("Fonte: IBGE"), sem número de tabela.

| # | Slide | Título (curto, fixo) | Subtítulo (análise automática) |
|---|---|---|---|
| 1 | Capa: número do mês e 12 meses; data de divulgação discreta no rodapé | IPCA de [mês] | sem análise |
| 2 | Comparativo das projeções: régua com piso, teto e mediana + um parágrafo curto (só aparece com `projecoes`) | Abaixo/Acima do esperado | sem subtítulo |
| 3 | Últimos 12 meses, com média | Últimos 12 meses | acumulado em 12 meses e posição frente ao teto da meta |
| 4 | Histórico anual, 20 anos + ano corrente com a projeção do Focus | Inflação ano a ano | média do período e pico |
| 5 | IPCA+6% e CDI, 20 anos acumulados (como o comparador do hub) | IPCA+6% e CDI em 20 anos | quanto cada um acumulou |
| 6 | Impacto de cada grupo no índice, com ícones e barra de peso | Impacto de cada grupo | quem pressionou e quem segurou |
| 7 | Grupo a grupo, mês atual x anterior | Grupo a grupo | o grupo com a maior virada |
| 8 | 16 regiões + Brasil, com 12 meses | Por região | sem subtítulo |
| 9 | Matriz região × grupo com ícones; 5 maiores altas e quedas contornadas | Região × grupo | sem subtítulo |
| 10 | O mesmo mês nos últimos 10 anos | [Mês] na história | posição no ranking e média |
| 11 | Expectativas: quanto falta para a projeção do Focus | Boletim Focus | quanto falta e o boletim usado |
| 12 | Fechamento: o que é o IPCA, CTA, lema, identificação XP | IPCA | fixo |

Títulos curtos podem ser trocados em `textos` com as chaves `<slide>_titulo_curto` (`projecoes`, `doze`, `anual`, `cdi`, `contribuicao`, `grupos`, `regioes`, `matriz`, `historia`, `expectativas`); as análises dos subtítulos, com `contribuicao_titulo`, `grupos_titulo`, `regioes_titulo`, `matriz_titulo`, `historia_titulo` e `expectativas_titulo`.

## Fluxo mensal

1. `python3 fetch_ipca.py --divulgacao AAAA-MM-DD --projecoes dados/projecoes-AAAA-MM.json` monta `dados/ipca-AAAA-MM.json` direto do SIDRA (tabelas 7060 e 1737) e da API Olinda do Banco Central (Focus).
2. `dados/projecoes-AAAA-MM.json` é o único arquivo feito à mão: mediana e intervalo das projeções (Bloomberg, Reuters) e projeções de casas (XP), tirados das notícias do dia. Sem esse arquivo, o slide 2 some e o resto sai normalmente. Use `"intervalo_confirmado": false` enquanto o intervalo não tiver fonte conferida, e não publique sozinho nesse caso.
3. `python3 render.py dados/ipca-AAAA-MM.json` gera os PNGs e JPEGs.
4. `python3 legenda.py dados/ipca-AAAA-MM.json > saida/AAAA-MM/legenda.txt` escreve e valida a legenda (sem identificação da XP nem ouvidoria).

## De onde vêm os dados (conferir na primeira execução)

| Campo | Fonte | Observação |
|---|---|---|
| `indice.variacao`, `acumulado_ano`, `acumulado_12m`, `grupos[].atual/anterior/peso`, `regioes[]` | IBGE/SIDRA, tabela 7060 (variáveis 63, 69, 2265 e 66; classificação 315 para os grupos; níveis Brasil, regiões metropolitanas e municípios) | Usar o peso exato do mês (variável 66), não o arredondado; aí a soma das contribuições fecha com o índice |
| `historico_12m` | SIDRA 7060, Brasil, variável 63 | `render.py` recusa o JSON se os 12 meses não compuserem o acumulado informado |
| `mesmo_mes_anos_anteriores` | SIDRA 1737 (série longa, variável 63) | A 7060 começa em 2020; anos anteriores vêm da 1737 |
| `mediana_esperada` | Hoje vem da mediana das casas de análise (fonte do relatório da Wealth) | Alternativa automatizável: mediana mensal do Focus (API Olinda do BCB, ExpectativaMercadoMensais) da véspera da divulgação; se trocar a fonte, ajustar o rótulo "mediana do mercado" |
| `cdi_ipca6` | BCB SGS 4391 (CDI mensal) e IBGE 1737 (IPCA mensal) | IPCA + 6% composto mês a mês: (1 + IPCA) x 1,06^(1/12). Em out/2026 dá CDI 591,7% (o comparador do hub mostra 591,2%) e IPCA + 6% 852,6% (o hub mostra 865,4%; a diferença vem do método diário e da defasagem do IPCA no hub) |
| `focus` | BCB, API Olinda, ExpectativasMercadoAnuais, indicador IPCA, último boletim antes da divulgação | `ipca_ano_corrente_anterior` é o boletim da semana anterior |

Códigos conferidos contra o SIDRA e a API Olinda em 12/11/2026, na montagem do IPCA de outubro. Os pesos regionais são fixos no `fetch_ipca.py` (aproximados, IBGE).

## Recorrência e publicação

Instalado no repositório `hubmaison-comparador-ativos`, junto com os resultados da B3 e as datas comemorativas: pasta `ipca-mensal/` na main e `.github/workflows/postar-ipca.yml`. Mesmo token (`IG_ACCESS_TOKEN`), mesma fila (`concurrency: instagram`) e mesmo `instagram/postar.py`, que passou a aceitar pastas `AAAA-MM-DD/IPCA-AAAA-MM`.

- O workflow roda nos dias 7 a 16, dias úteis, às 9h30 e às 12h (Brasília). O IBGE divulga às 9h.
- `hoje.py` confere se o SIDRA já tem o mês anterior e se ele ainda não tem `publicado.json` na branch `posts`. Sem IPCA novo, o workflow termina sem fazer nada.
- Com IPCA novo: `fetch_ipca.py` (SIDRA, Focus e CDI), `render.py`, `legenda.py`; as telas viram `01.jpg` a `12.jpg` em `posts/AAAA-MM-DD/IPCA-AAAA-MM/` e saem pelo `postar.py`.
- Projeções: no automático, a régua usa o Focus mensal (mediana, mínimo e máximo da última coleta antes da divulgação). Se existir `dados/projecoes-AAAA-MM.json` na main (Reuters, Bloomberg), ele tem prioridade.
- Qualquer erro de validação (12 meses que não fecham, legenda com travessão ou palavra de risco, limite do Instagram) para o workflow antes de publicar.
- Para publicar à mão um mês específico: Actions, "Publicar IPCA do mês", `mes` = AAAA-MM e `divulgacao` = data do IBGE.
- Ou editar `ipca-mensal/publicar.txt` na main com `AAAA-MM AAAA-MM-DD` (mês e data da divulgação): o push dispara a publicação daquele mês. Mês já publicado é ignorado.

## Antes de publicar (checagem automática mínima)

- `render.py` passou sem erro de validação.
- Legenda sem "garantido", "renda certa", "sem risco", "recomendamos" ou nome de ativo específico.
- Se algum título automático parecer estranho para o mês, o post fica pendente de revisão em vez de sair sozinho.
