# Comparador de Ativos · Maison Hub

Comparador de fundos de investimento, ações e BDRs da B3, títulos do Tesouro Nacional, renda fixa e benchmarks, publicado em **hubmaison.com/comparadordeativos**.
Os dados vêm dos dados abertos da CVM (informe diário e cadastro de fundos), do Banco Central (CDI, IPCA, poupança e PTAX pelo SGS),
do Tesouro Transparente (preços e taxas do Tesouro Nacional), da B3 (Ibovespa, IFIX e o arquivo COTAHIST, que define o universo e a liquidez das ações e BDRs), do Yahoo Finance (cotação ajustada das ações), da Nasdaq (Nasdaq 100, S&P 500 via ETF SPY, MSCI World via URTH,
ouro via GLD e inteligência artificial via AIQ) e da Coinbase (bitcoin em dólar, convertido pela PTAX), com CoinGecko, Yahoo Finance, Stooq e FRED como reservas,
e são regenerados **de terça a sábado às 10:07 (Brasília)** por este repositório, logo após a publicação da CVM (08:00).
Os últimos 12 meses de informes da CVM são baixados de novo a cada execução, para absorver as retificações.

## Como funciona

```
pipeline/build_data.py     baixa CVM + BCB, calcula as métricas e grava dist/data/
pipeline/fontes_extras.py  benchmarks (BCB, B3, Nasdaq, Coinbase), Tesouro Nacional e a lista de fundos da XP
pipeline/acoes.py          ações e BDRs: universo e liquidez pelo COTAHIST anual da B3, cotação ajustada do Yahoo (com cache por papel)
pipeline/coes.json         catálogo dos COEs da prateleira da XP (termos lidos das lâminas e dos DIEs)
pipeline/gestoras.json     casas gestoras: nome curto, site (ícone) e trechos do nome legal da CVM para o casamento
pipeline/emissores.json    emissores de renda fixa (bancos, financeiras, securitizadoras) e o Tesouro, com site para o ícone
pipeline/extrair_guia.py   lê o Guia de Fundos da XP (.xlsx): refaz a lista de fundos locais e extrai os perfis (abas ocultas)
pipeline/perfis.json       perfis do Guia: 126 gestoras (descrição, equipe), 452 gestores (carreira), 1.137 fundos (estratégia, equipe, posicionamento)
status/ima.csv             número diário dos índices IMA da ANBIMA, acumulado a cada execução (público só o dia corrente)
pipeline/xp_fundos.csv     fundos da plataforma XP (tipo, classe, risco, benchmark, taxas, liquidez)
site/index.html            a página (autocontida), lê dist/data/ ou o GitHub Pages deste repositório
.github/workflows/         agendamento de terça a sábado + publicação no GitHub Pages
```

Saída do pipeline (`dist/data/`):

| Arquivo | Conteúdo |
|---|---|
| `meta.json` | calendário de dias úteis, CDI acumulado e diário, semanas, data de referência, lista de benchmarks, títulos do Tesouro, históricos, tipos XP, expectativas do Focus (`focus`: Selic, IPCA e câmbio) e estatísticas de 15 anos (`hist15`: CDI, IPCA 12 m, juro real 10 anos) |
| `index.json` | índice de busca: um registro compacto por fundo (CNPJ, nome, classe, gestora, PL, cotistas, 12/24/36 meses, campos XP, prazo de resgate `xp_liq`, site e ícone da gestora, `pf`/`pg` = tem perfil de fundo / id da gestora no Guia) |
| `fundos/<cnpj>.json` | cotas diárias, patrimônio e cotistas semanais, métricas por janela (12/24/36/48 meses), retornos mensais, dados XP |
| `bench/<id>.json` | benchmarks alinhados ao calendário: ipca, ipca6 (IPCA + 6% a.a.), poupanca, dolar, ibov, ifix, imab, irfm, sp500, sp500brl, nasdaq, nasdaqbrl, msci, mscibrl, ouro, ourobrl, btc |
| `tesouro/<id>.json` | títulos do Tesouro Nacional: preço, taxa semanal, duration, histórico de taxa (mín., mediana, máx. desde a primeira oferta do título) |
| `acoes.json` | índice das ações e BDRs: ticker, nome, tipo (acao/bdr), espécie, 12/24/36 meses, % do CDI, Sharpe, volatilidade, prêmio histórico sobre o índice (`premio`, p.p. ao ano, na janela `premio_w`), benchmark (`bm`: ibov ou sp500brl), volume médio diário e último preço |
| `acoes/<ticker>.json` | série ajustada alinhada ao calendário, métricas por janela, retornos mensais e o prêmio histórico |
| `hist/<id>.json` | histórico longo dos ativos-objeto (GLD, AIQ, S&P 500, Nasdaq 100, Ibovespa, URTH) para cenários de COE |
| `coes.json` | cópia do catálogo de COEs (estrutura, ativo-objeto, participação, proteção, prazo, links da lâmina e do DIE) |
| `perfis/gestoras.json` | gestoras do Guia de Fundos (descrição, principais executivos) e a carreira dos gestores |
| `perfis/fundos/<cnpj>.json` | por fundo: estratégia, equipe, gestores, categorias, vídeo, atribuição de performance e posicionamento atual |
| `emissores.json` | catálogo de emissores de renda fixa com o slug do ícone em `logos/` |
| `status.json` | contagens e avisos da execução |

