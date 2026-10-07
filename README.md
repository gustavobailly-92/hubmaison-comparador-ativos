# Comparador de Ativos · Maison Hub

Comparador de fundos de investimento, ações, FIIs e BDRs da B3, títulos do Tesouro Nacional, renda fixa e benchmarks, com **10 anos de histórico** (benchmarks desde o Plano Real, julho de 1994), publicado em **hubmaison.com/comparadordeativos**.
Os dados vêm dos dados abertos da CVM (informe diário e cadastro de fundos), do Banco Central (CDI, IPCA, poupança e PTAX pelo SGS),
do Tesouro Transparente (preços e taxas do Tesouro Nacional), da B3 (Ibovespa, IFIX, os arquivos COTAHIST com as cotações de ações, FIIs e BDRs e a API de empresas e fundos listados com os eventos societários), da CVM (informe mensal dos FIIs, com o rendimento de cada mês), da Nasdaq (Nasdaq 100, S&P 500 via ETF SPY, MSCI World via URTH,
ouro via GLD e inteligência artificial via AIQ) e da Coinbase (bitcoin em dólar, convertido pela PTAX), com CoinGecko, Yahoo Finance, Stooq e FRED como reservas,
e são regenerados **de terça a sábado às 10:07 (Brasília)** por este repositório, logo após a publicação da CVM (08:00).
Os últimos 12 meses de informes da CVM são baixados de novo a cada execução, para absorver as retificações; os meses até 2020 vêm dos ZIPs anuais da pasta HIST da CVM e ficam no cache do Actions, assim como os COTAHIST de anos fechados.

## Como funciona

