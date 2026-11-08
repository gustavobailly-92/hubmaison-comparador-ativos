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

1. Capa: marca da Invest, logo da empresa, "Resultado do 3T26 · data de entrega à CVM", o destaque
   (receita líquida; lucro para bancos e seguradoras) e a maior variação contra o mesmo trimestre do ano anterior,
   para cima ou para baixo, entre receita, EBITDA, lucro, PL, dívida e ativo (n.m. fica de fora).
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
bash codigo/post/preparar.sh $B/w
python3 codigo/post/selecionar.py dados/index.json            # empresas do dia (até 3)
MAISON_WORK=$B/w node codigo/post/empresa.mjs dados/<TICKER>.json saida/<TICKER>-<periodo>
```

Sai `01.png` a `08.png` (ou `07.png`) e `legenda.txt`. Para uma empresa específica, pular o `selecionar.py` e usar o
JSON do ticker. Capa de notícia: no JSON, `"capa": {"tipo": "noticia"}` e `"noticia": {"titulo", "data", "fonte"}`,
só com fato documentado (fato relevante ou comunicado na CVM).

## Antes de entregar

- Olhar todas as telas: texto cortado, sobreposição, "n/d" inesperado, logo ilegível.
- Nome da empresa: o índice traz o nome curto da B3 ("Santander Br", "Ambev S/A", "Jsl"); corrigir `empresa` no JSON
  para o nome usual ("Santander Brasil", "Ambev", "JSL") antes de renderizar.
- Conferir no JSON: `entrega.versao` (reapresentação aparece na linha de fonte), `financeira`, `multiplos.data_cotacao`.
- Valor muito fora da escala da empresa (receita que dobra num trimestre, lucro maior que a receita): avisar o Gustavo
  em vez de entregar como pronto.
- Entregar as telas e a legenda com o aviso de que precisa do ok antes de postar, e listar o que faltou (logo, dado).

## Logos

Biblioteca em `post/logos/<4 letras do ticker>.png` (ex.: `VALE.png`), uma por companhia, com o índice em
`post/logos/indice.csv` (código, tickers, razão social, arquivo, fonte e status). Origem: coleção pública
github.com/alextchatalov/logos-acoes-b3 (levantamento de setembro de 2026), PNG 450x450 com a marca oficial sobre a
placa branca ou na cor da marca. O `placa.py` recorta a margem e mantém a placa; nada é recolorido nem redesenhado.

- Status diferente de "ok" (desatualizado ou verificar) fica fora da capa: o render mostra o espaço e avisa.
- Para trocar ou corrigir: salvar o arquivo oficial (site de RI ou kit de imprensa) como `<código>.svg` ou `.png`
  nesta pasta e pôr "ok" no status. Um `.svg` tem preferência sobre o `.png` do mesmo código.
- Nunca redesenhar nem vetorizar à mão.

## Limites conhecidos

- A CVM atualiza os dados abertos de ITR e DFP uma vez por semana (domingo), e o workflow roda de terça a sábado: o
  post sai de 2 a 9 dias depois da entrega. A data de entrega aparece na capa e na fonte.
- Os horários agendados do GitHub Actions atrasam (nas execuções de novembro de 2026, de 5 a 7 horas): a execução das 10:07 roda
  entre 15h e 17h30.
- Múltiplos passados usam o número de ações de hoje (não captam emissões e recompras).