Métricas por janela: rentabilidade acumulada, CDI no mesmo período e % do CDI, volatilidade anualizada,
índice de Sharpe (retorno anualizado menos CDI, dividido pela volatilidade), drawdown máximo e atual,
consistência (% de meses fechados acima do CDI), meses positivos, melhor e pior mês.

**Ações e BDRs**: o universo é o mercado à vista em lote padrão do COTAHIST anual da B3 (ações ON, PN e units; BDRs patrocinados e não patrocinados), mantendo os papéis com negócios em pelo menos 60% dos pregões dos últimos 12 meses (mínimo de 20 pregões). A série de preços é a cotação ajustada do Yahoo Finance (proventos reinvestidos e desdobramentos incorporados, comparável à cota de um fundo); cada papel fica em cache (`cache/acoes/<ticker>.json`) e, quando o Yahoo falha numa execução, vale a série da execução anterior (aviso em `status.json`). O prêmio histórico é o excesso anualizado sobre o Ibovespa (BDRs: sobre o S&P 500 em reais) na maior janela fechada disponível (36, 24 ou 12 meses); no simulador, a projeção de cada ação é o caminho do índice mais esse prêmio, editável na própria linha. O arquivo do ano corrente (~50 MB) é baixado a cada execução; os anos anteriores ficam no cache.

Universo publicado: fundos em funcionamento normal, não exclusivos, com pelo menos 10 cotistas e informe recente. Os fundos da plataforma XP
e os fundos de previdência (nome com PREV, FIE, VGBL ou PGBL; os FIEs têm a seguradora como único cotista) entram sem a regra de cotistas.

Gestora e administrador vêm de `registro_fundo.csv` (RCVM 175), cruzado com `registro_classe.csv` por `ID_Registro_Fundo`; o nome curto e o site da gestora vêm de `pipeline/gestoras.json` (com um nome curto derivado do nome legal quando a casa não está no catálogo). A taxa de administração não existe no cadastro novo da CVM; quando o fundo está na planilha da XP, usa-se a taxa de lá.
Nos fundos de previdência (FIEs dos planos XP Seguros, Icatu etc.) a gestora exibida é o **gestor estratégico** da planilha XP (SPX, Ibiuna...), e o gestor da CVM fica como nome legal.
Os ícones das gestoras são baixados pelo pipeline (favicons dos sites oficiais), têm o fundo branco removido e, quando são pretos ou de cor escura (luminância média abaixo de 0,34), têm a luminância invertida para ficarem claros sobre o fundo escuro do site; vão para `data/logos/<slug>.png` (coluna `gestor_logo = "p"`; cache de 30 dias em `cache/logos/<slug>.v2.png`). Quando o processamento falha, a página usa o favicon direto ou um monograma.

