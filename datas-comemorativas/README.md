# Datas comemorativas (@maison.invest)

Kit para o Claude Code publicar, a cada data comemorativa e feriado nacional, um carrossel no Instagram da Maison Invest, e para o time mandar uma mensagem individual aos clientes daquela data. Irmão dos kits `ipca-mensal/`, `igpm-mensal/` e `focus-semanal/`: mesmo visual, mesmo formato de pasta da branch `posts` e o mesmo `instagram/postar.py` dos resultados da B3. Montado em 12/11/2026.

Desde 17/11/2026 o mesmo calendário traz também as datas das profissões (20) e das especialidades médicas (14), com o mesmo template, a mesma aprovação e o mesmo workflow. Ficam fora o Notário e Registrador (decisão do Gustavo) e o Aposentado, que já é data comemorativa.

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
| 2/12/2026 | 07:40 | UAE National Day (Emirados Árabes) | 2 | sem CTA | aprovada |
| 8/12/2026 | 07:40 | Dia Nacional da Família | 2 | Agenda online, link na bio | aprovada |
| 25/12/2026 | 07:40 | Natal | 2 | sem CTA | aprovada |
| 1/1/2027 | 07:40 | Ano Novo | 3 | Agenda online, link na bio | aprovada |
| 24/1/2027 | 07:40 | Dia do Aposentado | 3 | hubmaison.com/simuladorlongoprazo | aprovada |
| 6/2/2027 | 07:40 | Ano Novo Lunar | 2 | sem CTA | aprovada |
| 8/2/2027 | 07:40 | Carnaval | 3 | sem CTA | aprovada |
| 8/3/2027 | 07:40 | Dia Internacional da Mulher | 2 | sem CTA | aprovada |
| 15/3/2027 | 07:40 | Dia do Consumidor | 4 | WhatsApp (21) 98500-4567 | aprovada |
| 17/3/2027 | 07:40 | St. Patrick's Day (Irlanda) | 2 | sem CTA | aprovada |
| 26/3/2027 | 07:40 | Sexta-feira Santa | 2 | sóbrio | aprovada |
| 21/4/2027 | 07:40 | Tiradentes | 2 | sem CTA | aprovada |
| 1/5/2027 | 07:40 | Dia do Trabalho | 3 | hubmaison.com/simuladorlongoprazo | aprovada |
| 9/5/2027 | 07:40 | Dia das Mães | 3 | Agenda online, link na bio | aprovada |
| 2/6/2027 | 07:40 | Festa della Repubblica (Itália) | 2 | sem CTA | aprovada |
| 10/6/2027 | 07:40 | Dia de Portugal | 2 | sem CTA | aprovada |
| 12/6/2027 | 07:40 | Dia dos Namorados | 3 | Agenda online, link na bio | aprovada |
| 1/7/2027 | 07:40 | Canada Day | 2 | sem CTA | aprovada |
| 4/7/2027 | 07:40 | Independence Day (EUA) | 3 | hubmaison.com/cambio | aprovada |
| 7/7/2027 | 07:40 | Tanabata (Japão) | 2 | hubmaison.com/simuladorlongoprazo | aprovada |
| 14/7/2027 | 07:40 | Fête nationale (14 de julho, França) | 3 | sem CTA | aprovada |
| 20/7/2027 | 07:40 | Dia do Amigo | 2 | sem CTA | aprovada |
| 26/7/2027 | 07:40 | Dia dos Avós | 3 | WhatsApp (21) 98500-4567 | aprovada |
| 8/8/2027 | 07:40 | Dia dos Pais | 3 | sem CTA | aprovada |
| 7/9/2027 | 07:40 | Independência do Brasil | 3 | hubmaison.com/simuladorlongoprazo | aprovada |
| 15/9/2027 | 07:40 | Dia do Cliente | 3 | sem CTA | aprovada |
| 1/10/2027 | 07:40 | Dia Internacional da Pessoa Idosa | 3 | WhatsApp (21) 98500-4567 | aprovada |
| 12/10/2027 | 07:40 | Nossa Senhora Aparecida | 2 | sóbrio | aprovada |
| 12/10/2027 | 11:40 | Dia das Crianças | 3 | WhatsApp (21) 98500-4567 | aprovada |
| 31/10/2027 | 07:40 | Dia Mundial da Poupança | 5 | hubmaison.com/mapadosinvestimentos | aprovada |
| 2/11/2027 | 07:40 | Finados | 2 | sóbrio | aprovada |

