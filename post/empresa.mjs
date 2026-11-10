// Template "Resultado da empresa" da Maison Invest: 7 ou 8 telas 1080x1350 e a legenda, a partir do JSON da branch resultados.
// Uso: MAISON_WORK=<pasta preparada por preparar.sh> node empresa.mjs dados.json pasta-de-saida
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const HERE = path.dirname(new URL(import.meta.url).pathname);
const STUDIO = process.env.MAISON_WORK || path.join(HERE, '..');

// ---------------------------------------------------------------- cálculos
const ltm = (a, i) => { const w = a.slice(i - 3, i + 1); return i < 3 || w.some(x => x == null) ? null : w.reduce((s, x) => s + x, 0); };
// NaN = n.m.: valor negativo (ou n.m.) em um dos períodos, ou variação acima de 999% (base perto de zero)
const pct = (a, b) => (Number.isNaN(a) || Number.isNaN(b) ? NaN : a == null || !b ? null : a < 0 || b < 0 ? NaN : Math.abs(a / b - 1) >= 10 ? NaN : a / b - 1);
const sen = (a, b, r) => (r == null ? null : Number.isNaN(r) ? (Number.isNaN(a) || Number.isNaN(b) ? null : Math.sign(a - b)) : r); // sentido, para seta e rótulo
// múltiplos: n.m. acima de 100x (denominador perto de zero) ou com PL, lucro ou EBITDA de 12 meses negativo
const corta = (v) => (v != null && v > 100 ? NaN : v);
export function multHoje(d) {
  const S = d.serie, n = d.trimestres.length - 1, m = d.multiplos;
  const neg = (v, den) => (v == null && den != null && den <= 0 ? NaN : corta(v));
  return { pvp: neg(m.pvp, S.pl ? S.pl[n] : null), pl: neg(m.pl, S.lucro ? ltm(S.lucro, n) : null),
    ev: d.financeira ? null : neg(m.ev_ebitda, S.ebitda ? ltm(S.ebitda, n) : null) };
}
export function calcula(d) {
  const S = d.serie, n = d.trimestres.length - 1;
  const fluxo = ['receita', 'ebitda', 'lucro'], estoque = ['pl', 'divida', 'ativos'];
  const nivel = (k, i) => (fluxo.includes(k) ? ltm(S[k], i) : S[k][i]);
  const tem = (k) => S[k] && S[k][n] != null && !(d.financeira && k === 'ebitda');
  const out = { tri: {}, tend: {}, var: {}, spark: {} };
  for (const k of fluxo.filter(tem)) { const a = S[k][n], b = S[k][n - 4], r = pct(a, b); out.tri[k] = { v: a, yoy: r, s: sen(a, b, r) }; }
  for (const k of [...fluxo, ...estoque].filter(tem)) {
    const a = nivel(k, n), b = nivel(k, n - 4), r = pct(a, b), s = sen(a, b, r);
    out.tend[k] = { r, s, lab: s > 0.02 ? 'Crescente' : s < -0.02 ? 'Decrescente' : 'Estável' };
    out.spark[k] = Array.from({ length: 12 }, (_, j) => nivel(k, n - 11 + j));
  }
  for (const k of ['pl', 'ebitda', 'receita'].filter(tem)) {
    out.var[k] = [4, 8, 12].map(m => (n - m - (fluxo.includes(k) ? 3 : 0) >= 0 ? pct(nivel(k, n), nivel(k, n - m)) : null));
  }
  // 12, 24 e 36 meses: 'linha' compara o acumulado de 12 meses (fluxos) ou o nível (estoques), como o comparador;
  // 'barras' compara o trimestre com o mesmo trimestre de 1, 2 e 3 anos antes. Série de 13 pontos (36 meses + a base).
  out.hor = { linha: {}, barras: {} }; out.s13 = { linha: {}, barras: {} };
  for (const k of [...fluxo, ...estoque].filter(tem)) {
    for (const [modo, f, i0] of [['linha', i => nivel(k, i), fluxo.includes(k) ? 3 : 0], ['barras', i => S[k][i], 0]]) {
      out.hor[modo][k] = [4, 8, 12].map(m => { if (n - m < i0) return { r: null, s: null }; const a = f(n), b = f(n - m), r = pct(a, b); return { r, s: sen(a, b, r) }; });
      out.s13[modo][k] = Array.from({ length: 13 }, (_, j) => (n - 12 + j >= i0 ? f(n - 12 + j) : null));
    }
    out.yoy13 = out.yoy13 || {};
    out.yoy13[k] = Array.from({ length: 13 }, (_, j) => { const i = n - 12 + j; return i - 4 >= 0 ? pct(S[k][i], S[k][i - 4]) : null; });
  }
  // capa: o indicador com a maior variação, para cima ou para baixo, contra o mesmo trimestre do ano anterior
  // (trimestre para receita, EBITDA e lucro; fim do trimestre para PL, dívida e ativo); n.m. fica de fora
  for (const k of [...fluxo, ...estoque].filter(tem)) {
    const a = S[k][n], b = S[k][n - 4], r = pct(a, b);
    if (r != null && !Number.isNaN(r) && (!out.capa || Math.abs(r) > Math.abs(out.capa.r))) out.capa = { k, a, b, r, estoque: estoque.includes(k) };
  }
  return out;
}

