"""Конвертер схемы Тефкот 770 (SVG из HTML-документа) в редактируемый .vsdx."""
import re, sys, os, shutil, zipfile, math
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

SRC, TPL, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

html = open(SRC, encoding='utf-8').read()
svg = re.search(r'<svg viewBox.*?</svg>', html, re.S).group(0)
svg = svg.replace(' 🔒', '*').replace(' ⏚', '')
svg = re.sub(r'<!--.*?-->', '', svg, flags=re.S)
root = ET.fromstring(svg)

PW, PH = 16.5354, 11.6929            # A3 альбом, дюймы
S = 0.01150                           # дюйм на px SVG
X0 = (PW - 1400 * S) / 2
YTOP = PH - 1.00

def X(x): return X0 + x * S
def Y(y): return YTOP - y * S

COL = {'fg': '#1d2226', 'muted': '#5d666d', 'rule': '#b9c0c3', 'paper': '#ffffff', 'note': '#eef3f5',
       'amine': '#b4491b', 'aq': '#a07a12', 'argon': '#2d6fb3', 'vent': '#7a4fa0', 'liq': '#2f6b3a',
       'cool': '#0f8a8a', 'vac': '#6b6f73'}
# класс -> (цвет линии, толщина px, узор, заливка или None)
STY = {
    'eq': (COL['fg'], 1.6, 1, COL['paper']), 'eqf': (COL['fg'], 1.6, 1, COL['note']),
    'thin': (COL['muted'], 1.0, 1, None), 'zone': (COL['rule'], 1.2, 2, None),
    'liqlvl': (COL['liq'], 1.2, 2, None),
    'amine': (COL['amine'], 2.6, 1, None), 'aq': (COL['aq'], 2.2, 1, None), 'argon': (COL['argon'], 2.2, 1, None),
    'vent': (COL['vent'], 2.6, 1, None), 'liq': (COL['liq'], 2.8, 1, None),
    'cool': (COL['cool'], 2.2, 2, None), 'vac': (COL['vac'], 2.2, 3, None),
    'v': (COL['fg'], 1.4, 1, COL['paper']), 'vno': (COL['fg'], 1.4, 1, COL['fg']),
    'plain': (COL['fg'], 2.0, 1, None),
}
SYM = {  # символы <use>
    'bv':   [('v',   [[(-9,-6),(9,6),(9,-6),(-9,6)]], True)],
    'bvv':  [('v',   [[(-6,-9),(6,9),(-6,9),(6,-9)]], True)],
    'nrv':  [('vno', [[(-8,-6),(6,0),(-8,6)]], True), ('plain', [[(8,-7),(8,7)]], False)],
    'nrvd': [('vno', [[(-6,-8),(0,6),(6,-8)]], True), ('plain', [[(-7,8),(7,8)]], False)],
    'nrvu': [('vno', [[(-6,8),(0,-6),(6,8)]], True), ('plain', [[(-7,-8),(7,-8)]], False)],
}
SYMNAME = {'bv': 'Кран шаровой', 'bvv': 'Кран шаровой', 'nrv': 'Клапан обратный',
           'nrvd': 'Клапан обратный', 'nrvu': 'Клапан обратный'}

shapes, sid = [], [0]
def nid():
    sid[0] += 1; return sid[0]

def fmt(v): return f'{v:.5f}'

