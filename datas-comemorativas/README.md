# Datas comemorativas (@maison.invest)

Kit para o Claude Code publicar, a cada data comemorativa e feriado nacional, um carrossel no Instagram da Maison Invest, e para o time mandar uma mensagem individual aos clientes daquela data. Irmão dos kits `ipca-mensal/`, `igpm-mensal/` e `focus-semanal/`: mesmo visual, mesmo formato de pasta da branch `posts` e o mesmo `instagram/postar.py` dos resultados da B3. Montado em 12/11/2026.

As profissões (Dia do Médico, do Servidor etc.) ficam no calendário das profissões, não aqui.

## Estrutura

```
calendario.json              as 34 datas: regra da data, ícone, textos das telas, legenda, mensagem ao cliente, regra da lista
bandeiras/                   bandeiras em SVG (flag-icons, MIT) das datas de país
template/data-carrossel.html template único; desenha capa, miolo (educativo, texto ou números), fechamento e o card do WhatsApp
render.py                    valida (tamanhos, travessão, palavras de risco, limite do Instagram) e gera saida/AAAA-MM-DD/DATA-slug/
listas.py                    lê o export da Base XP/CRM (CSV ou XLSX) e gera listas/AAAA-MM-DD-slug.csv com a mensagem personalizada
hoje.py                      diz ao workflow se a data do dia está aprovada
aprovados.json               o que o Gustavo aprovou (AAAA-MM-DD/slug); só isso sai sozinho
bloco_xp.txt                 vazio desde 15/11/2026 (sem identificação da XP nem ouvidoria)
publicacao/postar-datas.yml  workflow diário (7h40) para .github/workflows/ do repositório hubmaison-comparador-ativos
publicacao/postar.py.patch   uma linha no postar.py para aceitar pastas AAAA-MM-DD/DATA-slug
logo-invest-xp-negativo.svg  da skill maison: assets/logos/invest-xp/cor-negativo.svg
fonts/                       Montserrat 300 a 900 (npm pack @fontsource/montserrat)
```

Rodar: `python3 render.py --de 2026-11-12 --ate 2027-11-11 --chrome /caminho/do/chrome` (sem datas, faz os próximos 12 meses). `--so criancas,maes` faz só algumas.

## O calendário (nov/2026 a nov/2027)

34 datas: os 10 feriados nacionais e o Carnaval, as datas de relação e datas internacionais dos países onde há clientes (EUA, Canadá, Irlanda, Itália, França, Portugal, Japão, Ásia do Ano Novo Lunar, Emirados). Dois posts no mesmo dia são permitidos: cada data tem um campo `horario` (padrão 07:40); em 12/10, Aparecida sai às 7h40 e Crianças às 11h40.

| Data | Hora | Dia | Telas | CTA | Status |
|---|---|---|---|---|---|
| 15/11/2026 | 07:40 | Proclamação da República | 3 | hubmaison.com/simuladortesouronacional | aprovada |
| 20/11/2026 | 07:40 | Dia Nacional de Zumbi e da Consciência Negra | 2 | sóbrio | aprovada |
| 26/11/2026 | 07:40 | Thanksgiving (Ação de Graças, EUA) | 2 | sem CTA | aprovada |
| 2/12/2026 | 07:40 | UAE National Day (Emirados Árabes) | 2 | sem CTA | pendente |
| 8/12/2026 | 07:40 | Dia Nacional da Família | 2 | Agenda online, link na bio | aprovada |
| 25/12/2026 | 07:40 | Natal | 2 | sem CTA | aprovada |
| 1/1/2027 | 07:40 | Ano Novo | 3 | Agenda online, link na bio | aprovada |
| 24/1/2027 | 07:40 | Dia do Aposentado | 3 | hubmaison.com/simuladorlongoprazo | aprovada |
| 6/2/2027 | 07:40 | Ano Novo Lunar | 2 | sem CTA | pendente |
| 8/2/2027 | 07:40 | Carnaval | 3 | sem CTA | pendente |
| 8/3/2027 | 07:40 | Dia Internacional da Mulher | 2 | sem CTA | aprovada |
| 15/3/2027 | 07:40 | Dia do Consumidor | 4 | WhatsApp (21) 98500-4567 | pendente (conteúdo novo) |
| 17/3/2027 | 07:40 | St. Patrick's Day (Irlanda) | 2 | sem CTA | pendente |
| 26/3/2027 | 07:40 | Sexta-feira Santa | 2 | sóbrio | aprovada |
| 21/4/2027 | 07:40 | Tiradentes | 2 | sem CTA | aprovada |
| 1/5/2027 | 07:40 | Dia do Trabalho | 3 | hubmaison.com/simuladorlongoprazo | aprovada |
| 9/5/2027 | 07:40 | Dia das Mães | 3 | Agenda online, link na bio | aprovada |
| 2/6/2027 | 07:40 | Festa della Repubblica (Itália) | 2 | sem CTA | pendente |
| 10/6/2027 | 07:40 | Dia de Portugal | 2 | sem CTA | pendente |
| 12/6/2027 | 07:40 | Dia dos Namorados | 3 | Agenda online, link na bio | aprovada |
| 1/7/2027 | 07:40 | Canada Day | 2 | sem CTA | pendente |
| 4/7/2027 | 07:40 | Independence Day (EUA) | 3 | hubmaison.com/cambio | aprovada |
| 7/7/2027 | 07:40 | Tanabata (Japão) | 2 | hubmaison.com/simuladorlongoprazo | pendente |
| 14/7/2027 | 07:40 | Fête nationale (14 de julho, França) | 3 | sem CTA | aprovada |
| 20/7/2027 | 07:40 | Dia do Amigo | 2 | sem CTA | aprovada |
| 26/7/2027 | 07:40 | Dia dos Avós | 3 | WhatsApp (21) 98500-4567 | aprovada |
| 8/8/2027 | 07:40 | Dia dos Pais | 3 | sem CTA | aprovada |
| 7/9/2027 | 07:40 | Independência do Brasil | 3 | hubmaison.com/simuladorlongoprazo | aprovada |
| 15/9/2027 | 07:40 | Dia do Cliente | 3 | sem CTA | aprovada |
| 1/10/2027 | 07:40 | Dia Internacional da Pessoa Idosa | 3 | WhatsApp (21) 98500-4567 | aprovada |
| 12/10/2027 | 07:40 | Nossa Senhora Aparecida | 2 | sóbrio | pendente |
| 12/10/2027 | 11:40 | Dia das Crianças | 3 | WhatsApp (21) 98500-4567 | aprovada |
| 31/10/2027 | 07:40 | Dia Mundial da Poupança | 5 | hubmaison.com/mapadosinvestimentos | aprovada |
| 2/11/2027 | 07:40 | Finados | 2 | sóbrio | aprovada |

