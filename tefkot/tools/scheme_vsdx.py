"""Технологическая схема из HTML-документа → редактируемый Visio (.vsdx) через движок draw.py."""
import re, os, sys, zipfile, tempfile, math
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(__file__))
from draw import Sheet, to_vsdx, to_svg

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(HERE, 'tefkot-770-reaktor-50l.html'), encoding='utf-8').read()
svg = re.sub(r'<!--.*?-->', '', re.search(r'<svg viewBox.*?</svg>', html, re.S).group(0), flags=re.S)
svg = svg.replace(' 🔒', '*').replace(' ⏚', '')
root = ET.fromstring(svg)

K, OX, OY = 0.29, 7.0, 22.0
def P(x, y): return (OX + x * K, OY + y * K)

C = {'fg': '#1d2226', 'muted': '#5d666d', 'paper': '#ffffff', 'note': '#eef3f5', 'rule': '#b9c0c3'}
LINE = {  # класс: (цвет, толщина px, штрих)
    'amine': ('#b4491b', 2.6, None), 'aq': ('#a07a12', 2.2, None), 'argon': ('#2d6fb3', 2.2, None),
    'vent': ('#7a4fa0', 2.6, None), 'liq': ('#2f6b3a', 2.8, None), 'cool': ('#0f8a8a', 2.2, 'dash'),
    'vac': ('#37474f', 2.8, 'dash'), 'thin': (C['muted'], 1.0, None), 'liqlvl': ('#2f6b3a', 1.2, 'dash'),
    'zone': (C['rule'], 1.2, 'dash'), 'eq': (C['fg'], 1.6, None), 'eqf': (C['fg'], 1.6, None),
}
FILL = {'eq': C['paper'], 'eqf': C['note']}
SYM = {'bv': [[(-9, -6), (9, 6), (9, -6), (-9, 6)]], 'bvv': [[(-6, -9), (6, 9), (-6, 9), (6, -9)]],
       'nrv': [[(-8, -6), (6, 0), (-8, 6)]], 'nrvd': [[(-6, -8), (0, 6), (6, -8)]], 'nrvu': [[(-6, 8), (0, -6), (6, 8)]], 'nrvl': [[(8, -6), (-6, 0), (8, 6)]]}
BAR = {'nrvl': [(-8, -7), (-8, 7)], 'nrv': [(8, -7), (8, 7)], 'nrvd': [(-7, 8), (7, 8)], 'nrvu': [(-7, -8), (7, -8)]}

sh = Sheet('Технологическая схема', 420.0, 297.0)
sh.keep_order = True      # порядок слоёв как в исходной схеме (внутренности аппаратов поверх заливки)
sh.rect(0.2, 0.2, 419.6, 296.6, lw=0.1, color='#bbbbbb', nc=True)
sh.text(8, 10, 'ТЕФКОТ 770 — синтез на стальном реакторе 50 л. Технологическая схема (принципиальная)', 4.2, bold=True, color=C['fg'])
sh.text(8, 16, 'АО «ИНУМиТ» · позиции соответствуют спецификации и монтажным чертежам ИНУМ.770-50.00', 2.6, color=C['muted'])


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
            for k in range(1, 11):
                u = k / 10
                cur.append(((1 - u) ** 2 * sx + 2 * (1 - u) * u * cx + u * u * ex, (1 - u) ** 2 * sy + 2 * (1 - u) * u * cy + u * u * ey))
    if cur:
        subs.append(cur)
    return subs, closed