def geom_shape(subpaths, cls, closed, name=None, rounding=0.0, arrow=False, style_over=None):
    """subpaths: списки точек в px SVG."""
    lc, lw, pat, fill = STY[cls]
    if style_over: lc, lw, pat, fill = style_over
    pts = [(X(x), Y(y)) for sp in subpaths for x, y in sp]
    minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
    miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
    w, h = max(maxx - minx, 0.001), max(maxy - miny, 0.001)
    i = nid()
    cells = [f"<Cell N='PinX' V='{fmt(minx+w/2)}'/>", f"<Cell N='PinY' V='{fmt(miny+h/2)}'/>",
             f"<Cell N='Width' V='{fmt(w)}'/>", f"<Cell N='Height' V='{fmt(h)}'/>",
             f"<Cell N='LocPinX' V='{fmt(w/2)}' F='Width*0.5'/>", f"<Cell N='LocPinY' V='{fmt(h/2)}' F='Height*0.5'/>",
             f"<Cell N='LineColor' V='{lc}'/>", f"<Cell N='LineWeight' V='{fmt(lw*S)}' U='PT'/>",
             f"<Cell N='LinePattern' V='{pat}'/>"]
    if fill:
        cells += [f"<Cell N='FillForegnd' V='{fill}'/>", "<Cell N='FillPattern' V='1'/>"]
    if rounding:
        cells.append(f"<Cell N='Rounding' V='{fmt(rounding*S)}'/>")
    if arrow:
        cells += ["<Cell N='EndArrow' V='13'/>", "<Cell N='EndArrowSize' V='1'/>"]
    secs = []
    for gi, sp in enumerate(subpaths):
        nofill = 0 if (closed and fill) else 1
        rows = [f"<Cell N='NoFill' V='{nofill}'/><Cell N='NoLine' V='0'/><Cell N='NoShow' V='0'/><Cell N='NoSnap' V='0'/>"]
        seq = list(sp) + ([sp[0]] if closed else [])
        for k, (x, y) in enumerate(seq):
            fx, fy = (X(x) - minx) / w, (Y(y) - miny) / h
            t = 'RelMoveTo' if k == 0 else 'RelLineTo'
            rows.append(f"<Row T='{t}' IX='{k+1}'><Cell N='X' V='{fmt(fx)}'/><Cell N='Y' V='{fmt(fy)}'/></Row>")
        secs.append(f"<Section N='Geometry' IX='{gi}'>{''.join(rows)}</Section>")
    nm = f" NameU='{escape(name)}' Name='{escape(name)}'" if name else ''
    shapes.append(f"<Shape ID='{i}'{nm} Type='Shape' LineStyle='3' FillStyle='3' TextStyle='3'>{''.join(cells)}{''.join(secs)}</Shape>")

def ellipse_shape(cx, cy, r, cls):
    lc, lw, pat, fill = STY[cls]
    i = nid(); d = 2 * r * S
    fillc = f"<Cell N='FillForegnd' V='{fill}'/><Cell N='FillPattern' V='1'/>" if fill else ''
    nofill = 0 if fill else 1
    shapes.append(
        f"<Shape ID='{i}' Type='Shape' LineStyle='3' FillStyle='3' TextStyle='3'>"
        f"<Cell N='PinX' V='{fmt(X(cx))}'/><Cell N='PinY' V='{fmt(Y(cy))}'/><Cell N='Width' V='{fmt(d)}'/><Cell N='Height' V='{fmt(d)}'/>"
        f"<Cell N='LocPinX' V='{fmt(d/2)}' F='Width*0.5'/><Cell N='LocPinY' V='{fmt(d/2)}' F='Height*0.5'/>"
        f"<Cell N='LineColor' V='{lc}'/><Cell N='LineWeight' V='{fmt(lw*S)}' U='PT'/><Cell N='LinePattern' V='{pat}'/>{fillc}"
        f"<Section N='Geometry' IX='0'><Cell N='NoFill' V='{nofill}'/><Cell N='NoLine' V='0'/><Cell N='NoShow' V='0'/><Cell N='NoSnap' V='0'/>"
        f"<Row T='Ellipse' IX='1'><Cell N='X' V='{fmt(d/2)}' F='Width*0.5'/><Cell N='Y' V='{fmt(d/2)}' F='Height*0.5'/>"
        f"<Cell N='A' V='{fmt(d)}' F='Width*1'/><Cell N='B' V='{fmt(d/2)}' F='Height*0.5'/>"
        f"<Cell N='C' V='{fmt(d/2)}' F='Width*0.5'/><Cell N='D' V='{fmt(d)}' F='Height*1'/></Row></Section></Shape>")

TXT = {'lbl': (12, 1, COL['fg']), 'sm': (10.5, 0, COL['muted']), 'zt': (11, 0, COL['muted']),
       'title': (18, 1, COL['fg']), 'sub': (12, 0, COL['muted'])}
