"""Проверка технологической схемы (SVG в HTML-документе) тем же движком, что и чертежи."""
import re, sys, os
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(__file__))
import check
from draw import Sheet

check.TOL = 2.0
SRC = os.path.join(os.path.dirname(__file__), '..', 'tefkot-770-reaktor-50l.html')
html = open(SRC, encoding='utf-8').read()
svg = re.sub(r'<!--.*?-->', '', re.search(r'<svg viewBox.*?</svg>', html, re.S).group(0), flags=re.S)
root = ET.fromstring(svg)
sh = Sheet('Технологическая схема', 1400, 900)
sh.vessels = []
LW = {'amine': 2.6, 'aq': 2.2, 'argon': 2.2, 'vent': 2.6, 'liq': 2.8, 'cool': 2.2, 'vac': 2.2}
SYM = {'bv': ('valve', 'h', 9), 'bvv': ('valve', 'v', 9), 'nrv': ('check', 'h', 8), 'nrvd': ('check', 'v', 8), 'nrvu': ('check', 'v', 8), 'nrvl': ('check', 'h', 8)}


def parse_path(d):
    toks = re.findall(r'[MLQZ]|-?\d+(?:\.\d+)?', d)
    subs, cur, cmd, closed, i = [], [], None, False, 0
    while i < len(toks):
        t = toks[i]
        if t in 'MLQZ':
            cmd = t; i += 1
            if t == 'Z':
                closed = True
            elif t == 'M' and cur:
                subs.append(cur); cur = []
            continue
        if cmd in 'ML':
            cur.append((float(toks[i]), float(toks[i + 1]))); i += 2
        else:
            cx, cy, ex, ey = map(float, toks[i:i + 4]); i += 4
            sx, sy = cur[-1]
            for k in range(1, 9):
                u = k / 8
                cur.append(((1 - u) ** 2 * sx + 2 * (1 - u) * u * cx + u * u * ex, (1 - u) ** 2 * sy + 2 * (1 - u) * u * cy + u * u * ey))
    if cur:
        subs.append(cur)
    return subs, closed


for el in root:
    tag = el.tag.split('}')[-1]
    c = el.get('class') or ''
    if tag == 'defs':
        continue
    if tag == 'rect':
        if c == 'zone':
            continue
        x, y, w, h = (float(el.get(k)) for k in ('x', 'y', 'width', 'height'))
        sh.rect(x, y, w, h, lw=1.6, fill='#fff' if c in ('eq', 'eqf') else None)
        if c in ('eq', 'eqf') and w > 30 and h > 30:
            sh.vessels.append((x, y, x + w, y + h))
    elif tag == 'circle':
        sh.circle(float(el.get('cx')), float(el.get('cy')), float(el.get('r')), lw=1.6)
    elif tag == 'path':
        subs, closed = parse_path(el.get('d'))
        lw = LW.get(c, 1.6 if c in ('eq', 'eqf', 'v', 'vno') else 0.3)
        if c in ('thin', 'liqlvl', 'zone') or 'stroke-width="2"' in ET.tostring(el, encoding='unicode'):
            lw = 0.3
        for sp in subs:
            sh.poly(sp, lw=lw, closed=closed, fill='#fff' if (closed and c in ('eq', 'eqf')) else None)
            if closed and c in ('eq', 'eqf'):
                xs = [p[0] for p in sp]; ys = [p[1] for p in sp]
                sh.vessels.append((min(xs), min(ys), max(xs), max(ys)))
            if el.get('marker-end'):
                ex, ey = sp[-1]
                sh.poly([(ex - 3, ey - 3), (ex + 3, ey - 3), (ex + 3, ey + 3), (ex - 3, ey + 3)], lw=0.3, closed=True)
    elif tag == 'use':
        name = el.get('href').lstrip('#'); x, y = float(el.get('x')), float(el.get('y'))
        kind, ax, half = SYM[name]
        i0 = len(sh.items)
        sh.rect(*((x - half, y - 3, 2 * half, 6) if ax == 'h' else (x - 3, y - half, 6, 2 * half)), lw=0.3)   # линия подходит к краю символа
        sh._sym(kind, x, y, ax, half, i0)
    elif tag == 'text':
        sh.text(float(el.get('x')), float(el.get('y')), ''.join(el.itertext()), 12 if c == 'lbl' else 10.5, {'end': 'end', 'middle': 'middle'}.get(el.get('text-anchor'), 'start'))

pr = check.check_sheet(sh)
texts = [it for it in sh.items if it[0] == 'text']
def near_label(p):
    m = re.search(r'\(([\d.]+),([\d.]+)\)', p)
    x, y = float(m.group(1)), float(m.group(2))
    for _, tx, ty, st, size, anchor, *_ in texts:
        w = len(st) * size * 0.55
        x0 = {'start': tx, 'middle': tx - w / 2, 'end': tx - w}[anchor]
        if x0 - 12 < x < x0 + w + 12 and ty - size - 12 < y < ty + 12:
            return True
    return False
pr = [p for p in pr if not (p.startswith('висит конец') and near_label(p))]
print(len(pr))
for p in pr:
    print(' ', p)
