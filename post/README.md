# Post de resultados da Maison Invest

Carrossel de 7 ou 8 telas (1080x1350) e legenda sobre o resultado trimestral de uma empresa listada, a partir dos
JSONs que o workflow publica na branch `resultados`. Este README é o procedimento de referência: a tarefa agendada
diária e a skill `resultado-empresa-maison` seguem o que está aqui.

## Trava regulatória (vale para toda execução)

- Conteúdo sobre emissor determinado pode ser enquadrado como análise (Res. CVM 20). O post é frio: números, variações e
  fontes, sem adjetivo, sem opinião, sem previsão e sem "oportunidade", "barata", "cara", "vale a pena", "recomendamos".
- Nunca publicar sozinho. Cada carrossel vai para o Gustavo aprovar. O modelo passa pelo compliance da XP antes do
  primeiro post.
- Setas com a mesma cor para alta e queda; nada de verde e vermelho.
- Toda peça leva a fonte das demonstrações, a dos múltiplos com a data da cotação e a linha legal da Invest com a
  ouvidoria da XP (já no modelo). A fonte dos múltiplos é o cálculo próprio com dados da B3 e da CVM; não atribuir a
  terceiros números que não são deles.
- Dado ausente fica "n/d" e é avisado. Nunca estimar nem completar de memória.

## Telas

1. Capa: marca da Invest, logo da empresa (sem logo aprovada, o nome da empresa em texto), "Resultado do 3T26 · data de entrega à CVM" e o indicador com a maior
   variação contra o mesmo trimestre do ano anterior, para cima ou para baixo, entre receita, EBITDA, lucro, PL,
   dívida e ativo (n.m. fica de fora): o valor do trimestre em destaque, a variação e o valor do ano anterior. Sem
   variação mensurável, a capa mostra o destaque do JSON (receita; lucro para bancos e seguradoras).
2. O trimestre em números, contra o mesmo trimestre do ano anterior.
3. 12, 24 e 36 meses: receita, EBITDA e lucro somados em 12 meses; PL, dívida e ativo no fim do trimestre.
4. e 5. Barras por trimestre (13 trimestres) com o valor em cima; em destaque o mesmo trimestre de cada ano, com a
   variação dentro da barra. Com até 3 indicadores (bancos), uma tela só.
6. P/VP em destaque, P/L e EV/EBITDA de hoje.
7. Preço, P/VP e EV/EBITDA mês a mês em 36 meses, com 12, 24 e 36 meses antes (sem EV/EBITDA para financeiras).
8. Fontes, definição do EBITDA e linha legal.

Convenções: "n.m." (não mensurável) quando há valor negativo em um dos períodos, quando a variação passa de 999% ou
quando o múltiplo passa de 100x ou tem PL, lucro ou EBITDA de 12 meses negativo; cada tela traz a nota. EBITDA =
resultado antes do resultado financeiro e dos tributos (DRE 3.05) mais depreciação e amortização da DVA, sem os
ajustes que a empresa divulga.

## Execução

```bash
REPO=https://github.com/gustavobailly-92/hubmaison-comparador-ativos
B=$HOME/post-resultados; rm -rf $B && mkdir -p $B && cd $B
git clone -q --depth 1 --branch post-template $REPO codigo
git clone -q --depth 1 --branch resultados $REPO dados
git clone -q --depth 1 --branch posts $REPO posts
bash codigo/post/preparar.sh $B/w
python3 codigo/post/selecionar.py dados/index.json --posts posts      # entregas à CVM das últimas 36 horas, sem repetir
MAISON_WORK=$B/w node codigo/post/empresa.mjs dados/<TICKER>.json saida/<TICKER>-<periodo>
python3 -I codigo/post/para_posts.py saida/<TICKER>-<periodo> posts <AAAA-MM-DD> <TICKER>-<periodo>
```

Sai `01.png` a `08.png` (ou `07.png`) e `legenda.txt`; `para_posts.py` converte para JPEG na branch `posts`
(`AAAA-MM-DD/TICKER-PERIODO/`), de onde o workflow **Publicar no Instagram** (branch main) publica depois do ok.
Para uma empresa específica, pular o `selecionar.py` e usar o JSON do ticker. Capa de notícia: no JSON,
`"capa": {"tipo": "noticia"}` e `"noticia": {"titulo", "data", "fonte"}`, só com fato documentado (fato relevante ou
comunicado na CVM).