**IMA-B e IRF-M** não têm fonte aberta com histórico (as séries do BCB pararam em maio/2023 e a ANBIMA publica em aberto só o dia corrente).
São replicados pela cota dos fundos passivos Caixa Brasil IMA-B e IRF-M Títulos Públicos, com a taxa de administração (0,20% a.a.) devolvida.
A cada execução o pipeline lê `ima_completo.txt` da ANBIMA e acumula o número oficial em `status/ima.csv`; quando houver pelo menos 20 dias oficiais,
a série passa a seguir o número da ANBIMA a partir do primeiro dia disponível (emendada ao proxy).

A página ainda calcula no navegador: séries sintéticas de renda fixa (% do CDI, prefixado, IPCA+), períodos personalizados e o período
máximo (desde a primeira cota do ativo mais recente da comparação), a carteira de **Diversificação** (até 10 ativos com pesos, com ou sem rebalanceamento), o **Simulador** e a análise dos COEs da prateleira da XP (payoff, histórico do ativo-objeto,
cenários e leitura de outras lâminas em PDF).

**Simulador** (botão no cabeçalho do gráfico): o horizonte (1, 2, 3, 5 e 10 anos) fica acima do gráfico; abaixo dele, **Opções avançadas** (recolhidas por padrão) guardam
a tabela de **patamares** (% a.a., em hoje, 1, 2, 3, 5 e 10 anos, interpolados mês a mês), o prazo em que os cenários chegam ao alvo e o intervalo da faixa (68% ou 95%).
A tabela tem uma linha para o CDI, uma para o IPCA e uma por benchmark de risco em uso (Ibovespa, S&P 500 e MSCI em reais, IFIX, ouro, dólar). O **juro real** (NTN-B de
referência: o Tesouro IPCA+ da comparação ou o principal com vencimento mais perto de 10 anos) é **derivado** do CDI e do IPCA pela hipótese das expectativas: em cada marco,
a média do juro real ex-ante (Fisher, CDI contra IPCA) dos 10 anos seguintes mais o prêmio a termo de hoje (taxa da NTN-B menos essa média); "Adicionar juro real" mostra a
linha para quem quiser editar ou escolher um cenário próprio. Cada linha tem um menu de cenário com ícone: medianas do **Focus** (CDI e IPCA, padrão; dólar pelo câmbio de fim
de ano do Focus), **mediana, mínima ou máxima de 15 anos** (CDI diário do BCB, IPCA de 12 meses e juro real de 10 anos construído com as NTN-Bs do histórico do Tesouro
Direto; `meta.hist15`), "fica como está", ou base + prêmio para os benchmarks (padrão: Ibovespa, S&P e MSCI = CDI + 3 p.p.; IFIX = CDI + 1; ouro = IPCA + 2; dólar = IPCA − 2
sem Focus). Os cenários chegam ao alvo em 1, 2 ou 3 anos (padrão 3, linear) e ficam lá; qualquer célula editada (com os botões − e +, teclado ou digitando) vira "personalizado".
Modelo por ativo: pós-fixados e % do CDI seguem o caminho do CDI; IPCA+ segue IPCA + taxa; títulos do Tesouro combinam o carrego com o efeito de preço (duration que encurta
até o vencimento; depois reinvestem no juro do momento); fundos com benchmark IMA-B viram uma NTN-B sintética de duration 7,5 anos escalada pelo beta do fundo (regressão diária
na janela; só quando a correlação passa de 0,35); fundos de risco seguem beta × caminho do seu benchmark; atrelados à inflação seguem o IPCA mais o spread; em todos os fundos
entra metade do alfa (ou do excesso) histórico, com faixa lognormal de 68% ou 95%. O gráfico traz o CDI e os benchmarks ligados no trilho como linhas tracejadas.
A tabela de resultados mostra os marcos com o ágio/deságio dos títulos, a faixa pessimista/otimista, uma coluna **"vs"** por referência do trilho (vs CDI sempre; vs Ibov, vs S&P
etc. quando o benchmark está ligado), em pontos percentuais acumulados no horizonte, o Sharpe no período e a correlação com o Ibovespa; em cada linha, o botão "Trocar"
(e a linha "Adicionar ativo") abre o **seletor de ativos**: um painel com as seções Renda fixa, Tesouro Nacional, Fundos XP (por tipo e classe XP), Previdência XP (por classe)
e Outros fundos (por classe CVM), busca, filtro de prazo de resgate (livre, até D+0, D+1, D+5, D+30, D+60, D+90) e, em cada fundo, o retorno de 12 meses, a volatilidade
e o Sharpe com barras, em ordem decrescente de retorno (as contagens das fichas acompanham o filtro e a busca); a troca mantém cor e peso na comparação inteira. Na tabela
de resultados, cada linha tem o × para tirar o ativo da comparação, e os valores vêm com barras finas: retorno por marco na cor do ativo, volatilidade em vermelho e Sharpe
em azul, na escala da coluna. Com o simulador aberto, a tabela de rentabilidade por período some (volta ao fechar). As letras miúdas ("Como a simulação é construída") ficam recolhidas no fim do card. Os campos numéricos do site (patamares, COE, renda fixa) usam o mesmo
stepper (− e +, segurar para repetir, setas; o valor digitado entra como está).

