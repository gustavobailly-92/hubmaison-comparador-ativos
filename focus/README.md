# Carrossel semanal do Focus (@maison.invest)

Kit para o Claude Code publicar, toda segunda-feira de manhã, o carrossel do Relatório Focus no Instagram da Maison Invest. O layout é fixo; números, destaque e textos saem sozinhos da API do Banco Central. Irmão do kit `ipca-mensal/`, com o mesmo padrão de pastas e de publicação.

Versão 4 (15/11/2026, noite): cinco slides no visual da Selic revisada, com o horizonte do mercado (ano corrente a quatro anos à frente). Exemplo com os dados reais do boletim de 9/11/2026 na galeria "Focus da semana · modelo de layout". O histórico das rodadas de melhoria está em `LOOP.md`.

## Estrutura

```
fetch_focus.py                 baixa da API Olinda e monta dados/focus-AAAA-MM-DD.json (data da segunda de divulgação)
template/focus-carrossel.html  template único; desenha os 5 slides a partir do JSON
render.py                      valida o JSON, gera saida/AAAA-MM-DD/0N-slide.png e .jpg, legenda.txt e alt.json
checar.py                      mede os PNGs: letra (22 px no conteúdo, 18 na nota), contraste 4,5:1, margem de 60 px, colisão, travessão
testar_cenarios.py             renderiza e checa 4 semanas diferentes (parada, outro destaque, dólar na capa)
hoje.py                        diz ao workflow se a API já tem o boletim da semana e se ele ainda não foi publicado
publicacao/postar-focus.yml    workflow do hub (segunda a quarta, 8h40, 9h40 e 11h10)
icones/                        carrinho e indústria do Iconoir (MIT), os mesmos do IGP-M
LOOP.md                        estado da melhoria contínua deste kit
bloco_xp.txt                   vazio desde 15/11/2026 (a legenda não leva identificação da XP nem ouvidoria)
logo-invest-xp-negativo.svg    copiar da skill maison: assets/logos/invest-xp/cor-negativo.svg
fonts/                         montserrat-latin-{300,400,500,600,700,800,900}-normal.woff2 (npm pack @fontsource/montserrat)
dados/raw/                     cópia crua da API da última execução (permite rodar com --raw sem rede)
```

Rodar: `python3 fetch_focus.py` e depois `python3 render.py dados/focus-AAAA-MM-DD.json --chrome /caminho/do/chrome`.

## Os slides (1080 x 1350, 4:5)

Fundo de todos os slides igual ao do carrossel do IPCA (azul profundo escurecido), sem a moldura (16/11/2026). Slides internos no visual da Selic revisada em 12/11: topo com marcador dourado, "Focus", "Boletim do Banco Central" e a data, com fio inteiro embaixo; título de 52 px e subtítulo de 26 px nos slides de gráfico, para o gráfico mandar; rodapé só com a fonte. Sem @maison.invest, sem contador de slides, sem traços curtos, sem travessão. "Deslize" e lockup na capa; lockup no fechamento. Dourado #c9a96e só em marcador, linhas, pontos e no % da capa; mesma cor para alta e queda.

| # | Slide | Título | Conteúdo automático |
|---|---|---|---|
| 1 | Capa, no formato da capa do IPCA (16/11/2026) | sempre "Selic esperada para o fim de AAAA", em letra leve de 44 px e azul suave (o número fica em branco); embaixo da semana anterior, ícone de tendência (subida, queda ou seta reta) com o número de semanas seguidas de alta, queda ou sem mudança | logo no alto; kicker com a perna do logotipo, "Focus · expectativas de mercado"; número grande; linha "Semana anterior 5,22%" com a nota ("queda de 0,11%", "segunda alta seguida, de 0,25%"); gráfico em degraus das 26 semanas com meses e valor inicial; no pé, data de divulgação e "Deslize" |
| 2 | Ano corrente | As projeções para AAAA | por indicador: seis meses em degraus com linha de referência no valor inicial (área entre as duas), "em maio, 4,92%"; mediana de hoje e variação na semana em % (como na Selic, nunca "p.p."). Subtítulo: o segundo movimento da semana |
| 3 | Horizonte | Previsão do mercado | mediana do ano corrente a quatro à frente (hoje 2026 a 2030) dos quatro indicadores; ano corrente em ponto cheio, demais vazados; linha da meta de 3% no IPCA; subtítulo curto ("Selic cai para 10,00% até 2030; IPCA acima da meta em todos os anos."). Rodapé diz quantas instituições projetam os anos distantes |
| 4 | Consenso | Onde há consenso | subtítulo só descritivo ("Da menor à maior projeção de cada indicador para AAAA."); por linha, o nome e a faixa da menor à maior projeção, todas na mesma escala relativa, com a mediana dourada no centro e o valor dela em cima do ponto |
| 5 | Fechamento | O mercado, semana a semana | sem texto de explicação; três cartões com ícone (carrinho, percentual, calendário): IPCA do ano, Selic no fim do ano, data do próximo boletim; CTA em cápsula; lema; lockup; aviso de conteúdo informativo |