def text_shape(x, y, s, cls, color=None):
    fs, bold, col = TXT[cls]
    if color: col = color
    if cls == 'sm' and re.match(r'^[A-Z]{1,3}-?\d', s): col = COL['fg']
    size = fs * S                      # дюймы
    w = max(len(s), 1) * size * 0.72 + 0.12
    h = size * 1.5
    cx, cy = X(x) + w / 2, Y(y - fs * 0.35)
    i = nid()
    shapes.append(
        f"<Shape ID='{i}' Type='Shape' LineStyle='3' FillStyle='3' TextStyle='3'>"
        f"<Cell N='PinX' V='{fmt(cx)}'/><Cell N='PinY' V='{fmt(cy)}'/><Cell N='Width' V='{fmt(w)}'/><Cell N='Height' V='{fmt(h)}'/>"
        f"<Cell N='LocPinX' V='{fmt(w/2)}' F='Width*0.5'/><Cell N='LocPinY' V='{fmt(h/2)}' F='Height*0.5'/>"
        f"<Cell N='LeftMargin' V='0'/><Cell N='RightMargin' V='0'/><Cell N='TopMargin' V='0'/><Cell N='BottomMargin' V='0'/>"
        f"<Cell N='VerticalAlign' V='1'/>"
        f"<Section N='Character'><Row IX='0'><Cell N='Color' V='{col}'/><Cell N='Size' V='{fmt(size)}' U='PT'/><Cell N='Style' V='{bold}'/></Row></Section>"
        f"<Section N='Paragraph'><Row IX='0'><Cell N='HorzAlign' V='0'/></Row></Section>"
        f"<Text>{escape(s)}</Text></Shape>")

def parse_path(d):
    toks = re.findall(r'[MLQZ]|-?\d+(?:\.\d+)?', d)
    subs, cur, i, cmd, closed = [], [], 0, None, False
    while i < len(toks):
        t = toks[i]
        if t in 'MLQZ':
            cmd = t; i += 1
            if t == 'Z': closed = True; continue
            if t == 'M' and cur: subs.append(cur); cur = []
            continue
        if cmd in ('M', 'L'):
            cur.append((float(toks[i]), float(toks[i+1]))); i += 2
        elif cmd == 'Q':
            cx_, cy_, ex, ey = map(float, toks[i:i+4]); i += 4
            sx, sy = cur[-1]
            for k in range(1, 9):
                t_ = k / 8
                cur.append(((1-t_)**2*sx + 2*(1-t_)*t_*cx_ + t_**2*ex, (1-t_)**2*sy + 2*(1-t_)*t_*cy_ + t_**2*ey))
    if cur: subs.append(cur)
    return subs, closed

def cls_of(el):
    c = el.get('class')
    if c: return c
    return 'plain'

# ---- заголовок, штамп, легенда
text_shape(10, -52, 'ТЕФКОТ 770 — синтез на стальном реакторе 50 л. Технологическая схема (принципиальная)', 'title')
text_shape(12, -28, 'АО «ИНУМиТ» · ред. 2 · 29.09.2026 · позиции соответствуют спецификации в документе проекта', 'sub')

for el in root:
    tag = el.tag.split('}')[-1]
    if tag == 'defs': continue
    c = cls_of(el)
    if tag == 'rect':
        x, y, w, h = (float(el.get(k)) for k in ('x', 'y', 'width', 'height'))
        geom_shape([[(x, y), (x+w, y), (x+w, y+h), (x, y+h)]], c, True, rounding=float(el.get('rx', 0)))
    elif tag == 'circle':
        ellipse_shape(float(el.get('cx')), float(el.get('cy')), float(el.get('r')), c)
    elif tag == 'path':
        subs, closed = parse_path(el.get('d'))
        over = None
        st = el.get('style') or ''
        if 'dasharray:none' in st: over = (COL['cool'], 1.6, 1, None)
        geom_shape(subs, c, closed, arrow=bool(el.get('marker-end')), style_over=over)
    elif tag == 'use':
        name = el.get('href').lstrip('#'); ux, uy = float(el.get('x')), float(el.get('y'))
        for pcls, subs, closed in SYM[name]:
            geom_shape([[(ux+px, uy+py) for px, py in sp] for sp in subs], pcls, closed, name=SYMNAME[name])
    elif tag == 'text':
        text_shape(float(el.get('x')), float(el.get('y')), ''.join(el.itertext()), c if c in TXT else 'sm')