```
pipeline/build_data.py     baixa CVM + BCB, calcula as métricas e grava dist/data/
pipeline/fontes_extras.py  benchmarks (BCB, B3, Nasdaq, Coinbase), Tesouro Nacional e a lista de fundos da XP
pipeline/acoes.py          ações, FIIs e BDRs: universo, liquidez e preços pelo COTAHIST da B3; proventos e desdobramentos pela API da B3 e pela CVM
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
| `fundos/<cnpj>.json` | cotas diárias (até 10 anos), patrimônio e cotistas semanais, métricas por janela (12/24/36/60/120 meses), retornos mensais, dados XP |
| `bench/<id>.json` | benchmarks alinhados ao calendário: ipca, ipca6 (IPCA + 6% a.a.), poupanca, dolar, ibov, ifix, imab, irfm, sp500, sp500brl, nasdaq, nasdaqbrl, msci, mscibrl, ouro, ourobrl, btc |
| `tesouro/<id>.json` | títulos do Tesouro Nacional: preço, taxa semanal, duration, histórico de taxa (mín., mediana, máx. desde a primeira oferta do título) |
| `acoes.json` | índice das ações, FIIs e BDRs: ticker, nome, tipo (acao/fii/bdr), espécie, 12/24/36 meses, % do CDI, Sharpe, volatilidade, prêmio histórico sobre o índice (`premio`, p.p. ao ano, na janela `premio_w`), benchmark (`bm`: ibov, ifix ou sp500brl), volume médio diário, último preço e `ajuste` (completo ou sem proventos) |
| `acoes/<ticker>.json` | duas séries alinhadas ao calendário: `q` (proventos reinvestidos) e `qp` (só preço), métricas por janela (12/24/36/60/120 meses), retornos mensais e o prêmio histórico |
| `hist/<id>.json` | histórico longo dos ativos-objeto (GLD, AIQ, S&P 500, Nasdaq 100, Ibovespa, URTH) para cenários de COE |
| `coes.json` | cópia do catálogo de COEs (estrutura, ativo-objeto, participação, proteção, prazo, links da lâmina e do DIE) |
| `perfis/gestoras.json` | gestoras do Guia de Fundos (descrição, principais executivos) e a carreira dos gestores |
| `perfis/fundos/<cnpj>.json` | por fundo: estratégia, equipe, gestores, categorias, vídeo, atribuição de performance e posicionamento atual |
| `emissores.json` | catálogo de emissores de renda fixa com o slug do ícone em `logos/` |
| `status.json` | contagens e avisos da execução |

Métricas por janela: rentabilidade acumulada, CDI no mesmo período e % do CDI, volatilidade anualizada,
índice de Sharpe (retorno anualizado menos CDI, dividido pela volatilidade), drawdown máximo e atual,
consistência (% de meses fechados acima do CDI), meses positivos, melhor e pior mês.

**Ações, FIIs e BDRs**: o universo é o mercado à vista do COTAHIST anual da B3 (ações ON, PN e units em lote padrão; BDRs patrocinados e não patrocinados; cotas de fundos imobiliários), mantendo os papéis com negócios em pelo menos 60% dos pregões dos últimos 12 meses (mínimo de 20 pregões). Os preços são os fechamentos oficiais do COTAHIST de cada ano (o ano corrente baixado a cada execução; os fechados em cache). Cada papel ganha duas séries: `qp`, só de preço, com desdobramentos, grupamentos e bonificações incorporados (eventos da API de empresas e fundos listados da B3; nos BDRs, sem fonte, o desdobramento é detectado pelo salto de preço de razão inteira), e `q`, com os proventos reinvestidos (dividendos e JCP brutos pela API de dividendos da B3, com o fechamento na data com; rendimentos mensais dos FIIs pelo campo `Percentual_Dividend_Yield_Mes` do informe mensal da CVM). BDRs ficam só com o preço (`ajuste = sem proventos`). O Yahoo Finance foi descartado: devolve 429 para os IPs do GitHub Actions. O prêmio histórico é o excesso anualizado sobre o Ibovespa (FIIs: IFIX; BDRs: S&P 500 em reais) na maior janela fechada disponível (36, 24 ou 12 meses); no simulador, a projeção de cada papel é o caminho do índice mais esse prêmio, editável na própria linha. Na página, a opção "Proventos de ações e FIIs" (Opções avançadas do bloco Carteira) alterna entre as duas séries em toda a comparação; o padrão é reinvestidos.

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
máximo (desde a primeira cota do ativo mais recente da comparação), a **carteira** (até 10 ativos com pesos, com ou sem rebalanceamento), a **projeção** e a análise dos COEs da prateleira da XP (payoff, histórico do ativo-objeto,
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

Na tabela de rentabilidade por período e no ranking, cada coluna (12, 24, 36 meses) tem a sua própria escala de tons, discreta: azul da marca mais presente nas maiores rentabilidades, vermelho suave nas negativas. O CDI e os benchmarks ligados ficam só no trilho lateral e nos gráficos (não aparecem como card nem como linha nas tabelas de ativos). O ranking tem a aba "Todos" (sem filtro de tipo). O **modo carteira** (botão "Carteira" no gráfico) coloca a carteira no lugar onde a comparação já acontece: um card **Carteira** entre os cards dos ativos (resultado no período, % do CDI, Sharpe e volatilidade), a **linha branca** da carteira no gráfico de rentabilidade acumulada e, logo abaixo, o card **Portfólio**, que toma o lugar da tabela por período enquanto o modo está aberto. O Portfólio reúne numa tabela única, por ativo: peso (anel, controle deslizante, % e cadeado), valor em reais, resgate, taxa contratada ou selo do benchmark, Vol, Sharpe, Co Ibov e a projeção (1, 2, 3, 5 e 10 anos até o horizonte, mais pessimista e otimista), com a linha Carteira ao fim; abaixo vêm o gráfico de projeção (horizonte padrão de 10 anos), as opções avançadas e o formulário do relatório (só o cliente e o tema). O **valor total** fica no cabeçalho do card, ao lado do título: cada ativo mostra o valor que lhe cabe e a **aplicação mínima** (fundos pela XP, Tesouro R$ 30, ações/FIIs/BDRs o preço de uma unidade); quando o valor fica abaixo do mínimo, a linha avisa e "Fixar no mínimo" trava o peso no menor valor que respeita o mínimo. Cada linha tem um **cadeado**: travado, o ativo não se mexe quando os outros mudam (mover o próprio controle muda só ele e os destravados). O **valor em reais é editável** (digitar R$ 50.000 ajusta o peso pelo valor total) e o % é só leitura; a coluna **Resgate** mostra o D+ de cada ativo (XP nos fundos, D+0 Tesouro, D+2 bolsa, dias úteis até o vencimento na renda fixa) e a coluna **Taxa / benchmark** mostra, para renda fixa e Tesouro, a taxa contratada (prefixado "14,35% a.a.", inflação "IPCA + 7,20% a.a.", "110% do CDI") em vez da comparação. Mais abaixo vem a **Projeção da carteira**: horizonte (padrão 10 anos) acima do gráfico, os ativos como linhas finas e a carteira em branco com a **faixa da carteira** (lognormal com a volatilidade histórica da carteira nos pesos atuais, no período selecionado), a tabela de marcos com pessimista/otimista e "vs" por referência, e o formulário do relatório (cliente, tema e prazos; o horizonte e o valor vêm de cima). Os períodos da comparação são 1, 2, 3 e 5 anos, Máx. (desde o início do ativo mais recente) e Datas. No seletor do simulador, cada linha mostra 12, 24 e 36 meses com o selo contra o próprio benchmark ("112% CDI", "Ibov +3,2", "IPCA +4,1", "IMA-B +1,2"), volatilidade e Sharpe centralizados com barras em gradiente, e os ativos já na comparação podem ser retirados ali mesmo (×). As tabelas e listagens usam barras finas em gradiente que crescem da esquerda para a direita (retorno na cor do ativo, volatilidade em vermelho, Sharpe em verde, negativo em vermelho); a escala do Sharpe satura em 2. Patrimônio e volumes em "R$ 97,1M" / "R$ 1,2B". Os atalhos ficam acima do campo de busca, com os ícones em azul e a marca da XP em branco: Tesouro Nacional ("Selic | Pré | Inflação"), Renda fixa (ícone de contrato com %), Renda Variável ("Ação, FII e BDR") e Ranking XP. Os cards dos ativos preenchem a grade alinhados à largura da busca. A busca mostra, por resultado, 1, 2 e 3 anos, vol, Sharpe, resgate e patrimônio/volume com barras. Os **benchmarks** carregam o histórico desde julho de 1994 (Plano Real; CDI, IPCA, dólar e poupança pelo BCB, Ibovespa pela B3 desde 2002) e, sem ativos na comparação, o período Máx. mostra o histórico inteiro; fundos, Tesouro e ações seguem com 10 anos (meta.cal_fundos0 marca onde o calendário dos fundos começa). O índice traz a **correlação de 12 meses com o Ibovespa** (co12) para fundos, Tesouro e papéis da B3; no seletor ela é a coluna "Co Ibov", as colunas são ordenáveis pelo cabeçalho, o filtro de liquidez é um menu com descrições, as classes XP aparecem fundidas (Crédito; DI; Debêntures Incentivadas Hedgeado; Inflação; Pré; Internacional; Internacional Multimercado Hedgeado) e sem o nome do tipo repetido, e clicar no nome de qualquer ativo da listagem (seletor, ranking ou tabela do Portfólio) abre o card de perfil. No ranking, o botão do fundo que já está na comparação vira "Retirar".

O **ranking de fundos** e os **COEs** abrem em painéis sobrepostos (atalhos do topo; `?coe=<id>` abre o COE direto). No ranking, cada janela
(12, 24 e 36 meses) mostra a rentabilidade absoluta e, abaixo, a comparação com o benchmark do próprio fundo: "% CDI" para os referenciados,
"Ibov +x p.p." para ações, "IMA-B +x p.p." / "IPCA +x p.p." para os atrelados à inflação, e assim por diante (coluna `bm` do `index.json`,
deduzida do benchmark informado pela XP; sem ele, do nome do fundo (IPCA, inflação, IMA-B, juro real; dólar; ações) ou da classe CVM). O Simulador usa a mesma coluna para escolher o modelo de cada fundo.

Na tabela **Ativos e pesos**, mover o peso de um ativo redistribui o restante entre os outros não travados na proporção que já tinham,
de modo que a soma é sempre 100%; a carteira entra **sem rebalanceamento** por padrão, com a opção "com pesos constantes" discreta abaixo da tabela. "Montar carteira"
(barra do ranking) leva direto ao modo carteira; os cards dos ativos têm largura fixa e cada um tem o seu × para remover. O **relatório para o cliente** (bloco "Relatório para o cliente" na Projeção da carteira) monta, só no navegador, um documento A4 com capa, carteira,
rentabilidade estimada dos últimos 12 meses, projeção de 10 anos, liquidez (resgate por prazo, com o D+ da XP editável), uma página por ativo
e as gestoras da carteira. Abre numa nova aba com tema escuro ou claro; o PDF sai por "Imprimir → Salvar como PDF". A capa traz o valor, o horizonte e, no canto inferior direito, um QR code
em pontos com os padrões de localização arredondados (pré-renderizado com `segno`, legível pelos leitores do celular) que abre o WhatsApp da Maison com mensagem pronta. A tabela da carteira tem a coluna "Gestora/emissor" e a "Perspectiva" (retorno esperado em 1 ano pelo simulador, em vez de uma
comparação com o CDI que não vale para um prefixado); os gráficos de alocação usam tons da marca. A projeção usa o horizonte escolhido em cima do gráfico da simulação
(padrão 10 anos), usa o simulador (soma ponderada dos caminhos de cada ativo; faixa pela volatilidade histórica da carteira) e leva as premissas para o
rodapé da página. No relatório a linha da carteira é branca no tema escuro e quase preta no claro; na tabela do Portfólio, renda fixa e Tesouro mostram a taxa contratada sob o nome e a perspectiva vem com "a.a."; a página dos últimos 12 meses chama-se "Rentabilidade passada"; na capa, o símbolo da Maison junto de "Equipe Maison" é branco (escuro no tema claro) e o conjunto vai da borda esquerda à direita do QR. O relatório leva o lockup oficial Maison Invest + XP (negativo no tema escuro, cor no claro) com o descritivo "Private", a página "Portfólio" e as rosquinhas com o número de ativos e a parcela em renda fixa no miolo; a alocação por tipo divide em prefixado, pós-fixado, inflação+, multimercados, renda variável, exterior e alternativos. As rosquinhas têm bisel (anel em gradiente e sombra interna); a página de gestoras e emissores quebra em continuações a cada três casas. Cada ativo tem a sua página: o cabeçalho com ícone da gestora, do emissor ou do Tesouro (ticker nas ações), nome e classe fica acima do card de indicadores, gráfico de área (últimos 12 meses nos fundos e nas ações, contra o CDI ou o índice; perspectiva no Tesouro
e na renda fixa), a leitura do modelo e os textos do perfil (gestora e equipe, estratégia e posicionamento do fundo; tipo do título do Tesouro; papel e emissor da renda
fixa). A última página, "Gestoras e emissores", resume cada casa, a trajetória dos gestores, cada banco emissor e o Tesouro Nacional.

## Rodar localmente

```bash
pip install pandas numpy pillow
python pipeline/build_data.py --out dist/data --cache cache      # ~40 min na primeira vez (10 anos de informes); depois ~20 min com o cache
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