A renda fixa hipotética aceita o **papel** (CDB, LCI, LCA, LC, LF, LIG, CRI, CRA, debênture, RDB), o **emissor** escolhido num catálogo de bancos, financeiras e
securitizadoras com ícone (`pipeline/emissores.json`, texto livre também vale) e o **vencimento**; a chave fica `rf:tipo:taxa:emissor[:AAAA-MM-DD]`. O card mostra só o
nome ("CDB BMG"), a taxa contratada ("14,35% a.a.", "110% do CDI", "IPCA + 7,25% a.a.") e o indexador (prefixado, atrelado ao CDI, atrelado ao IPCA), sem comparação com o
CDI, porque um prefixado não se mede em % do CDI (o Tesouro Prefixado segue a mesma regra: etiqueta "prefixado" com a taxa, sem % do CDI); renda fixa e Tesouro usam
duas casas decimais em toda a página e no relatório. Na página, a família chama-se **Tesouro Nacional** (atalho, busca, seletor e relatório). O vencimento vira o prazo de resgate no
relatório (dias úteis até o vencimento); sem vencimento, liquidez diária. Títulos do Tesouro contam como D+0. A busca também entende "CDB Pine 110% do CDI".

**Perfis** (botão "Sobre" na ficha, ou clique no nome): card com a descrição da gestora e seus principais executivos, a trajetória dos gestores (empresa a empresa),
a estratégia e a equipe do fundo, o posicionamento atual e a atribuição de performance escritos pelo gestor, com links para a página e o material do fundo na XP; para
títulos do Tesouro, a explicação de cada tipo (IPCA+, com juros semestrais, Prefixado, Selic, Renda+, Educa+) com os dados do título; para a renda fixa, o emissor e o
papel (o que é, FGC, imposto, liquidez). Fonte: abas ocultas "Base Assets", "Base Gestores", "Base Fundos" e "Base Comentários" do Guia de Fundos da XP, extraídas com
`python pipeline/extrair_guia.py <Guia.xlsx>` (que também refaz a lista de fundos locais e mantém a de previdência) e publicadas em `data/perfis/`.

Em toda a página a comparação de um fundo é feita com o **seu benchmark** (coluna `bm`): "148% CDI" para os referenciados, "Ibov +5,2 p.p." para ações, "IMA-B +x p.p."
e "IPCA +x p.p." para os atrelados à inflação, "Dólar", "S&P 500", "MSCI" e "IFIX" nos demais; nos cards dos ativos, na tabela por período (barra com o marcador do
benchmark), na ficha (cards de 12, 24 e 36 meses), no ranking e no relatório. Títulos do Tesouro IPCA+ e renda fixa IPCA+ comparam com o IPCA; os demais com o CDI.

O catálogo `pipeline/coes.json` é mantido à mão: os COEs em oferta mudam a cada reserva e os termos vêm da lâmina (material publicitário)
e do DIE de cada um, disponíveis em "Detalhes do ativo" no Hub XP.