### Mesmo dia

Com o RAD (PR #2 do comparador), o `index.json` traz cada ITR/DFP no dia da entrega, com a hora (`hora`). 92% das
companhias divulgam após o fechamento, e o ITR chega à CVM entre 18h e 22h; as que divulgam antes da abertura entregam
de madrugada ou cedo. Para pegar os números logo depois:

1. Disparar a atualização: `gh workflow run atualizar.yml --repo gustavobailly-92/hubmaison-comparador-ativos --ref main`
   e esperar a execução terminar (uns 15 minutos); clonar `resultados` de novo.
2. Selecionar, renderizar, levar para `posts` e enviar ao Gustavo.
3. Só depois do ok dele, para cada carrossel aprovado:
   `gh workflow run postar-instagram.yml --repo gustavobailly-92/hubmaison-comparador-ativos --ref main -f pasta=AAAA-MM-DD/TICKER-PERIODO`

O calendário da temporada (data e horário previstos, com a fonte de cada data) fica em `post/calendario/`.

## Antes de entregar

- Olhar todas as telas: texto cortado, sobreposição, "n/d" inesperado, logo ilegível.
- Nome da empresa: o índice traz o nome curto da B3 ("Santander Br", "Ambev S/A", "Jsl"); corrigir `empresa` no JSON
  para o nome usual ("Santander Brasil", "Ambev", "JSL") antes de renderizar.
- Conferir no JSON: `entrega.versao` (reapresentação aparece na linha de fonte), `financeira`, `multiplos.data_cotacao`.
- Valor muito fora da escala da empresa (receita que dobra num trimestre, lucro maior que a receita): avisar o Gustavo
  em vez de entregar como pronto.
- Entregar as telas e a legenda com o aviso de que precisa do ok antes de postar, e listar o que faltou (logo, dado).

## Logos

Diretório em `post/logos/`, uma companhia por código de 4 letras do ticker (ex.: `VALE.png`), 422 companhias:

| Pasta | Conteúdo |
|---|---|
| `original/` | placa da coleção pública github.com/alextchatalov/logos-acoes-b3 (set/2026), PNG 450x450 opaco |
| `cor/` | cor original, fundo transparente, recortado |
| `branco/` | branco, fundo transparente, recortado (para o fundo azul escuro) |
| `oficial/` | opcional: arquivo oficial da empresa (`.svg` ou `.png`, versão para fundo escuro); tem prioridade na capa |
| `indice.csv` | código, tickers, razão social, fonte, fundo, versão da capa e status |

- `versoes.py` gera `cor/` e `branco/` a partir de `original/` (tira o fundo por cor; em placa colorida, pelo brilho,
  e limpa o ruído do JPEG). A versão branca é uma conversão, não o arquivo negativo da empresa.
- Coluna `capa`: `branco` (padrão), `cor` (quando o branco vira um bloco sem detalhe, como o Itaú) ou `placa` (a placa
  original, quando a transparência ficou com ruído, como Santander e Embraer). `placa` é escolha manual e
  `versoes.py` não sobrescreve.
- Status diferente de "ok" (desatualizado ou verificar) fica fora da capa: o render mostra o espaço e avisa.
- Para corrigir uma empresa: salvar o arquivo oficial (site de RI ou kit de imprensa) em `oficial/<código>.svg`
  ou `.png` e pôr "ok" no status. Nunca redesenhar nem vetorizar à mão.

## Limites conhecidos

- Sem o RAD, os dados abertos de ITR e DFP da CVM são semanais (domingo) e o post sairia de 2 a 9 dias depois da
  entrega. Com o RAD, sai no mesmo dia. A data de entrega aparece na capa e na fonte.
- Os horários agendados do GitHub Actions atrasam (nas execuções de novembro de 2026, de 5 a 7 horas): a execução das 10:07 roda
  entre 15h e 17h30.
- Múltiplos passados usam o número de ações de hoje (não captam emissões e recompras).
