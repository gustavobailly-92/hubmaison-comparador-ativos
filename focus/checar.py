#!/usr/bin/env python3
"""Mede os slides renderizados: tamanho de letra, contraste, colisões, saída da margem e travessões.

Uso: python3 checar.py saida/AAAA-MM-DD [--chrome /caminho/do/chrome]
Lê preview.html da pasta (gerado pelo render.py) e os PNGs. Sai com código 1 se algo falhar.
"""
import argparse, os, sys
from statistics import median

MIN_CONTEUDO, MIN_NOTA, MIN_CONTRASTE, MARGEM = 22, 18, 4.5, 60
CLASSES_NOTA = ("rodape", "ident", "graf-rot", "topo", "data-div")

JS = r"""
() => [...document.querySelectorAll('section.slide')].map((sl, n) => {
  const base = sl.getBoundingClientRect();
  const out = [];
  const walker = document.createTreeWalker(sl, NodeFilter.SHOW_TEXT);
  let t, no = 0;
  while ((t = walker.nextNode())) {
    const txt = t.textContent.trim();
    if (!txt) continue;
    const el = t.parentElement;
    const r = document.createRange(); r.selectNodeContents(t);
    const rects = [...r.getClientRects()].filter(q => q.width > 0);
    if (!rects.length) continue;
    const cs = getComputedStyle(el);
    let nota = false;
    for (let p = el; p && p !== sl; p = p.parentElement)
      if ([...p.classList].some(c => %s.includes(c))) nota = true;
    no++;
    for (const b of rects) out.push({no, txt: txt.slice(0, 40), x: b.left - base.left, y: b.top - base.top, w: b.width, h: b.height,
      fs: parseFloat(el.tagName === 'text' ? (el.getAttribute('font-size') || cs.fontSize) : cs.fontSize)
          * (el.ownerSVGElement ? el.ownerSVGElement.getBoundingClientRect().width / el.ownerSVGElement.viewBox.baseVal.width || 1 : 1),
      cor: el.tagName === 'text' ? el.getAttribute('fill') : cs.color, nota});
    continue;
  }
  return out;
})
""" % repr(list(CLASSES_NOTA)).replace("'", '"')


def rgb(c):
    c = c.strip()
    if c.startswith("#"):
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    v = c[c.index("(") + 1:c.index(")")].split(",")
    return tuple(int(float(x)) for x in v[:3])


def lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in c)
    return .2126 * r + .7152 * g + .0722 * b


def contraste(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + .05) / (lb + .05)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH"))
    args = ap.parse_args()
    from PIL import Image
    from playwright.sync_api import sync_playwright

    falhas = []
    html = open(os.path.join(args.pasta, "preview.html")).read()
    for ch in ("—", "–"):
        if ch in html.split("<script>")[0] or ch in html:
            falhas.append(f"travessão '{ch}' no HTML")
    leg = os.path.join(args.pasta, "legenda.txt")
    if os.path.exists(leg) and any(ch in open(leg).read() for ch in ("—", "–")):
        falhas.append("travessão na legenda")

    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": args.chrome} if args.chrome else {}))
        pg = b.new_page(viewport={"width": 1200, "height": 1500})
        pg.goto("file://" + os.path.abspath(os.path.join(args.pasta, "preview.html")))
        pg.evaluate("document.fonts.ready")
        slides = pg.evaluate(JS)
        b.close()

    for n, itens in enumerate(slides, 1):
        img = Image.open(os.path.join(args.pasta, f"{n:02d}-slide.png")).convert("RGB")
        for it in itens:
            rot = f"slide {n} '{it['txt']}'"
            minimo = MIN_NOTA if it["nota"] else MIN_CONTEUDO
            if it["fs"] < minimo - .5:
                falhas.append(f"{rot}: letra {it['fs']:.0f}px < {minimo}")
            x0, y0 = int(it["x"]), int(it["y"])
            x1, y1 = int(it["x"] + it["w"]), int(it["y"] + it["h"])
            if x0 < MARGEM - 2 or y0 < MARGEM - 2 or x1 > 1080 - MARGEM + 2 or y1 > 1350 - MARGEM + 2:
                falhas.append(f"{rot}: fora da margem ({x0},{y0},{x1},{y1})")
            # fundo: mediana da moldura de 6 px em volta da caixa
            px = []
            for xx in range(max(0, x0 - 6), min(1080, x1 + 6), 3):
                for yy in (max(0, y0 - 6), min(1349, y1 + 6)):
                    px.append(img.getpixel((xx, yy)))
            fundo = tuple(int(median(c[i] for c in px)) for i in range(3))
            cr = contraste(rgb(it["cor"]), fundo)
            if cr < MIN_CONTRASTE:
                falhas.append(f"{rot}: contraste {cr:.2f} ({it['cor']} sobre {fundo})")
        # colisão entre caixas de texto
        # números de vitrine (letra acima de 100 px) têm caixa de texto bem maior que o desenho: ficam
        # de fora desta conta e são conferidos no olho; 3 px de folga para trechos na mesma linha
        normais = [t for t in itens if t["fs"] <= 100]
        for i, a in enumerate(normais):
            for c in normais[i + 1:]:
                if a["no"] == c["no"]:
                    continue  # linhas do mesmo parágrafo
                if (a["x"] < c["x"] + c["w"] - 3 and c["x"] < a["x"] + a["w"] - 3 and
                        a["y"] < c["y"] + c["h"] - 3 and c["y"] < a["y"] + a["h"] - 3):
                    falhas.append(f"slide {n}: '{a['txt']}' encosta em '{c['txt']}'")

    total = sum(len(s) for s in slides)
    if falhas:
        print(f"{len(falhas)} falha(s) em {total} textos:")
        for f in falhas:
            print(" -", f)
        sys.exit(1)
    print(f"ok: {total} textos em {len(slides)} slides; letra, contraste, margem, colisão e travessão")


if __name__ == "__main__":
    main()