// ---------------------------------------------------------------- formatos pt-BR
const nf = (x, d = 1) => x.toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }).replace(/[\u00a0\u202f]/g, ' ');
// valores do JSON em bilhões de reais; a escala escolhe tri, bi, mi ou mil e 3 algarismos significativos
const escala = (bi) => { const a = Math.abs(bi); return a >= 1000 ? [a / 1000, 'tri'] : a >= 1 ? [a, 'bi'] : a >= 0.001 ? [a * 1000, 'mi'] : [a * 1e6, 'mil']; };
const dec = (v) => (v >= 100 ? 0 : v >= 10 ? 1 : 2);
export const brl = (bi) => { if (bi == null) return 'n/d'; const [v, u] = escala(bi); return `${bi < 0 ? '−' : ''}R$ ${nf(v, dec(v))} ${u}`; };
const brlH = (bi, big, small) => { if (bi == null) return `<span style="font-size:${big}px;color:var(--sky)">n/d</span>`; const [v, u] = escala(bi); return `<span style="font-size:${small}px;color:var(--sky);font-weight:400;margin-right:.32em">${bi < 0 ? '−' : ''}R$</span><span style="font-size:${big}px;font-variant-numeric:lining-nums proportional-nums">${nf(v, dec(v))}</span><span style="font-size:${small}px;color:var(--mist);font-weight:500;letter-spacing:.02em;margin-left:.28em">${u}</span>`; };
export const fpct = (r) => (r == null ? 'n/d' : Number.isNaN(r) ? 'n.m.' : `${r > 0 ? '+' : r < 0 ? '−' : ''}${nf(Math.abs(r) * 100, 1)}%`);
const fx = (m) => (m == null ? 'n/d' : Number.isNaN(m) ? 'n.m.' : `${nf(m, 2)}x`);
const fdate = (s) => (s ? s.split('-').reverse().join('/') : '');
// capa: valor com uma casa (sem casa a partir de 100) e variação inteira (uma casa abaixo de 10%), para ler de longe
const brlCapa = (bi) => { const [v, u] = escala(bi); return [bi < 0 ? '−' : '', nf(v, v >= 100 ? 0 : 1), u]; };
const pctCapa = (r) => `${r > 0 ? '+' : r < 0 ? '−' : ''}${nf(Math.abs(r) * 100, Math.abs(r) >= 0.1 ? 0 : 1)}%`;
const ARW = (r, z = 30) => r == null ? '' : `<svg viewBox="0 0 24 24" width="${z}" height="${z}" fill="none" stroke="currentColor" stroke-width="1.8"><path d="${r > 0.02 ? 'M7 17L17 7M9 7h8v8' : r < -0.02 ? 'M7 7l10 10M17 9v8H9' : 'M4 12h16M14 6l6 6-6 6'}"/></svg>`;