Na tabela de rentabilidade por período e no ranking, cada coluna (12, 24, 36 meses) tem a sua própria escala de tons, discreta: azul da marca mais presente nas maiores rentabilidades, vermelho suave nas negativas. O CDI e os benchmarks ligados ficam só no trilho lateral e nos gráficos (não aparecem como card nem como linha nas tabelas de ativos). O ranking tem a aba "Todos" (sem filtro de tipo). No seletor do simulador, cada linha mostra 12, 24 e 36 meses com o selo contra o próprio benchmark ("112% CDI", "Ibov +3,2", "IPCA +4,1", "IMA-B +1,2"), volatilidade e Sharpe centralizados com barras em gradiente, e os ativos já na comparação podem ser retirados ali mesmo (×). A tabela de resultados do simulador usa "Vol", "Co Ibov" e "CDI +x p.p.", com pessimista e otimista em pastilhas coloridas.

O **ranking de fundos** e os **COEs** abrem em painéis sobrepostos (atalhos do topo; `?coe=<id>` abre o COE direto). No ranking, cada janela
(12, 24 e 36 meses) mostra a rentabilidade absoluta e, abaixo, a comparação com o benchmark do próprio fundo: "% CDI" para os referenciados,
"Ibov +x p.p." para ações, "IMA-B +x p.p." / "IPCA +x p.p." para os atrelados à inflação, e assim por diante (coluna `bm` do `index.json`,
deduzida do benchmark informado pela XP; sem ele, do nome do fundo (IPCA, inflação, IMA-B, juro real; dólar; ações) ou da classe CVM). O Simulador usa a mesma coluna para escolher o modelo de cada fundo.

Na **Diversificação** (que vem logo depois do gráfico de rentabilidade acumulada), mover o peso de um ativo redistribui o restante entre os outros na proporção que já tinham,
de modo que a soma é sempre 100%; a carteira entra **sem rebalanceamento** por padrão, com a opção "com pesos constantes" discreta abaixo da legenda. "Montar carteira"
(botão no trilho, abaixo das referências, e barra do ranking) leva direto a essa seção; os cards dos ativos têm largura fixa e cada um tem o seu × para remover. O **relatório para o cliente** (bloco "Relatório para o cliente" na Diversificação) monta, só no navegador, um documento A4 com capa, carteira,
rentabilidade estimada dos últimos 12 meses, projeção de 10 anos, liquidez (resgate por prazo, com o D+ da XP editável), uma página por ativo
e as gestoras da carteira. Abre numa nova aba com tema escuro ou claro; o PDF sai por "Imprimir → Salvar como PDF". A capa traz o valor, o horizonte e, no canto inferior direito, um QR code
em pontos com os padrões de localização arredondados (pré-renderizado com `segno`, legível pelos leitores do celular) que abre o WhatsApp da Maison com mensagem pronta. A tabela da carteira tem a coluna "Gestora/emissor" e a "Perspectiva" (retorno esperado em 1 ano pelo simulador, em vez de uma
comparação com o CDI que não vale para um prefixado); os gráficos de alocação usam tons da marca. A projeção é opcional e tem horizonte escolhido no formulário
(10, 5 ou 3 anos, ou sem projeção), usa o simulador (soma ponderada dos caminhos de cada ativo; faixa pela volatilidade histórica da carteira) e leva as premissas para o
rodapé da página. O relatório leva o lockup oficial Maison Invest + XP (negativo no tema escuro, cor no claro) com o descritivo "Private", a página "Portfólio" e as rosquinhas com o número de ativos e a parcela em renda fixa no miolo; a alocação por tipo divide em prefixado, pós-fixado, inflação+, multimercados, renda variável, exterior e alternativos. Cada ativo tem a sua página: ícone da gestora, do emissor ou do Tesouro (ticker nas ações), indicadores, gráfico de área (últimos 12 meses nos fundos e nas ações, contra o CDI ou o índice; perspectiva no Tesouro
e na renda fixa), a leitura do modelo e os textos do perfil (gestora e equipe, estratégia e posicionamento do fundo; tipo do título do Tesouro; papel e emissor da renda
fixa). A última página, "Gestoras e emissores", resume cada casa, a trajetória dos gestores, cada banco emissor e o Tesouro Nacional.

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