Não entram: Corpus Christi (ponto facultativo), Páscoa (coberta pela Sexta-feira Santa) e Black Friday. Nenhuma peça cita número de países (decisão de 15/11/2026: a lista de países muda sempre).

## Ícones e bandeiras

Ícones em traço dourado no `template/data-carrossel.html` (`ICONES`). Desenhos próprios e, desde 15/11/2026, alguns do Tabler Icons (sacola, idoso com bengala, aperto de mão com coração; MIT) e do Phosphor Icons, peso thin (tulipa, mão com coração; MIT). Datas de país usam a bandeira em cores reais (campo `bandeira` no `calendario.json`, arquivos em `bandeiras/`, do pacote flag-icons, MIT): Irlanda, Itália, Canadá, EUA e Independência do Brasil; Portugal leva caravela e bandeira. Nas telas do meio o emblema fica pequeno no canto superior esquerdo, longe do título.

## Regras de conteúdo (da skill maison)

- Data comemorativa fala da relação; o produto entra só como explicação de como funciona, sem oferta, taxa ou rentabilidade (A9). Conteúdo educativo leva "não constitui recomendação" na legenda.
- Pouco texto na imagem, explicação na legenda; dourado só em ícones, números do miolo e no contorno do botão do CTA; numeral da capa em tom sobre tom.
- Sem traços decorativos (fios curtos, marcadores de linha, "·", "▪️"): o Gustavo achou com cara de IA em 12/11/2026. O `render.py` recusa " · " e "▪". Topo só com a data, sem "Datas que importam".
- CTA por data, ligado ao tema: simulador de renda, simulador do Tesouro, mapa dos investimentos, câmbio, agenda ou WhatsApp. Datas de relação (Natal, Mulher, Pais, Cliente, Amigo) e datas sóbrias (Consciência Negra, Sexta-feira Santa, Finados) saem sem CTA; as sóbrias também sem o lema.
- Natal fala em clientes "ao redor do mundo", sem o número de países.
- Sem travessão, sem "garantido", "grátis", "consultoria", "gestão" (o `render.py` recusa).
- Todo post leva o lockup Maison Invest | XP nas telas. Nem a legenda nem as telas levam a frase "assessora de investimentos credenciada à XP Investimentos" ou a ouvidoria (decisão do Gustavo de 15/11/2026).

## Listas de clientes

`python3 listas.py --todas export.csv` mostra quantos clientes cada data alcança e quais campos faltam. `python3 listas.py criancas export.csv --data 2027-10-12` gera o CSV com grupo, nome, telefone, assessor e mensagem. Nada é inferido: mães, pais e avós dependem de um campo "filhos" e "netos" no CRM (hoje não existe); sem ele a lista sai vazia. Envio individual pelo assessor, nunca em massa.

## Publicação

1. Gustavo revisa a galeria e aprova; cada aprovação vira uma linha `AAAA-MM-DD/slug` em `aprovados.json`.
2. `postar-datas.yml` roda às 7h40 e às 11h40, e também quando `aprovados.json` muda na main. `hoje.py` lista as datas aprovadas do dia cujo horário já chegou; para cada uma sem `publicado.json`, renderiza, grava em `posts/AAAA-MM-DD/DATA-slug/` e publica pelo `instagram/postar.py`.
3. Instalado em 15/11/2026 na main do `hubmaison-comparador-ativos` (pasta `datas-comemorativas/` e `.github/workflows/postar-datas.yml`; `postar.py` aceita `DATA-slug`). Mesmo token (`IG_ACCESS_TOKEN`) e mesma fila (`concurrency: instagram`) da B3. Primeira publicação: Proclamação da República, 15/11/2026, https://www.instagram.com/p/DfxEbV-Emep/. O repositório é a fonte de verdade; este projeto guarda uma cópia.

## Todo ano

Em outubro, rodar `render.py` para os 12 meses seguintes e mandar a galeria para revisão. Datas móveis (Mães, Pais) e `{ano}` do Ano Novo se ajustam sozinhos.

## Pendências

- `bloco_xp.txt` fica vazio: desde 15/11/2026 a legenda não leva identificação da XP nem ouvidoria (decisão do Gustavo, ciente de que a Res. CVM 178, art. 24 pede as duas). A identificação fica só no lockup Maison Invest | XP das telas; a linha "assessora credenciada à XP" também saiu da última tela.
- Confirmar a história pessoal no Dia dos Pais.
- Criar no CRM os campos "filhos" e "netos" se quiser as listas de Mães, Pais, Avós e a parte "com filhos" das Crianças.
- Trocar Montserrat por Gotham se o ambiente de render tiver a fonte.