// série com pontos em destaque (marcas) e o último ponto em dourado; 13 trimestres (marcas 0, 4, 8) ou 37 meses (0, 12, 24)
// rotulo (opcional): função que formata o valor; escreve o valor sobre cada ponto em destaque e sobre o último, numa faixa
// de 30 px acima do gráfico (a altura total passa a ser h + 30)
function grafLinha(v, w, h, marcas = [0, 4, 8], rotulo = null) {
  const ok = v.map((y, i) => [y, i]).filter(([y]) => y != null && !Number.isNaN(y)), ys = ok.map(([y]) => y);
  if (!ok.length) return '';
  const top = rotulo ? 30 : 0, H = h + top;
  const lo = Math.min(...ys), hi = Math.max(...ys), sp = hi - lo || 1, n1 = v.length - 1;
  const P = ([y, i]) => [i * (w - 8) / n1 + 4, H - 8 - (y - lo) / sp * (h - 16)];
  const pts = ok.map(P), dd = pts.map((p, j) => (j ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const marc = ok.filter(([, i]) => marcas.includes(i));
  const base = marc.map(P).map(([x, y]) => `<circle cx="${x}" cy="${y}" r="4.5" fill="#293654" stroke="#b2cbe6" stroke-width="2"/>`).join('');
  const [lx, ly] = pts[pts.length - 1];
  const txt = ([y, i], ult) => {
    const [x, py] = P([y, i]), anc = x < 40 ? 'start' : x > w - 40 ? 'end' : 'middle';
    return `<text x="${x.toFixed(1)}" y="${(py - 12).toFixed(1)}" text-anchor="${anc}" font-size="19" font-weight="${ult ? 600 : 500}" fill="${ult ? 'var(--accent)' : '#dbe5f0'}" stroke="#26324f" stroke-width="7" stroke-linejoin="round" paint-order="stroke" style="font-variant-numeric:tabular-nums">${rotulo(y)}</text>`;
  };
  const fim = ok[ok.length - 1], rot = rotulo ? marc.map(m => txt(m, false)).join('') + (fim[1] === n1 ? txt(fim, true) : '') : '';   // valor de hoje só se houver (n.m. fica sem rótulo)
  return `<svg viewBox="0 0 ${w} ${H}" width="${w}" height="${H}" style="overflow:visible"><path d="${dd} L${lx} ${H} L${pts[0][0]} ${H}Z" fill="rgba(147,172,198,.10)"/><path d="${dd}" fill="none" stroke="#93acc6" stroke-width="2.5" stroke-linejoin="round"/>${base}${!rotulo || fim[1] === n1 ? `<circle cx="${lx}" cy="${ly}" r="6" fill="var(--accent)"/>` : ''}${rot}</svg>`;
}
// barras dos 13 trimestres com o valor em cima de cada barra (embaixo, se negativo) e o trimestre no pé; a unidade da linha
// sai do maior valor (tri, bi, mi ou mil) e vai no cabeçalho do cartão
function grafBarrasValores(v, tri, w, h, yoy = null) {
  const ys = v.filter(y => y != null);
  if (!ys.length) return { svg: '', u: '' };
  const [, u] = escala(Math.max(...ys.map(Math.abs))), div = { tri: 1000, bi: 1, mi: 0.001, mil: 1e-6 }[u];
  const dd = dec(Math.max(...ys.map(y => Math.abs(y) / div)));
  const lo = Math.min(0, ...ys), hi = Math.max(0, ...ys), sp = hi - lo || 1;
  const topo = 34, pe = 30, hb = h - topo - pe - (lo < 0 ? 28 : 0), slot = w / v.length, bw = Math.min(54, slot * 0.8);
  const Y = (y) => topo + (hi - y) / sp * hb, y0 = Y(0);
  const cor = (i) => (i === v.length - 1 ? 'var(--accent)' : (v.length - 1 - i) % 4 === 0 ? 'rgba(178,203,230,.78)' : 'rgba(147,172,198,.26)');
  const corT = (i) => (i === v.length - 1 ? '#C8A96A' : (v.length - 1 - i) % 4 === 0 ? '#b2cbe6' : '#93acc6');
  const g = v.map((y, i) => {
    const cx = i * slot + slot / 2, ult = i === v.length - 1;
    const tq = `<text x="${cx}" y="${h - 6}" text-anchor="middle" font-size="16" font-weight="500" fill="${ult ? '#C8A96A' : '#93acc6'}">${tri[i] || ''}</text>`;
    if (y == null) return tq + `<text x="${cx}" y="${y0 - 10}" text-anchor="middle" font-size="18" fill="#93acc6">n/d</text>`;
    const y1 = Y(y), txt = (y < 0 ? '−' : '') + nf(Math.abs(y) / div, dd);
    // variação de 12 meses no meio das barras em destaque; barra baixa demais: o número vai junto do valor, por fora
    let vz = '';
    if (yoy && (v.length - 1 - i) % 4 === 0) {
      const alt = Math.abs(y1 - y0);
      const tv = fpct(yoy[i]), fz = tv.length > 6 ? 13 : 15;   // +100,0% e maiores: fonte menor para caber na barra
      vz = alt >= 28 ? `<text x="${cx}" y="${((y0 + y1) / 2 + 5.5).toFixed(1)}" text-anchor="middle" font-size="${fz}" font-weight="600" fill="#293654">${tv}</text>`
        : `<text x="${cx}" y="${(y >= 0 ? y1 - 32 : y1 + 44).toFixed(1)}" text-anchor="middle" font-size="15" font-weight="500" fill="#b2cbe6">${fpct(yoy[i])}</text>`;
    }
    return `<rect x="${(cx - bw / 2).toFixed(1)}" y="${Math.min(y0, y1).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1.5, Math.abs(y1 - y0)).toFixed(1)}" fill="${cor(i)}"/>`
      + `<text x="${cx}" y="${(y >= 0 ? y1 - 10 : y1 + 24).toFixed(1)}" text-anchor="middle" font-size="19" font-weight="${i === v.length - 1 ? 600 : 400}" fill="${corT(i)}">${txt}</text>` + vz + tq;
  }).join('');
  return { svg: `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" font-family="M" style="font-variant-numeric:lining-nums">${g}${lo < 0 ? `<line x1="0" x2="${w}" y1="${y0}" y2="${y0}" stroke="#93acc6" stroke-width="1"/>` : ''}</svg>`, u };
}
function grafBarras(v, w, h) {
  const ys = v.filter(y => y != null), lo = Math.min(0, ...ys), hi = Math.max(0, ...ys), sp = hi - lo || 1;
  const bw = 22, gap = (w - 13 * bw) / 12, Y = (y) => (hi - y) / sp * (h - 2) + 1;
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">${v.map((y, i) => {
    if (y == null) return '';
    const cor = i === 12 ? 'var(--accent)' : (i === 0 || i === 4 || i === 8) ? 'rgba(178,203,230,.78)' : 'rgba(147,172,198,.26)';
    const y0 = Y(0), y1 = Y(y);
    return `<rect x="${(i * (bw + gap)).toFixed(1)}" y="${Math.min(y0, y1).toFixed(1)}" width="${bw}" height="${Math.max(1.5, Math.abs(y1 - y0)).toFixed(1)}" fill="${cor}"/>`;
  }).join('')}${lo < 0 ? `<line x1="0" x2="${w}" y1="${Y(0)}" y2="${Y(0)}" stroke="#93acc6" stroke-width="1"/>` : ''}</svg>`;
}

function spark(v, w = 380, h = 92) {
  const lo = Math.min(...v), hi = Math.max(...v), sp = hi - lo || 1;
  const pts = v.map((y, i) => [i * (w / (v.length - 1)), h - 10 - (y - lo) / sp * (h - 20)]);
  const d = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const [lx, ly] = pts[pts.length - 1];
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><path d="${d} L${w} ${h} L0 ${h}Z" fill="rgba(147,172,198,.10)"/><path d="${d}" fill="none" stroke="#93acc6" stroke-width="2.5" stroke-linejoin="round"/><circle cx="${lx - 1}" cy="${ly}" r="6" fill="var(--accent)"/></svg>`;
}

