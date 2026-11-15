# Datas comemorativas (@maison.invest)

Kit para o Claude Code publicar, a cada data comemorativa e feriado nacional, um carrossel no Instagram da Maison Invest, e para o time mandar uma mensagem individual aos clientes daquela data. Irmão dos kits `ipca-mensal/`, `igpm-mensal/` e `focus-semanal/`: mesmo visual, mesmo formato de pasta da branch `posts` e o mesmo `instagram/postar.py` dos resultados da B3. Montado em 12/11/2026.

As profissões (Dia do Médico, do Servidor etc.) ficam no calendário das profissões, não aqui.

## Estrutura

```
calendario.json              as 14 datas: regra da data, ícone, textos das telas, legenda, mensagem ao cliente, regra da lista
template/data-carrossel.html template único; desenha capa, miolo (educativo, texto ou números), fechamento e o card do WhatsApp
render.py                    valida (tamanhos, travessão, palavras de risco, limite do Instagram) e gera saida/AAAA-MM-DD/DATA-slug/
listas.py                    lê o export da Base XP/CRM (CSV ou XLSX) e gera listas/AAAA-MM-DD-slug.csv com a mensagem personalizada
hoje.py                      diz ao workflow se a data do dia está aprovada
aprovados.json               o que o Gustavo aprovou (AAAA-MM-DD/slug); só isso sai sozinho
bloco_xp.txt                 identificação XP da legenda (mesmo bloco do Focus e do IPCA)
publicacao/postar-datas.yml  workflow diário (7h40) para .github/workflows/ do repositório hubmaison-comparador-ativos
publicacao/postar.py.patch   uma linha no postar.py para aceitar pastas AAAA-MM-DD/DATA-slug
logo-invest-xp-negativo.svg  da skill maison: assets/logos/invest-xp/cor-negativo.svg
fonts/                       Montserrat 300 a 900 (npm pack @fontsource/montserrat)
```

Rodar: `python3 render.py --de 2026-11-12 --ate 2027-11-11 --chrome /caminho/do/chrome` (sem datas, faz os próximos 12 meses). `--so criancas,maes` faz só algumas.

## O calendário (nov/2026 a nov/2027)

25 datas: os 10 feriados nacionais (Nossa Senhora Aparecida vira uma linha na legenda do Dia das Crianças, no mesmo 12/10), as datas de relação e quatro datas internacionais para os clientes no exterior (Thanksgiving, 4 e 14 de julho, além do Dia do Amigo).

| Data | Dia | Telas | CTA | Lista de clientes |
|---|---|---|---|---|
| 15/11/2026 | Proclamação da República | 3 | hubmaison.com/simuladortesouronacional | Só post, sem mensagem individual. |
| 20/11/2026 | Dia Nacional de Zumbi e da Consciência Negra | 2 | sóbrio, sem CTA | Só post, sem mensagem individual. |
| 26/11/2026 | Thanksgiving (Ação de Graças, EUA) | 2 | sem CTA (relação) | Clientes com país de residência nos Estados Unidos, se o cadastro tiver o campo. |
| 8/12/2026 | Dia Nacional da Família | 2 | Agenda online, link na bio | Todos os clientes ativos. |
| 25/12/2026 | Natal | 2 | sem CTA (relação) | Todos os clientes ativos. |
| 1/1/2027 | Ano Novo | 3 | Agenda online, link na bio | Todos os clientes ativos. |
| 24/1/2027 | Dia do Aposentado | 3 | hubmaison.com/simuladorlongoprazo | Clientes com a profissão cadastrada como aposentado(a). Não se infere pela idade. |
| 8/3/2027 | Dia Internacional da Mulher | 2 | sem CTA (relação) | Clientes com sexo feminino no cadastro. |
| 15/3/2027 | Dia do Consumidor | 3 | WhatsApp (21) 98500-4567 | Só post. Data informativa, sem mensagem individual. |
| 26/3/2027 | Sexta-feira Santa | 2 | sóbrio, sem CTA | Só post, sem mensagem individual. |
| 21/4/2027 | Tiradentes | 2 | sem CTA (relação) | Só post, sem mensagem individual. |
| 1/5/2027 | Dia do Trabalho | 3 | hubmaison.com/simuladorlongoprazo | Só post, sem mensagem individual. |
| 9/5/2027 | Dia das Mães | 3 | Agenda online, link na bio | Clientes do sexo feminino com filhos marcados no CRM. Sem o campo de filhos, a lista sai vazia: nunca inferir maternidade pela idade. |
| 12/6/2027 | Dia dos Namorados | 3 | Agenda online, link na bio | Clientes com estado civil casado(a) ou em união estável, se o cadastro tiver o campo. |
| 4/7/2027 | Independence Day (EUA) | 3 | hubmaison.com/cambio | Clientes com país de residência nos Estados Unidos, se o cadastro tiver o campo. |
| 14/7/2027 | Fête nationale (14 de julho, França) | 3 | sem CTA (relação) | Clientes com país de residência na França, se o cadastro tiver o campo. |
| 20/7/2027 | Dia do Amigo | 2 | sem CTA (relação) | Todos os clientes ativos. |
| 26/7/2027 | Dia dos Avós | 3 | WhatsApp (21) 98500-4567 | Clientes com netos marcados no CRM. Sem o campo, a lista sai vazia. |
| 8/8/2027 | Dia dos Pais | 3 | sem CTA (relação) | Clientes do sexo masculino com filhos marcados no CRM. Sem o campo de filhos, a lista sai vazia. |
| 7/9/2027 | Independência do Brasil | 3 | hubmaison.com/simuladorlongoprazo | Só post, sem mensagem individual. |
| 15/9/2027 | Dia do Cliente | 3 | sem CTA (relação) | Todos os clientes ativos. |
| 1/10/2027 | Dia Internacional da Pessoa Idosa | 3 | WhatsApp (21) 98500-4567 | Clientes com 60 anos ou mais na data (Estatuto da Pessoa Idosa), pela data de nascimento do cadastro. |
| 12/10/2027 | Dia das Crianças | 3 | WhatsApp (21) 98500-4567 | Dois grupos: clientes com filhos marcados no CRM (recebem a ideia do cadastro de menor) e cadastros de menores já existentes (recebem só a felicitação, endereçada à família; o telefone costuma ser do responsável). |
| 31/10/2027 | Dia Mundial da Poupança | 5 | hubmaison.com/mapadosinvestimentos | Só post. Data informativa, sem mensagem individual. |
| 2/11/2027 | Finados | 2 | sóbrio, sem CTA | Só post, sem mensagem individual. |