## Regras dos textos automáticos (`fetch_focus.py`)

- Semana do boletim = mediana da sexta anterior à divulgação (`ExpectativasMercadoAnuais`, `baseCalculo = 0`, janela de 30 dias), que é o número do relatório publicado.
- Capa: desde 16/11/2026 é sempre a Selic esperada para o fim do ano, e a Selic vem primeiro em todos os slides (pedido do Gustavo). Número com cinco caracteres ou mais cai de 250 para 218 px.
- Maior movimento da semana (vai para a legenda e o subtítulo do slide 2): nota = peso x (variação na semana / escala + 0,15 x semanas seguidas), com escala Selic 0,25, IPCA e PIB 0,10, dólar R$ 0,05 e peso 1,3 para IPCA e Selic. Selic que mexe ganha +1. Semana sem mudança: IPCA na capa com "Sem mudança na semana."
- Frase de apoio: outro indicador do ano corrente com a sequência mais longa; sem nenhum, "As demais projeções para AAAA ficaram onde estavam."
- Contexto da capa: lido da série semanal ("Segunda alta seguida", "Primeira alta em 5 semanas", "Virada depois de 3 quedas", "Parada há 4 semanas").
- Horizonte: "Selic cai/sobe para Y até AAAA"; "IPCA na meta de 3% em AAAA" no primeiro ano com mediana até 3%, senão "IPCA acima da meta em todos os anos".
- Frase da capa: contexto da série e variação numa frase só ("Segunda alta seguida, 0,25 p.p. acima da semana anterior."; "Parada há 4 semanas."; "Mesma mediana da semana anterior.").
- Consenso: sem análise no slide nem na legenda (pedido de 15/11); a legenda só explica como ler a faixa.
- A partir de 20/12 o "ano corrente" passa a ser o ano seguinte.

Conferido contra a imprensa em 12/11/2026: Selic 2026 de 13,50% para 13,75%, IPCA 2026 mantido em 5,22%, IPCA 2027 em 4,90%.

## Recorrência e publicação (instalado no hub em 16/11/2026)

O Banco Central publica o Focus às segundas, por volta das 8h25, com as expectativas coletadas até a sexta anterior; em feriado ou greve sai no dia útil seguinte. O kit roda no `hubmaison-comparador-ativos`, pasta `focus/` da main, pelo workflow `.github/workflows/postar-focus.yml`:

- de segunda a quarta, às 8h40, 9h40 e 11h10 (Brasília), `hoje.py` confere se a API Olinda já tem a sexta mais recente e se nenhuma pasta `FOCUS-<sexta>` da branch `posts` tem `publicado.json`;
- havendo boletim novo: `fetch_focus.py --data <sexta> --divulgacao <hoje>`, `render.py`, `checar.py`; qualquer falha para o workflow antes de publicar (o GitHub avisa por e-mail);
- grava os JPEGs, a legenda e o `alt.json` em `posts/<hoje>/FOCUS-<sexta>/` e publica pelo `instagram/postar.py` (mesmo token e mesma fila da B3, do IPCA e das datas). O `postar.py` aceita `FOCUS-AAAA-MM-DD` desde 16/11/2026.

Para publicar uma semana atrasada: Actions, "Publicar Focus da semana", Run workflow, com a sexta da coleta.

O código-fonte do kit fica neste repositório (`claude-projetos`, branch `claude/focus-semanal`); a cópia que roda é a do hub. Mudou aqui, copie para lá.

## Antes de publicar (sozinho)

- `render.py` passou sem erro (faixas plausíveis, série com 8+ semanas, textos até 110 caracteres, legenda sem palavra de risco nem travessão e até 2.200 caracteres, `alt.json` sem texto vazio).
- `checar.py saida/AAAA-MM-DD` passou.
- Se o destaque escolhido parecer estranho para a semana, o post fica pendente de revisão em vez de sair sozinho.

## Regra da identificação (decisão do Gustavo em 15/11/2026, para todos os posts)

Nem a legenda nem as telas levam "Maison Invest, assessora de investimentos credenciada à XP Investimentos", ouvidoria da XP ou link da relação de assessores. `bloco_xp.txt` fica vazio, então a trava do "[" não segura mais a publicação. Nas telas fica só o lockup Maison Invest | XP e o aviso de conteúdo informativo ou educativo. Ele decidiu ciente de que a Res. CVM 178, art. 24 lista essas informações para material publicitário. Vale para B3, Focus, IPCA, IGP-M, Selic e datas comemorativas.

## Pendências

- Nota de fonte em 20 px (a revisão às cegas pediu mais; os outros kits usam 19 px). Decidir se sobe em todos.
- Trocar Montserrat por Gotham se o ambiente de render tiver a fonte.