// ---------------------------------------------------------------- telas
const LABEL = { receita: 'Receita líquida', ebitda: 'EBITDA', lucro: 'Lucro líquido', pl: 'Patrimônio líquido', divida: 'Dívida bruta', ativos: 'Ativo total' };
const NM = ' n.m.: não mensurável, há valor negativo em um dos períodos ou a variação passa de 999%.';
const EBITDA_DEF = 'Resultado antes do resultado financeiro e dos tributos, mais depreciação e amortização (DVA), sem os ajustes que a empresa divulga';
const NMX =' n.m.: não mensurável, PL, lucro ou EBITDA de 12 meses negativo, ou múltiplo acima de 100x.';
const LEGAL_TELA = 'Conteúdo informativo, sem recomendação de compra ou venda.';   // na última tela; a legenda leva o LEGAL completo
const LEGAL = 'Conteúdo informativo, sem recomendação de compra ou venda. Maison Invest, assessora de investimentos credenciada à XP Investimentos. Ouvidoria XP: 0800 722 3730.';

function logoEmpresa(d, h = d.logoH || 120) {
  // logo da biblioteca na versão da capa (branca, cor ou placa, escolhida por placa.py); placa com cantos arredondados
  if (d.logo) return `<img src="${d.logo}" alt="${d.empresa}" style="height:${h}px;max-width:560px;object-fit:contain;display:block;border-radius:14px">`;
  // sem logo aprovada (ausente ou com a marca anterior): o nome da empresa em texto, no lugar da logo
  return `<div style="height:${h}px;display:flex;align-items:center;font-size:${Math.round(Math.min(76, h * 0.62))}px;font-weight:600;letter-spacing:-.015em;line-height:1;color:#fff">${d.empresa}</div>`;
}
const head = (d, i, n) => `<div class="top"><div class="kicker"><i class="leg"></i>${d.ticker} · ${d.periodo}</div><div class="count">${String(i).padStart(2, '0')} / ${String(n).padStart(2, '0')}</div></div>`;
const foot = (i, n) => `<div class="bottom"><div class="prog">${Array.from({ length: n }, (_, j) => `<i class="${j + 1 === i ? 'on' : ''}"></i>`).join('')}</div><img class="sym" src="assets/symbol.png" alt=""></div>`;
const band = (d) => d.ilustrativo ? `<div style="position:absolute;left:0;right:0;top:0;height:46px;background:#C8A96A;color:#293654;font-size:20px;font-weight:700;letter-spacing:.3em;display:grid;place-items:center;z-index:5">DADOS ILUSTRATIVOS · MODELO</div>` : '';
const src = (t) => `<p class="small" style="margin-top:28px">${t}</p>`;