## Profissões e especialidades médicas (desde 17/11/2026)

69 datas: 24 profissões e 45 especialidades médicas (todas as da agenda do CRM-PR 2026, menos o Dia da Mulher Médica, que não é especialidade). Ficam fora o Notário e Registrador (decisão do Gustavo) e o Aposentado, que já é data comemorativa. As 34 da galeria de 17/11 foram aprovadas em 18/11/2026; as 35 incluídas em 18/11 aguardam a revisão do Gustavo e só saem depois de entrarem em `aprovados.json`.

2 telas cada (capa e fechamento com o lema), sem CTA, legenda curta de homenagem e mensagem individual ao cliente daquela profissão. A lista usa a regra `profissao:<regex>` sobre a profissão cadastrada no CRM (a Mulher Empresária usa `profissao_f:`, que exige também sexo feminino); nada é inferido. Quando uma palavra do título não cabe na linha (Otorrinolaringologista), o template reduz o corpo só daquele título.

Dias com mais de um post: o segundo sai às 11h40, o terceiro às 16h40 e o quarto às 19h40 (campo `horario`). O caso extremo é 12/10: Aparecida 7h40, Crianças 11h40, Corretor de Seguros 16h40 e Cirurgião Pediátrico 19h40.

| Data | Hora | Dia | Grupo | Status |
|---|---|---|---|---|
| 3/12/2026 | 07:40 | Dia do Delegado de Polícia | profissão | aprovada |
| 4/12/2026 | 07:40 | Dia do Médico Perito | especialidade médica | pendente |
| 5/12/2026 | 07:40 | Dia do Médico de Família | especialidade médica | aprovada |
| 7/12/2026 | 07:40 | Dia do Cirurgião Plástico | especialidade médica | pendente |
| 11/12/2026 | 07:40 | Dia do Engenheiro | profissão | aprovada |
| 13/12/2026 | 07:40 | Dia do Marinheiro | profissão | aprovada |
| 14/12/2026 | 07:40 | Dia do Ministério Público | profissão | aprovada |
| 15/12/2026 | 07:40 | Dia do Arquiteto | profissão | aprovada |
| 5/2/2027 | 07:40 | Dia do Dermatologista | especialidade médica | aprovada |
| 5/2/2027 | 11:40 | Dia do Mastologista | especialidade médica | pendente |
| 10/2/2027 | 07:40 | Dia do Atleta Profissional | profissão | pendente |
| 3/3/2027 | 07:40 | Dia do Otorrinolaringologista | especialidade médica | pendente |
| 16/3/2027 | 07:40 | Dia do Clínico | especialidade médica | pendente |
| 7/4/2027 | 07:40 | Dia do Médico Legista | especialidade médica | aprovada |
| 11/4/2027 | 07:40 | Dia do Infectologista | especialidade médica | aprovada |
| 12/4/2027 | 07:40 | Dia do Obstetra | especialidade médica | aprovada |
| 14/4/2027 | 07:40 | Dia do Neurocirurgião | especialidade médica | aprovada |
| 7/5/2027 | 07:40 | Dia do Oftalmologista | especialidade médica | aprovada |
| 16/5/2027 | 07:40 | Dia do Geriatra | especialidade médica | pendente |
| 19/5/2027 | 07:40 | Dia do Defensor Público | profissão | aprovada |
| 27/5/2027 | 07:40 | Dia do Profissional Liberal | profissão | aprovada |
| 27/5/2027 | 11:40 | Dia do Cirurgião Torácico | especialidade médica | pendente |
| 29/5/2027 | 07:40 | Dia do Gastroenterologista | especialidade médica | pendente |
| 2/6/2027 | 11:40 | Dia do Pneumologista | especialidade médica | pendente |
| 17/6/2027 | 07:40 | Dia do Cirurgião de Mão | especialidade médica | pendente |
| 9/7/2027 | 07:40 | Dia do Oncologista Clínico | especialidade médica | pendente |
| 15/7/2027 | 07:40 | Dia do Pecuarista | profissão | pendente |
| 15/7/2027 | 11:40 | Dia do Médico Geneticista | especialidade médica | pendente |
| 16/7/2027 | 07:40 | Dia do Comerciante | profissão | pendente |
| 25/7/2027 | 07:40 | Dia do Médico Endoscopista | especialidade médica | pendente |
| 27/7/2027 | 07:40 | Dia do Pediatra | especialidade médica | aprovada |
| 28/7/2027 | 07:40 | Dia do Agricultor | profissão | pendente |
| 30/7/2027 | 07:40 | Dia do Cirurgião Geral | especialidade médica | pendente |
| 2/8/2027 | 07:40 | Dia do Nefrologista | especialidade médica | pendente |
| 5/8/2027 | 07:40 | Dia do Médico Patologista | especialidade médica | pendente |
| 11/8/2027 | 07:40 | Dia do Advogado e do Magistrado | profissão | aprovada |
| 11/8/2027 | 11:40 | Dia do Médico Acupunturista | especialidade médica | pendente |
| 13/8/2027 | 07:40 | Dia do Economista | profissão | aprovada |
| 13/8/2027 | 11:40 | Dia do Psiquiatra | especialidade médica | pendente |
| 14/8/2027 | 07:40 | Dia do Cardiologista | especialidade médica | aprovada |
| 15/8/2027 | 07:40 | Dia do Cirurgião Vascular | especialidade médica | pendente |
| 17/8/2027 | 07:40 | Dia da Mulher Empresária | profissão | aprovada |
| 19/8/2027 | 07:40 | Dia do Médico do Tráfego | especialidade médica | pendente |
| 25/8/2027 | 07:40 | Dia do Soldado | profissão | aprovada |
| 1/9/2027 | 07:40 | Dia do Endocrinologista | especialidade médica | pendente |
| 9/9/2027 | 07:40 | Dia do Administrador | profissão | aprovada |
| 9/9/2027 | 11:40 | Dia do Médico Fisiatra | especialidade médica | pendente |
| 14/9/2027 | 07:40 | Dia do Médico Nuclear | especialidade médica | pendente |
| 15/9/2027 | 11:40 | Dia do Reumatologista | especialidade médica | pendente |
| 15/9/2027 | 16:40 | Dia do Médico Nutrólogo | especialidade médica | pendente |
| 16/9/2027 | 07:40 | Dia do Médico Emergencista | especialidade médica | pendente |
| 19/9/2027 | 07:40 | Dia do Ortopedista | especialidade médica | aprovada |
| 21/9/2027 | 07:40 | Dia do Auditor Fiscal | profissão | aprovada |
| 22/9/2027 | 07:40 | Dia do Contador | profissão | aprovada |
| 4/10/2027 | 07:40 | Dia do Médico do Trabalho | especialidade médica | aprovada |
| 5/10/2027 | 07:40 | Dia do Empreendedor | profissão | aprovada |
| 12/10/2027 | 16:40 | Dia do Corretor de Seguros | profissão | aprovada |
| 12/10/2027 | 19:40 | Dia do Cirurgião Pediátrico | especialidade médica | pendente |
| 15/10/2027 | 07:40 | Dia do Neurologista | especialidade médica | pendente |
| 16/10/2027 | 07:40 | Dia do Anestesiologista | especialidade médica | aprovada |
| 18/10/2027 | 07:40 | Dia do Médico | profissão | aprovada |
| 23/10/2027 | 07:40 | Dia do Aviador | profissão | aprovada |
| 25/10/2027 | 07:40 | Dia do Dentista | profissão | aprovada |
| 28/10/2027 | 07:40 | Dia do Servidor Público | profissão | aprovada |
| 29/10/2027 | 07:40 | Dia do Hematologista e Hemoterapeuta | especialidade médica | pendente |
| 30/10/2027 | 07:40 | Dia do Ginecologista e Obstetra | especialidade médica | aprovada |
| 8/11/2027 | 07:40 | Dia do Radiologista | especialidade médica | aprovada |
| 10/11/2027 | 07:40 | Dia do Médico Intensivista | especialidade médica | pendente |
| 17/11/2027 | 07:40 | Dia do Alergista e Imunologista | especialidade médica | pendente |