Não entram: Carnaval e Corpus Christi (pontos facultativos, não feriados nacionais), Páscoa (coberta pela Sexta-feira Santa) e Black Friday.

## Regras de conteúdo (da skill maison)

- Data comemorativa fala da relação; o produto entra só como explicação de como funciona, sem oferta, taxa ou rentabilidade (A9). Conteúdo educativo leva "não constitui recomendação" na legenda.
- Pouco texto na imagem, explicação na legenda; dourado só em ícones, números do miolo e no contorno do botão do CTA; numeral da capa em tom sobre tom.
- Sem traços decorativos (fios curtos, marcadores de linha, "·", "▪️"): o Gustavo achou com cara de IA em 12/11/2026. O `render.py` recusa " · " e "▪". Topo só com a data, sem "Datas que importam".
- CTA por data, ligado ao tema: simulador de renda, simulador do Tesouro, mapa dos investimentos, câmbio, agenda ou WhatsApp. Datas de relação (Natal, Mulher, Pais, Cliente, Amigo) e datas sóbrias (Consciência Negra, Sexta-feira Santa, Finados) saem sem CTA; as sóbrias também sem o lema.
- Natal fala em clientes "ao redor do mundo", sem o número de países.
- Sem travessão, sem "garantido", "grátis", "consultoria", "gestão" (o `render.py` recusa).
- Todo post leva o lockup Maison Invest | XP e o bloco XP da legenda (Res. CVM 178, art. 24).

## Listas de clientes

`python3 listas.py --todas export.csv` mostra quantos clientes cada data alcança e quais campos faltam. `python3 listas.py criancas export.csv --data 2027-10-12` gera o CSV com grupo, nome, telefone, assessor e mensagem. Nada é inferido: mães, pais e avós dependem de um campo "filhos" e "netos" no CRM (hoje não existe); sem ele a lista sai vazia. Envio individual pelo assessor, nunca em massa.

## Publicação

1. Gustavo revisa a galeria e aprova; cada aprovação vira uma linha `AAAA-MM-DD/slug` em `aprovados.json`.
2. Todo dia às 7h40, `postar-datas.yml` roda `hoje.py`. Com data aprovada, `bloco_xp.txt` sem "[" e sem `publicado.json`, renderiza, grava em `posts/AAAA-MM-DD/DATA-slug/` e publica pelo `instagram/postar.py`.
3. Para instalar: copiar esta pasta para `datas-comemorativas/` na main do `hubmaison-comparador-ativos`, o workflow para `.github/workflows/` e aplicar `postar.py.patch`. Mesmo token (`IG_ACCESS_TOKEN`) e mesma fila (`concurrency: instagram`) da B3.

## Todo ano

Em outubro, rodar `render.py` para os 12 meses seguintes e mandar a galeria para revisão. Datas móveis (Mães, Pais) e `{ano}` do Ano Novo se ajustam sozinhos.

## Pendências

- Link da relação de assessores no `bloco_xp.txt` (o mesmo pendente do Focus e do IPCA). Sem ele, nada publica.
- Confirmar a história pessoal no Dia dos Pais.
- Criar no CRM os campos "filhos" e "netos" se quiser as listas de Mães, Pais, Avós e a parte "com filhos" das Crianças.
- Trocar Montserrat por Gotham se o ambiente de render tiver a fonte.