export function telas(d) {
  const c = calcula(d), H = d.historico && d.historico.datas && d.historico.datas.length > 36 ? d.historico : null;
  const invest = `<img class="logo" src="assets/invest-xp.png" style="height:70px" alt="Maison Invest">`;
  // barras por trimestre: um slide com até 3 indicadores; com mais, resultado (fluxos) e balanço (estoques) separados
  const fluxo3 = ['receita', 'ebitda', 'lucro'];
  const kb = ['receita', 'ebitda', 'lucro', 'pl', 'divida', 'ativos'].filter(k => c.s13.barras[k]);
  const grupos = (kb.length <= 3 ? [['Por trimestre.', kb]] : [['Resultado por trimestre.', kb.filter(k => fluxo3.includes(k))], ['Balanço por trimestre.', kb.filter(k => !fluxo3.includes(k))]]).filter(g => g[1].length);
  const nM = 4 + grupos.length, nH = nM + 1, N = nM + (H ? 2 : 1);
  const T = [];
  // 1 capa: resultado ou notícia
  const noticia = d.capa.tipo === 'noticia';
  const capaR = !noticia && c.capa, ant = d.trimestres[d.trimestres.length - 5];
  T.push(`<img class="legs" src="assets/symbol.png" style="left:520px;top:420px;height:1100px;opacity:.05"><div class="frame"><div class="top">${invest}<div class="swipe">Arraste <svg viewBox="0 0 56 14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M0 7h54M47 1l7 6-7 6"/></svg></div></div>
    <div style="margin-top:120px">${logoEmpresa(d)}<div style="margin-top:34px;display:flex;gap:20px;align-items:baseline"><span style="font-size:26px;font-weight:600;letter-spacing:.16em;color:var(--sky)">${d.ticker}</span>${d.logo ? `<span style="font-size:26px;color:var(--mist)">${d.empresa}</span>` : ''}</div></div>
    <div style="margin-top:auto"><div class="kicker" style="margin-bottom:30px"><i class="leg"></i>${noticia ? 'Notícia · ' + fdate(d.noticia.data) : 'Resultado do ' + d.periodo}</div>
    ${capaR ? (() => { const m = c.capa, [sg, num, un] = brlCapa(m.a);
      return `<div style="font-size:44px;font-weight:400;letter-spacing:-.01em">${LABEL[m.k]}${m.estoque ? '<span style="color:var(--mist);font-size:30px"> · fim do ' + d.periodo + '</span>' : ''}</div>
      <div style="margin-top:6px;display:flex;align-items:baseline;white-space:nowrap;font-variant-numeric:lining-nums"><span style="font-size:52px;color:var(--sky);margin-right:18px">${sg}R$</span><span style="font-size:210px;font-weight:200;letter-spacing:-.04em;line-height:1">${num}</span><span style="font-size:68px;color:var(--mist);margin-left:16px;font-weight:400">${un}</span></div>
      <div style="margin-top:34px;display:flex;align-items:center;gap:30px;color:var(--accent)"><div style="display:flex;align-items:center;gap:10px">${ARW(m.r, 58)}<span style="font-size:92px;font-weight:500;letter-spacing:-.03em;line-height:1">${pctCapa(m.r)}</span></div>
      <div style="border-left:1px solid var(--hair);padding-left:30px"><div style="font-size:22px;font-weight:600;letter-spacing:.18em;color:var(--sky);text-transform:uppercase">contra o ${ant}</div><div style="font-size:28px;color:var(--mist);margin-top:6px">${brl(m.b)}</div></div></div>`; })()
    : `<h2 style="max-width:900px">${(noticia ? d.noticia.titulo : (d.capa.destaque || 'Resultado do ' + d.periodo + '.')).replace(/R\$ ?[\d.,]+( (mi|bi|milhões|bilhões|mil))?/g, x => `<span style="white-space:nowrap">${x}</span>`)}</h2>${noticia ? src('Fonte: ' + d.noticia.fonte) : ''}`}</div>
    ${!noticia && d.divulgacao ? `<div style="margin-top:40px;font-size:15px;letter-spacing:.02em;color:var(--sky);opacity:.5">Divulgado em ${fdate(d.divulgacao)}${d.entrega && d.entrega.hora ? ', às ' + d.entrega.hora : ''}</div>` : ''}
    <div style="margin-top:${!noticia && d.divulgacao ? 24 : 64}px">${foot(1, N).replace('<img class="sym" src="assets/symbol.png" alt="">', '')}</div></div>`);
  // 2 o trimestre
  T.push(`<div class="frame">${head(d, 2, N)}<h3 style="margin-top:100px">O ${d.periodo} em números.</h3>
    <div style="margin-top:56px;border-top:1px solid var(--hair)">${['receita', 'ebitda', 'lucro'].filter(k => c.tri[k]).map(k => `<div style="display:grid;grid-template-columns:1fr auto;align-items:end;padding:40px 0;border-bottom:1px solid var(--hair)">
      <div><div class="tag" style="color:var(--sky);font-size:22px">${LABEL[k]}</div><div style="font-size:84px;font-weight:300;letter-spacing:-.02em;margin-top:14px;font-variant-numeric:tabular-nums">${brlH(c.tri[k].v, 84, 40)}</div></div>
      <div style="text-align:right;color:var(--accent)">${ARW(c.tri[k].s)}<div style="font-size:34px;font-weight:500;font-variant-numeric:tabular-nums">${fpct(c.tri[k].yoy)}</div><div style="font-size:20px;color:var(--sky);letter-spacing:.12em">VS ${d.trimestres[d.trimestres.length - 5]}</div></div></div>`).join('')}</div>
    ${src('Fonte: ' + d.fontes.demonstracoes + '.' + (Object.values(c.tri).some(x => Number.isNaN(x.yoy)) ? NM : ''))}${foot(2, N)}</div>`);
  // 3 12, 24 e 36 meses: valor com unidade, gráfico de 36 meses e as três variações ('linha' ou 'barras')
  const ks = ['receita', 'ebitda', 'lucro', 'pl', 'divida', 'ativos'].filter(k => c.tend[k]);
  const modo = d.grafico === 'barras' ? 'barras' : 'linha', ini = d.trimestres[d.trimestres.length - 13];
  const card = (k) => {
    const s = c.s13[modo][k], hint = modo === 'linha' && fluxo3.includes(k) ? 'soma 12 meses' : d.periodo;
    return `<div style="padding:20px 0 22px;border-top:1px solid var(--hair)">
      <div style="display:flex;justify-content:space-between;align-items:baseline"><span style="font-size:22px;font-weight:500">${LABEL[k]}</span><span style="font-size:16px;font-weight:600;letter-spacing:.16em;color:var(--sky);text-transform:uppercase">${hint}</span></div>
      <div style="margin-top:4px;font-weight:300;letter-spacing:-.01em;line-height:1.15;font-variant-numeric:tabular-nums;white-space:nowrap">${brlH(s[12], 46, 22)}</div>
      <div style="margin-top:12px">${modo === 'barras' ? grafBarras(s, 420, 74) : grafLinha(s, 420, 74)}</div>
      <div style="margin-top:14px;display:grid;grid-template-columns:repeat(3,1fr)">${[2, 1, 0].map(j => [c.hor[modo][k][j], j]).map(([h, j]) => `<div><div style="font-size:16px;font-weight:600;letter-spacing:.16em;color:var(--sky)">${[12, 24, 36][j]} MESES</div><div style="display:flex;align-items:center;gap:4px;margin-top:4px"><span style="color:var(--accent);display:flex">${ARW(h.s, 22)}</span><span style="font-size:25px;font-variant-numeric:tabular-nums;color:${h.r == null ? 'var(--sky)' : '#fff'}">${fpct(h.r)}</span></div></div>`).join('')}</div></div>`;
  };
  const nm3 = ks.some(k => c.hor[modo][k].some(h => Number.isNaN(h.r))) ? NM : '';
  const nota3 = modo === 'barras'
    ? `Cada barra é um trimestre, de ${ini} a ${d.periodo}; em destaque, o mesmo trimestre de cada ano. Variação do ${d.periodo} contra o mesmo trimestre de 36, 24 e 12 meses antes.`
    : `Receita, EBITDA e lucro somados em 12 meses; patrimônio, dívida e ativo no fim do trimestre. Variação contra 36, 24 e 12 meses antes (pontos em destaque).`;
  T.push(`<div class="frame">${head(d, 3, N)}<h3 style="margin-top:64px">36, 24 e 12 meses.</h3>
    <div style="margin-top:30px;display:grid;grid-template-columns:1fr 1fr;column-gap:48px">${ks.map(card).join('')}</div>
    <p class="small" style="margin-top:8px">${nota3 + nm3}</p>${foot(3, N)}</div>`);
  // 4 (e 5) por trimestre: barras dos 13 trimestres, com o valor em cima de cada barra
  const tri13 = d.trimestres.slice(-13);
  grupos.forEach(([tit, lista], gi) => {
    const linhas = lista.map(k => {
      const { svg, u } = grafBarrasValores(c.s13.barras[k], tri13, 888, 212, c.yoy13[k]);
      return `<div style="padding:20px 0 12px;border-top:1px solid var(--hair)"><div style="display:flex;justify-content:space-between;align-items:baseline"><span style="font-size:24px;font-weight:500">${LABEL[k]}</span><span style="font-size:16px;font-weight:600;letter-spacing:.16em;color:var(--sky)">R$ ${u.toUpperCase()} · ${fluxo3.includes(k) ? 'NO TRIMESTRE' : 'FIM DO TRIMESTRE'}</span></div><div style="margin-top:6px">${svg}</div></div>`;
    }).join('');
    const so = lista.every(k => fluxo3.includes(k)) ? 'f' : lista.some(k => fluxo3.includes(k)) ? 'm' : 'e';
    const nota = (so === 'f' ? `Valor de cada trimestre, de ${tri13[0]} a ${d.periodo}.` : so === 'e' ? `Posição no fim de cada trimestre, de ${tri13[0]} a ${d.periodo}.`
      : `Lucro de cada trimestre; patrimônio e ativo no fim de cada trimestre, de ${tri13[0]} a ${d.periodo}.`) + ' Em destaque, o mesmo trimestre de cada ano; dentro da barra, a variação contra o mesmo trimestre do ano anterior.';
    const nmB = lista.some(k => c.yoy13[k].some((r, i) => (12 - i) % 4 === 0 && Number.isNaN(r))) ? NM : '';
    T.push(`<div class="frame">${head(d, 4 + gi, N)}<h3 style="margin-top:56px">${tit}</h3><div style="margin-top:18px;border-bottom:1px solid var(--hair)">${linhas}</div><p class="small" style="margin-top:16px">${nota}${nmB}</p>${foot(4 + gi, N)}</div>`);
  });
  // 4 múltiplos de hoje (os mesmos do comparador)
  const m = d.multiplos, mh = multHoje(d), nmx6 = [mh.pvp, mh.pl, mh.ev].some(Number.isNaN) ? NMX : '';
  T.push(`<img class="legs" src="assets/symbol.png" style="left:560px;top:380px;height:1000px;opacity:.05"><div class="frame">${head(d, nM, N)}
    <div style="margin-top:auto"><div class="tag" style="color:var(--sky);font-size:22px">Preço sobre valor patrimonial</div><div class="big" style="margin-top:20px">${fx(mh.pvp)}</div></div>
    <div style="margin-top:70px;display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--hair)">
      <div style="padding:34px 0"><div class="tag" style="color:var(--sky);font-size:20px">P/L</div><div style="font-size:64px;font-weight:300;margin-top:10px">${fx(mh.pl)}</div></div>
      <div style="padding:34px 0 34px 40px;border-left:1px solid var(--hair)"><div class="tag" style="color:var(--sky);font-size:20px">EV/EBITDA</div><div style="font-size:64px;font-weight:300;margin-top:10px">${d.financeira ? 'n/a' : fx(mh.ev)}</div></div></div>
    ${src((d.fontes.multiplos.includes(fdate(m.data_cotacao)) ? '' : `Cotação de fechamento de ${fdate(m.data_cotacao)}. `) + `Fonte: ${d.fontes.multiplos}.` + nmx6)}<div style="height:40px"></div>${foot(nM, N)}</div>`);
  // preço e múltiplos: mês a mês nos 36 meses; em destaque, 12, 24 e 36 meses antes (preço sem proventos, ajustado por desdobramentos)
  if (H) {
    const n = H.datas.length - 1, anc = [n - 12, n - 24, n - 36];
    const hp = H.pvp.map(corta), he = (H.ev_ebitda || []).map(corta), nmx7 = [...hp, ...he].some(Number.isNaN);
    if (hp.length) hp[n] = mh.pvp; if (he.length) he[n] = mh.ev;
    const linhas = [['Preço da ação', `${d.ticker}, sem proventos`, H.preco, 'R$', ''], ['P/VP', 'preço sobre valor patrimonial', hp, '', 'x'],
      ...(d.financeira ? [] : [['EV/EBITDA', 'valor da firma sobre EBITDA', he, '', 'x']])];
    const val = (v, big, small, pre, suf) => v == null || Number.isNaN(v) ? `<span style="font-size:${big}px;color:var(--sky)">${v == null ? 'n/d' : 'n.m.'}</span>`
      : `${pre ? `<span style="font-size:${small}px;color:var(--sky);font-weight:400;margin-right:.3em">${pre}</span>` : ''}<span style="font-size:${big}px">${nf(v, 2)}</span>${suf ? `<span style="font-size:${small}px;color:var(--mist);font-weight:500;margin-left:.08em">${suf}</span>` : ''}`;
    let nm5 = false;
    const linha = ([lab, hint, v, pre, suf]) => `<div style="display:grid;grid-template-columns:270px 1fr;column-gap:30px;align-items:center;padding:26px 0 24px;border-top:1px solid var(--hair)">
      <div><div style="font-size:24px;font-weight:500">${lab}</div><div style="font-size:18px;color:var(--sky);margin-top:4px">${hint}</div><div style="margin-top:18px;font-weight:300;line-height:1;white-space:nowrap">${val(v[n], 58, 24, pre, suf)}</div></div>
      <div>${grafLinha(v, 588, 92, anc.filter(a => a >= 0), y => nf(y, 2) + suf)}
        <div style="margin-top:10px;display:grid;grid-template-columns:repeat(3,1fr)">${[2, 1, 0].map(j => {
          const a = anc[j], r = a >= 0 ? pct(v[n], v[a]) : null; if (Number.isNaN(r)) nm5 = true;
          return `<div><div style="font-size:16px;font-weight:600;letter-spacing:.16em;color:var(--sky)">${12 * (j + 1)} MESES</div><div style="display:flex;align-items:center;gap:3px;margin-top:4px"><span style="color:var(--accent);display:flex">${ARW(a >= 0 ? sen(v[n], v[a], r) : null, 18)}</span><span style="font-size:24px;font-variant-numeric:tabular-nums;color:${r == null ? 'var(--sky)' : '#fff'}">${fpct(r)}</span></div></div>`;
        }).join('')}</div></div></div>`;
    const corpo = linhas.map(linha).join('');
    T.push(`<div class="frame">${head(d, nH, N)}<h3 style="margin-top:64px;max-width:860px">Preço e múltiplos em 36, 24 e 12 meses.</h3>
    <div style="margin-top:34px;border-bottom:1px solid var(--hair)">${corpo}</div>
    ${src(`Fechamento mês a mês na B3 até ${fdate(H.datas[n])}, sem proventos e ajustado por desdobramentos; nos pontos, o valor de 36, 24 e 12 meses antes e o de hoje; embaixo, a variação de cada um até hoje. Múltiplos passados com o último balanço divulgado em cada data e o número de ações atual.` + (nmx7 || [mh.pvp, mh.ev].some(Number.isNaN) ? NMX : nm5 ? NM : ''))}${foot(nH, N)}</div>`);
  }
  // 6 fontes e aviso
  T.push(`<div class="frame">${head(d, N, N)}<div style="margin:auto 0"><h3 style="max-width:860px">Os números, <em>sem opinião.</em></h3>
    <div style="margin-top:56px;display:flex;flex-direction:column;gap:22px;font-size:26px;line-height:1.5;color:var(--mist)">
      <div><span class="tag" style="color:var(--sky);font-size:20px;display:block;margin-bottom:6px">Demonstrações</span>${d.fontes.demonstracoes}</div>
      <div><span class="tag" style="color:var(--sky);font-size:20px;display:block;margin-bottom:6px">Múltiplos</span>${d.fontes.multiplos}</div>${d.financeira ? '' : `
      <div><span class="tag" style="color:var(--sky);font-size:20px;display:block;margin-bottom:6px">EBITDA</span>${EBITDA_DEF}</div>`}</div></div>
    <div style="display:flex;flex-direction:column;gap:30px">${invest.replace('height:70px', 'height:92px')}<p class="legal">${LEGAL_TELA}</p></div></div>`);
  return T.map(t => `<section class="slide"><div class="vignette"></div>${band(d)}${t}<div class="grain"></div></section>`);
}