# легенда линий (свободное поле слева внизу)
LEG = [('amine', 'газ CH₃NH₂'), ('aq', 'водн. метиламин'), ('argon', 'аргон'), ('vent', 'отдувка / сброс'),
       ('liq', 'жидкость, продукт'), ('cool', 'теплоноситель'), ('vac', 'вакуум')]
text_shape(22, 668, 'УСЛОВНЫЕ ОБОЗНАЧЕНИЯ ЛИНИЙ', 'zt'); text_shape(24, 838, '* SV-3 опломбирован открытым; НЗ — нормально закрыт', 'sm', COL['fg'])
for k, (cl, lab) in enumerate(LEG):
    yy = 690 + k * 20
    geom_shape([[(24, yy), (64, yy)]], cl, False)
    text_shape(72, yy + 4, lab, 'sm', COL['fg'])
geom_shape([[(12, 650), (350, 650), (350, 850), (12, 850)]], 'zone', True)

# ---- сборка пакета
work = OUT + '.d'
if os.path.exists(work): shutil.rmtree(work)
shutil.copytree(TPL, work)
page = ("<?xml version='1.0' encoding='utf-8' ?>\n<PageContents xmlns='http://schemas.microsoft.com/office/visio/2012/main' "
        "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships' xml:space='preserve'><Shapes>"
        + ''.join(shapes) + "</Shapes></PageContents>")
open(f'{work}/visio/pages/page1.xml', 'w', encoding='utf-8').write(page)

pp = open(f'{work}/visio/pages/pages.xml', encoding='utf-8').read()
pp = pp.replace("NameU='Page-1' Name='Page-1'", "NameU='Схема' Name='Схема'")
pp = re.sub(r"<Cell N='PageWidth' V='[^']*'/>", f"<Cell N='PageWidth' V='{PW}'/>", pp)
pp = re.sub(r"<Cell N='PageHeight' V='[^']*'/>", f"<Cell N='PageHeight' V='{PH}'/>", pp)
pp = re.sub(r"ViewCenterX='[^']*' ViewCenterY='[^']*'", f"ViewCenterX='{PW/2}' ViewCenterY='{PH/2}'", pp)
pp = pp.replace("<Cell N='PageScale' V='0.03937007874015748' U='MM'/>", "<Cell N='PageScale' V='0.03937007874015748' U='MM'/><Cell N='PrintPageOrientation' V='2'/>")
open(f'{work}/visio/pages/pages.xml', 'w', encoding='utf-8').write(pp)

ww = open(f'{work}/visio/windows.xml', encoding='utf-8').read()
ww = re.sub(r"ViewScale='1' ViewCenterX='[^']*' ViewCenterY='[^']*'", f"ViewScale='-1' ViewCenterX='{PW/2}' ViewCenterY='{PH/2}'", ww)
open(f'{work}/visio/windows.xml', 'w', encoding='utf-8').write(ww)

app = open(f'{work}/docProps/app.xml', encoding='utf-8').read().replace('<vt:lpstr>Page-1</vt:lpstr>', '<vt:lpstr>Схема</vt:lpstr>')
open(f'{work}/docProps/app.xml', 'w', encoding='utf-8').write(app)
rels = open(f'{work}/_rels/.rels', encoding='utf-8').read()
rels = re.sub(r'<Relationship Id="rId2"[^>]*thumbnail[^>]*/>', '', rels)
open(f'{work}/_rels/.rels', 'w', encoding='utf-8').write(rels)
os.remove(f'{work}/docProps/thumbnail.emf')

if os.path.exists(OUT): os.remove(OUT)
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    z.write(f'{work}/[Content_Types].xml', '[Content_Types].xml')
    for dp, _, fs in os.walk(work):
        for f in fs:
            full = os.path.join(dp, f); arc = os.path.relpath(full, work)
            if arc != '[Content_Types].xml': z.write(full, arc)
shutil.rmtree(work)
print('shapes:', len(shapes), '->', OUT)