Ícones novos: Lucide (ISC) e Tabler (MIT), no mesmo traço dourado.

Não entram: Corpus Christi (ponto facultativo), Páscoa (coberta pela Sexta-feira Santa) e Black Friday. Nenhuma peça cita número de países (decisão de 15/11/2026: a lista de países muda sempre).

## Ano Novo Lunar

O animal muda todo ano. `calendario.json` tem `animal_por_ano` (2027 Cabra, 2028 Macaco, 2029 Galo, 2030 Cão), que entra nos textos pelo marcador `{ano_lunar}`, e `icone_por_ano`, com o ícone de cada animal em `ICONES` do template. Hoje só a cabra (2027) está desenhada: o `render.py` recusa o ano que não tiver animal e ícone, então em outubro de 2027, ao renovar o calendário, é preciso desenhar o macaco. Leva a bandeira da China ao lado.

## Ícones e bandeiras

Ícones em traço dourado no `template/data-carrossel.html` (`ICONES`). Desenhos próprios e, desde 15/11/2026, alguns do Tabler Icons (sacola, idoso com bengala, aperto de mão com coração; MIT) e do Phosphor Icons, peso thin (tulipa, mão com coração; MIT). Datas de país usam a bandeira em cores reais (campo `bandeira` no `calendario.json`, arquivos em `bandeiras/`, do pacote flag-icons, MIT): Irlanda, Itália, Canadá, EUA, China (Ano Novo Lunar) e Independência do Brasil; Portugal leva caravela e bandeira. Nas telas do meio o emblema fica pequeno no canto superior esquerdo, longe do título.

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
2. Uma tarefa agendada do Claude dispara `postar-datas.yml` às 7h42 de cada data (ver "Horário" abaixo); o cron das 7h40 e 11h40 fica como reserva, e o workflow também roda quando `aprovados.json` muda na main. `hoje.py` lista as datas aprovadas do dia cujo horário já chegou; para cada uma sem `publicado.json`, renderiza, grava em `posts/AAAA-MM-DD/DATA-slug/` e publica pelo `instagram/postar.py`.
3. Instalado em 15/11/2026 na main do `hubmaison-comparador-ativos` (pasta `datas-comemorativas/` e `.github/workflows/postar-datas.yml`; `postar.py` aceita `DATA-slug`). Mesmo token (`IG_ACCESS_TOKEN`) e mesma fila (`concurrency: instagram`) da B3. Primeira publicação: Proclamação da República, 15/11/2026, https://www.instagram.com/p/DfxEbV-Emep/. O repositório é a fonte de verdade; este projeto guarda uma cópia.