// ---------------------------------------------------------------- legenda (fria, sem adjetivos)
export function legenda(d) {
  const c = calcula(d), H = d.historico, base = d.trimestres[d.trimestres.length - 5], L = [], mh = multHoje(d);
  let nmx = false;
  if (d.capa.tipo === 'noticia') L.push(`${d.ticker} | ${d.noticia.titulo}`, '', `Fonte: ${d.noticia.fonte}, ${fdate(d.noticia.data)}.`, '');
  L.push(`${d.ticker} | Resultado do ${d.periodo}`, '');
  const modo = d.grafico === 'barras' ? 'barras' : 'linha';
  for (const k of ['receita', 'ebitda', 'lucro']) if (c.tri[k]) L.push(`${LABEL[k]}: ${brl(c.tri[k].v)} (${fpct(c.tri[k].yoy)} vs ${base})`);
  if (c.capa && d.capa.tipo !== 'noticia') { const m = c.capa, fim = m.estoque ? 'no fim do ' : 'no ';
    L.push(`Maior variação contra o ${base}: ${m.k === 'ebitda' ? 'EBITDA' : LABEL[m.k].toLowerCase()}, ${fpct(m.r)} (${brl(m.a)} ${fim}${d.periodo}, contra ${brl(m.b)} ${fim}${base}).`); }
  L.push('', `Variação em 12, 24 e 36 meses${modo === 'linha' ? ' (receita, EBITDA e lucro somados em 12 meses)' : ' (trimestre contra o mesmo trimestre)'}:`);
  for (const k of Object.keys(c.hor[modo])) L.push(`${LABEL[k]}: ${c.hor[modo][k].map(h => fpct(h.r)).join(' | ')}`);
  if (H) {
    L.push('', 'Preço e múltiplos, hoje | 12 | 24 | 36 meses antes:');
    const n = H.datas.length - 1, ix = [n, n - 12, n - 24, n - 36], pega = (a) => ix.map(i => (i >= 0 ? a[i] : null));
    L.push(`Preço ${d.ticker} (sem proventos): ${pega(H.preco).map(v => (v == null ? 'n/d' : 'R$ ' + nf(v, 2))).join(' | ')}`);
    const hp = pega(H.pvp).map(corta), he = pega(H.ev_ebitda || []).map(corta);
    hp[0] = mh.pvp; he[0] = mh.ev;
    L.push(`P/VP: ${hp.map(fx).join(' | ')}`);
    if (!d.financeira) L.push(`EV/EBITDA: ${he.map(fx).join(' | ')}`);
    if ([...hp, ...(d.financeira ? [] : he)].some(Number.isNaN)) nmx = true;
  }
  L.push('', `P/VP de ${fx(mh.pvp)}${mh.pl != null ? `, P/L de ${fx(mh.pl)}` : ''} na cotação de ${fdate(d.multiplos.data_cotacao)}.`);
  const notas = [];
  if ([...Object.values(c.tri).map(x => x.yoy), ...Object.values(c.hor[modo]).flat().map(h => h.r)].some(Number.isNaN)) notas.push(NM.trim());
  if (nmx || [mh.pvp, mh.pl, mh.ev].some(Number.isNaN)) notas.push(NMX.trim());
  if (notas.length) L.push('', ...notas);
  L.push('', `Fontes: ${d.fontes.demonstracoes}; múltiplos: ${d.fontes.multiplos}.${d.financeira ? '' : ` EBITDA: ${EBITDA_DEF.charAt(0).toLowerCase() + EBITDA_DEF.slice(1)}.`}`, '', LEGAL, '', `#${d.ticker} #resultados #${d.periodo} #b3`);
  return L.join('\n');
}