for el in root:
    tag = el.tag.split('}')[-1]
    c = el.get('class') or ''
    if tag == 'defs':
        continue
    st = el.get('style') or ''
    if tag == 'rect':
        x, y, w, h = (float(el.get(k)) for k in ('x', 'y', 'width', 'height'))
        col, lw, dash = LINE.get(c, (C['fg'], 1.6, None))
        sh.poly([P(x, y), P(x + w, y), P(x + w, y + h), P(x, y + h)], lw=lw * K, color=col, dash=dash, closed=True, fill=FILL.get(c))
    elif tag == 'circle':
        col, lw, dash = LINE.get(c, (C['fg'], 1.6, None))
        cx, cy = P(float(el.get('cx')), float(el.get('cy')))
        sh.circle(cx, cy, float(el.get('r')) * K, lw=lw * K, color=col, fill=FILL.get(c))
    elif tag == 'path':
        subs, closed = parse_path(el.get('d'))
        if 'stroke:var(--fg)' in st:
            col, lw, dash = C['fg'], 2.0, None
        else:
            col, lw, dash = LINE.get(c, (C['fg'], 1.6, None))
        if 'dasharray:none' in st:
            dash, lw = None, 1.6
        for sp in subs:
            pts = [P(*p) for p in sp]
            sh.poly(pts, lw=lw * K, color=col, dash=dash, closed=closed, fill=FILL.get(c) if closed else None)
            if el.get('marker-end') and len(pts) > 1:
                (x1, y1), (x2, y2) = pts[-2], pts[-1]
                sh.arrow(x2, y2, math.atan2(y2 - y1, x2 - x1), L=2.4, W=1.0, color=C['fg'])
    elif tag == 'use':
        name = el.get('href').lstrip('#'); ux, uy = float(el.get('x')), float(el.get('y'))
        i0 = len(sh.items)
        for poly in SYM[name]:
            sh.poly([P(ux + a, uy + b) for a, b in poly], lw=1.4 * K, color=C['fg'], closed=True,
                    fill=C['fg'] if name.startswith('nrv') else C['paper'])
        if name in BAR:
            sh.poly([P(ux + a, uy + b) for a, b in BAR[name]], lw=2.0 * K, color=C['fg'])
        ax = 'v' if name in ('bvv', 'nrvd', 'nrvu') else 'h'
        sh._sym('valve', *P(ux, uy), ax, (9 if name.startswith('bv') else 8) * K, i0)
    elif tag == 'text':
        x, y = P(float(el.get('x')), float(el.get('y')))
        s = ''.join(el.itertext())
        size = (12 if c == 'lbl' else 11 if c == 'zt' else 10.5) * K
        anchor = {'end': 'end', 'middle': 'middle'}.get(el.get('text-anchor'), 'start')
        red = '?' in s
        sh.text(x, y, s, size, anchor, bold=(c == 'lbl'), color='#c62828' if red else (C['fg'] if c == 'lbl' or re.match(r'^[A-Z]{1,3}-?\d', s) else C['muted']))

# легенда
LEG = [('amine', 'газ CH₃NH₂'), ('aq', 'водн. метиламин'), ('argon', 'аргон'), ('vent', 'отдувка / сброс'),
       ('liq', 'жидкость, продукт'), ('cool', 'теплоноситель'), ('vac', 'вакуум')]
lx, ly = 8, 286
sh.text(lx, ly - 4, 'Условные обозначения линий:', 2.6, bold=True, color=C['fg'])
for i, (cl, lab) in enumerate(LEG):
    x = lx + i * 44
    col, lw, dash = LINE[cl]
    sh.poly([(x, ly), (x + 10, ly)], lw=lw * K, color=col, dash=dash, nc=True)
    sh.text(x + 12, ly + 0.9, lab, 2.4, color=C['fg'])
sh.text(330, ly + 0.9, 'SV-3* опломбирован «открыт»; НЗ — нормально закрыт', 2.2, color=C['fg'])

out = os.path.join(HERE, 'tefkot-770-skhema.vsdx')
tpl = tempfile.mkdtemp()
with zipfile.ZipFile(os.path.join(HERE, 'tools', 'visio-template.vsdx')) as z:
    z.extractall(tpl)
from legend import scheme_legend
to_vsdx([sh, scheme_legend()], tpl, out)
open(os.path.join(HERE, 'chertezh', 'skhema.svg'), 'w', encoding='utf-8').write(to_svg(sh))
print('ok', out)