## Horário: tarefas do Claude em cada data (17/11/2026)

O agendamento do próprio GitHub (cron do `postar-datas.yml`) está atrasando de 7 a 12 horas neste repositório: o disparo das 7h40 rodou entre 16h e 20h nos dias 16 e 17/11/2026, e o da B3 também. O atraso está no despacho do agendador do GitHub (a execução é criada já atrasada; não é fila de runner), problema relatado por outros usuários desde ago/2026 e sem correção do lado do repositório. Por isso cada data aprovada tem uma tarefa agendada do Claude, uma por post (33 datas comemorativas de 20/11/2026 a 02/11/2027 e, desde 18/11/2026, as profissões e especialidades aprovadas), dois minutos depois do horário do post (7h42, 11h42, 16h42 ou 19h42), que dispara o `postar-datas.yml` por `workflow_dispatch` (sem atraso; testado em 17/11/2026: começou 1 minuto depois), espera, confere o `publicado.json` e manda uma notificação com o link. O cron do workflow fica como reserva: se a tarefa falhar, ele publica mais tarde no mesmo dia. Nada é publicado duas vezes (pasta com `publicado.json` é pulada).

Ao renovar o calendário (outubro), criar as tarefas do novo ciclo. A tarefa de Finados (02/11/2027) avisa isso.

## Todo ano

Em outubro, rodar `render.py` para os 12 meses seguintes e mandar a galeria para revisão. Datas móveis (Mães, Pais) e `{ano}` do Ano Novo se ajustam sozinhos.

## Pendências

- `bloco_xp.txt` fica vazio: desde 15/11/2026 a legenda não leva identificação da XP nem ouvidoria (decisão do Gustavo, ciente de que a Res. CVM 178, art. 24 pede as duas). A identificação fica só no lockup Maison Invest | XP das telas; a linha "assessora credenciada à XP" também saiu da última tela.
- Confirmar a história pessoal no Dia dos Pais.
- Criar no CRM os campos "filhos" e "netos" se quiser as listas de Mães, Pais, Avós e a parte "com filhos" das Crianças.
- Trocar Montserrat por Gotham se o ambiente de render tiver a fonte.