// ---------------------------------------------------------------- render
if (process.argv[1] && process.argv[1].endsWith('empresa.mjs')) {
  const d = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  if (process.env.GRAFICO) d.grafico = process.env.GRAFICO;
  // logo oficial da biblioteca (logos/<4 letras do ticker>.svg ou .png, versão clara); sem arquivo, a capa mostra o espaço
  if (!d.logo) for (const ext of ['svg', 'png']) { const l = `logos/${d.ticker.slice(0, 4)}.${ext}`; if (fs.existsSync(path.join(STUDIO, l))) { d.logo = l; break; } }
  if (!d.logo) console.log(`aviso: sem logo para ${d.ticker} (falta logos/${d.ticker.slice(0, 4)}.svg ou .png, ou está marcado como desatualizado no indice.csv)`);
  // tamanho do logo pela área (largo fica mais baixo, quadrado mais alto), sem ampliar mais que 1,8x um png pequeno
  try {
    const t = JSON.parse(fs.readFileSync(path.join(STUDIO, 'logos', 'tamanhos.json'), 'utf8'))[d.ticker.slice(0, 4)];
    if (d.logo && d.logo.endsWith('.png') && t) {
      const asp = t[0] / t[1]; let h = Math.sqrt(38000 / asp);
      h = Math.min(h, 160, 540 / asp, t[1] * 1.8); d.logoH = Math.round(Math.max(h, 48));
    }
  } catch {}
  const outDir = path.resolve(process.argv[3] || 'saida'); fs.mkdirSync(outDir, { recursive: true });
  const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><link rel="stylesheet" href="styles.css"></head><body>${telas(d).join('')}</body></html>`;
  const f = path.join(STUDIO, `_empresa-${process.pid}.html`); fs.writeFileSync(f, html);   // um por processo: renderizações em paralelo não se misturam
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1400 } });
  await p.goto('file://' + f); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(150);
  const els = await p.$$('section.slide');
  for (let k = 0; k < els.length; k++) await els[k].screenshot({ path: path.join(outDir, String(k + 1).padStart(2, '0') + '.png') });
  fs.writeFileSync(path.join(outDir, 'legenda.txt'), legenda(d));
  await b.close(); fs.rmSync(f, { force: true }); console.log('ok', els.length, outDir);
}
