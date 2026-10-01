"""Мини-DSL для чертежей (мм, ось Y вниз) с выводом в SVG и VSDX."""
import math, re, os, shutil, zipfile
from xml.sax.saxutils import escape

RED = '#c62828'
INK = '#111111'
GREY = '#666666'
BLUE = '#1f5fa8'


class Sheet:
    def __init__(self, name, w=420.0, h=297.0):
        self.name, self.w, self.h = name, w, h
        self.items = []
        self.symbols = []      # для проверки стыков: (вид, x, y, ось, полудлина, i0, i1)
        self.nocheck = set()   # линии, не являющиеся трубопроводом (пол, мешалка, болты…)
        self.pending_sizes = []  # подписи размера у номеров клампов, ставятся в конце (place.py)

    def _sym(self, kind, x, y, axis, half, i0):
        self.symbols.append((kind, x, y, axis, half, i0, len(self.items)))

    # ---------- примитивы
    def poly(self, pts, lw=0.35, color=INK, dash=None, closed=False, fill=None, nc=False):
        if nc:
            self.nocheck.add(len(self.items))
        self.items.append(('poly', [tuple(p) for p in pts], lw, color, dash, closed, fill))

    def ordered(self):
        return [it for it in self._ordered() if not (it[0] == 'text' and not it[3].strip())]

    def _ordered(self):
        """Трубопроводы — под символами; линия прерывается на кране/клапане и подходит к нему с двух сторон."""
        own = set()
        for sym in self.symbols:
            own.update(range(sym[5], sym[6]))
        gaps = [(x, y, ax, half) for kind, x, y, ax, half, *_ in self.symbols if kind in ('valve', 'check') and half > 0]
        is_pipe = lambda i, it: it[0] == 'poly' and not it[5] and i not in own and i not in self.nocheck
        if getattr(self, 'keep_order', False):
            out = []
            for i, it in enumerate(self.items):
                out += _cut(it, gaps) if is_pipe(i, it) else [it]
            return out
        pipes, rest = [], []
        for i, it in enumerate(self.items):
            if is_pipe(i, it) and it[2] >= 0.44:
                pipes += _cut(it, gaps)
            else:
                rest += _cut(it, gaps) if is_pipe(i, it) else [it]
        return pipes + rest

    def stub_arrow(self, x, y, direction):
        """Стрелка на конце линии, уходящей за пределы вида (в вытяжку, на другой лист)."""
        ang = {'right': 0, 'down': math.pi / 2, 'left': math.pi, 'up': -math.pi / 2}[direction]
        self.arrow(x + 2.2 * math.cos(ang), y + 2.2 * math.sin(ang), ang, L=2.2, W=0.9)

    def line(self, x1, y1, x2, y2, **kw):
        self.poly([(x1, y1), (x2, y2)], **kw)

    def rect(self, x, y, w, h, **kw):
        self.poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], closed=True, **kw)

    def circle(self, cx, cy, r, lw=0.35, color=INK, fill=None, dash=None):
        self.items.append(('circle', cx, cy, r, lw, color, fill, dash))

    def text(self, x, y, s, size=2.5, anchor='start', bold=False, color=None):
        if color is None:
            color = RED if '?' in s else INK
        self.items.append(('text', x, y, s, size, anchor, bold, color))

    # ---------- составные элементы
    def arrow(self, x, y, ang, L=2.2, W=0.8, color=INK):
        ca, sa = math.cos(ang), math.sin(ang)
        bx, by = x - L * ca, y - L * sa
        self.poly([(x, y), (bx - W * sa, by + W * ca), (bx + W * sa, by - W * ca)], lw=0.1, color=color, closed=True, fill=color)

    def dim(self, x1, y1, x2, y2, off, label, size=2.5):
        """Линейный размер между точками; off — смещение размерной линии (по нормали)."""
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        a1 = (x1 + nx * off, y1 + ny * off)
        a2 = (x2 + nx * off, y2 + ny * off)
        sgn = 1 if off >= 0 else -1
        ext = 1.5 * sgn
        self.line(x1, y1, a1[0] + nx * ext, a1[1] + ny * ext, lw=0.18)
        self.line(x2, y2, a2[0] + nx * ext, a2[1] + ny * ext, lw=0.18)
        self.line(*a1, *a2, lw=0.18)
        ang = math.atan2(dy, dx)
        self.arrow(*a1, ang + math.pi)
        self.arrow(*a2, ang)
        mx, my = (a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2
        if abs(dy) < 1e-6:          # горизонтальный
            self.text(mx, my - 0.8, label, size, 'middle')
        else:                       # вертикальный — подпись справа от линии
            self.text(mx + 1.2, my + size * 0.35, label, size, 'start')

    def leader(self, x, y, tx, ty, s, size=2.5, anchor='start', dot=True):
        self.line(x, y, tx, ty, lw=0.18)
        shelf = len(s) * size * 0.55
        if anchor == 'start':
            self.line(tx, ty, tx + shelf, ty, lw=0.18)
            self.text(tx + 0.5, ty - 0.8, s, size, 'start')
        else:
            self.line(tx - shelf, ty, tx, ty, lw=0.18)
            self.text(tx - 0.5, ty - 0.8, s, size, 'end')
        if dot:
            self.circle(x, y, 0.5, lw=0.1, fill=INK)

    def axis(self, x1, y1, x2, y2):
        self.line(x1, y1, x2, y2, lw=0.18, dash='axis', color=GREY)

    def clamp(self, x, y, orient='h', tag=None, tag_side=1, w=None, size=None):
        """Кламповое соединение: две ферулы + хомут. orient — направление трубы.
        w — полуширина ферулы (для крупных аппаратных клампов на вертикальной оси)."""
        i0 = len(self.items)
        if orient == 'h':      # труба горизонтальна → ферулы вертикальные
            hw = w or 3.2
            self.rect(x - 1.4, y - hw, 1.1, 2 * hw, lw=0.3, fill='#ffffff')
            self.rect(x + 0.3, y - hw, 1.1, 2 * hw, lw=0.3, fill='#ffffff')
            self.line(x - 1.8, y - hw - 0.6, x + 1.8, y - hw - 0.6, lw=0.5)
            self.line(x - 1.8, y + hw + 0.6, x + 1.8, y + hw + 0.6, lw=0.5)
            if tag:
                ty = y - hw - 4 if tag_side > 0 else y + hw + 6.5
                self.jtag(x, ty, tag)
                if size:
                    self.pending_sizes.append((x, ty, size))
        else:
            hw = w or 3.2
            self.rect(x - hw, y - 1.4, 2 * hw, 1.1, lw=0.3, fill='#ffffff')
            self.rect(x - hw, y + 0.3, 2 * hw, 1.1, lw=0.3, fill='#ffffff')
            self.line(x - hw - 0.6, y - 1.8, x - hw - 0.6, y + 1.8, lw=0.5)
            self.line(x + hw + 0.6, y - 1.8, x + hw + 0.6, y + 1.8, lw=0.5)
            if tag:
                tx = x + hw + 4.8 if tag_side > 0 else x - hw - 4.8
                self.jtag(tx, y, tag)
                if size:
                    self.pending_sizes.append((tx, y, size))
        self._sym('flange' if (w and orient == 'v') else 'clamp', x, y, orient, 1.8, i0)

    def jtag(self, x, y, tag):
        self.circle(x, y, 2.9, lw=0.25, fill='#ffffff', color=BLUE)
        self.text(x, y + 0.9, tag, 2.0, 'middle', color=BLUE)

    def ball_valve(self, x, y, orient='h', s=3.2):
        i0 = len(self.items)
        self._ball_valve(x, y, orient, s)
        self._sym('valve', x, y, orient, s, i0)

    def _ball_valve(self, x, y, orient='h', s=3.2):
        if orient == 'h':
            self.poly([(x - s, y - s * 0.7), (x + s, y + s * 0.7), (x + s, y - s * 0.7), (x - s, y + s * 0.7)], lw=0.3, closed=True, fill='#ffffff')
            self.line(x, y, x, y - s * 1.3, lw=0.3)
            self.line(x - 1.5, y - s * 1.3, x + 1.5, y - s * 1.3, lw=0.4)
        else:
            self.poly([(x - s * 0.7, y - s), (x + s * 0.7, y + s), (x - s * 0.7, y + s), (x + s * 0.7, y - s)], lw=0.3, closed=True, fill='#ffffff')
            self.line(x, y, x + s * 1.3, y, lw=0.3)
            self.line(x + s * 1.3, y - 1.5, x + s * 1.3, y + 1.5, lw=0.4)

    def check_valve(self, x, y, direction='down', s=3.0):
        i0 = len(self.items)
        self._check_valve(x, y, direction, s)
        self._sym('check', x, y, 'v' if direction in ('down', 'up') else 'h', s * 0.8, i0)

    def _check_valve(self, x, y, direction='down', s=3.0):
        d = {'down': (0, 1), 'up': (0, -1), 'right': (1, 0), 'left': (-1, 0)}[direction]
        px, py = -d[1], d[0]
        tip = (x + d[0] * s * 0.8, y + d[1] * s * 0.8)
        b1 = (x - d[0] * s * 0.8 + px * s * 0.7, y - d[1] * s * 0.8 + py * s * 0.7)
        b2 = (x - d[0] * s * 0.8 - px * s * 0.7, y - d[1] * s * 0.8 - py * s * 0.7)
        self.poly([tip, b1, b2], lw=0.3, closed=True, fill=INK)
        self.line(tip[0] + px * s * 0.8, tip[1] + py * s * 0.8, tip[0] - px * s * 0.8, tip[1] - py * s * 0.8, lw=0.5)

    def gauge(self, x, y, r=3.5, up=True, label='PI'):
        i0 = len(self.items)
        self._gauge(x, y, r, up, label)
        self._sym('gauge', x, y, 'v', 0, i0)

    def _gauge(self, x, y, r=3.5, up=True, label='PI'):
        cy = y - r - 3 if up else y + r + 3
        self.line(x, y, x, cy + (r if up else -r), lw=0.3)
        self.circle(x, cy, r, lw=0.3, fill='#ffffff')
        self.text(x, cy + 0.8, label, 1.8, 'middle')

    def reducer(self, x, y, orient, big, small, L=5):
        """Концентрический переход; для 'v' вершина вниз: большой торец сверху."""
        i0 = len(self.items)
        self._reducer(x, y, orient, big, small, L)
        if orient == 'v':
            self._sym('reducer', x, y + L / 2, 'v', L / 2, i0)
        else:
            self._sym('reducer', x + L / 2, y, 'h', L / 2, i0)

    def _reducer(self, x, y, orient, big, small, L=5):
        if orient == 'v':
            self.poly([(x - big / 2, y), (x + big / 2, y), (x + small / 2, y + L), (x - small / 2, y + L)], lw=0.35, closed=True, fill='#ffffff')
        else:
            self.poly([(x, y - big / 2), (x, y + big / 2), (x + L, y + small / 2), (x + L, y - small / 2)], lw=0.35, closed=True, fill='#ffffff')

    def table(self, x, y, colw, rows, rowh=5.0, size=2.2, header=True):
        tw = sum(colw)
        self.rect(x, y, tw, rowh * len(rows), lw=0.5)
        for i, row in enumerate(rows):
            yy = y + i * rowh
            if i:
                self.line(x, yy, x + tw, yy, lw=0.5 if (header and i == 1) else 0.18)
            cx = x
            for j, cell in enumerate(row):
                if i == 0 and j:
                    pass
                self.text(cx + 1, yy + rowh * 0.68, str(cell), size, 'start', bold=(header and i == 0))
                cx += colw[j]
        cx = x
        for wcol in colw[:-1]:
            cx += wcol
            self.line(cx, y, cx, y + rowh * len(rows), lw=0.25)
        return y + rowh * len(rows)

    def frame(self, title, code, sheet_no, sheets, scale='б/м'):
        W, H = self.w, self.h
        self.rect(0.2, 0.2, W - 0.4, H - 0.4, lw=0.1, color='#bbbbbb')
        self.rect(20, 5, W - 25, H - 10, lw=0.7)
        # основная надпись (упрощённая, форма 1 ГОСТ 2.104)
        x0, y0 = W - 5 - 185, H - 5 - 55
        self.rect(x0, y0, 185, 55, lw=0.7)
        cols = [7, 10, 23, 15, 10]
        xs = [x0]
        for c in cols:
            xs.append(xs[-1] + c)
        for i in range(1, 11):
            self.line(x0, y0 + i * 5, x0 + 65, y0 + i * 5, lw=0.7 if i in (2, 3) else 0.18)
        for xx in xs[1:]:
            self.line(xx, y0, xx, y0 + 55, lw=0.7 if xx == xs[-1] else 0.18)
        for lab, xx in zip(['Изм.', 'Лист', '№ докум.', 'Подп.', 'Дата'], xs):
            self.text(xx + 0.6, y0 + 14.2, lab, 1.8)
        for i, lab in enumerate(['Разраб.', 'Пров.', 'Т.контр.', '', 'Н.контр.', 'Утв.']):
            if lab:
                self.text(x0 + 0.6, y0 + 19.2 + i * 5, lab, 1.8)
        self.text(x0 + 18.6, y0 + 19.2, '', 1.8)
        # правая часть
        xr = x0 + 65
        self.line(xr, y0 + 15, x0 + 185, y0 + 15, lw=0.7)
        self.text(xr + 60, y0 + 9.5, code, 4.2, 'middle', bold=True)
        self.line(xr + 70, y0 + 15, xr + 70, y0 + 55, lw=0.7)
        self.line(xr, y0 + 40, x0 + 185, y0 + 40, lw=0.7)
        words = title.split(' ')
        lines_, cur = [], ''
        for wd in words:
            if len(cur) + len(wd) > 32:
                lines_.append(cur); cur = wd
            else:
                cur = (cur + ' ' + wd).strip()
        lines_.append(cur)
        for k, ln in enumerate(lines_[:4]):
            self.text(xr + 35, y0 + 21 + k * 4.6 - (len(lines_) - 1) * 2.3 + 4, ln, 2.9, 'middle', bold=(k == 0))
        # Лит / Масса / Масштаб
        self.line(xr + 70, y0 + 20, x0 + 185, y0 + 20, lw=0.7)
        self.line(xr + 70, y0 + 35, x0 + 185, y0 + 35, lw=0.7)
        for xx in (xr + 87, xr + 102):
            self.line(xx, y0 + 15, xx, y0 + 35, lw=0.7)
        self.text(xr + 74, y0 + 18.8, 'Лит.', 1.9)
        self.text(xr + 89, y0 + 18.8, 'Масса', 1.9)
        self.text(xr + 104, y0 + 18.8, 'Масштаб', 1.9)
        self.text(xr + 78.5, y0 + 29, 'П', 3, 'middle')
        self.text(xr + 94.5, y0 + 29, '—', 3, 'middle')
        self.text(xr + 111, y0 + 29, scale, 3, 'middle')
        self.line(xr + 102, y0 + 35, xr + 102, y0 + 40, lw=0.7)
        self.text(xr + 72, y0 + 38.8, f'Лист {sheet_no}', 2.2)
        self.text(xr + 104, y0 + 38.8, f'Листов {sheets}', 2.2)
        self.text(xr + 92.5, y0 + 49, 'АО «ИНУМиТ»', 3.2, 'middle', bold=True)
        self.text(xr + 35, y0 + 51, 'ТЕФКОТ 770 · реактор 50 л', 2.2, 'middle', color=GREY)


def _cut(it, gaps, tol=0.05):
    """Разрезать ломаную там, где на неё посажен кран или клапан (вдоль его оси)."""
    pts = it[1]
    runs, cur = [], [pts[0]]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        horiz, vert = abs(y1 - y2) < tol, abs(x1 - x2) < tol
        a0, a1 = (x1, x2) if horiz else (y1, y2)
        lo, hi = min(a0, a1), max(a0, a1)
        cuts = []
        for gx, gy, ax, half in gaps:
            if ax == 'h' and horiz and abs(y1 - gy) < tol:
                g = gx
            elif ax == 'v' and vert and abs(x1 - gx) < tol:
                g = gy
            else:
                continue
            c0, c1 = max(lo, g - half), min(hi, g + half)
            if c0 < c1 - 1e-6:
                cuts.append((c0, c1))
        at = (lambda a: (a, y1)) if horiz else (lambda a: (x1, a))
        if not cuts or not (horiz or vert):
            cur.append((x2, y2))
            continue
        sgn = 1 if a1 >= a0 else -1
        for c0, c1 in sorted(cuts, key=lambda c: sgn * c[0]):
            near, far = (c0, c1) if sgn > 0 else (c1, c0)
            cur.append(at(near))
            runs.append(cur)
            cur = [at(far)]
        cur.append((x2, y2))
    runs.append(cur)
    out = []
    for r in runs:
        r = [p for k, p in enumerate(r) if k == 0 or abs(p[0] - r[k - 1][0]) + abs(p[1] - r[k - 1][1]) > 1e-6]
        if len(r) > 1:
            out.append((it[0], r) + tuple(it[2:]))
    return out


# ================= вывод SVG =================
def to_svg(sh):
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sh.w} {sh.h}" width="{sh.w}mm" height="{sh.h}mm" '
           f'font-family="Arial, \'Liberation Sans\', sans-serif"><rect width="100%" height="100%" fill="#fff"/>']
    for it in sh.ordered():
        if it[0] == 'poly':
            _, pts, lw, color, dash, closed, fill = it
            d = 'M' + ' L'.join(f'{x:.2f},{y:.2f}' for x, y in pts) + (' Z' if closed else '')
            da = {'axis': ' stroke-dasharray="6 1.5 1 1.5"', 'dash': ' stroke-dasharray="3 1.5"', 'dot': ' stroke-dasharray="0.6 1"'}.get(dash, '')
            out.append(f'<path d="{d}" fill="{fill if fill else "none"}" stroke="{color}" stroke-width="{lw}"{da} stroke-linejoin="round"/>')
        elif it[0] == 'circle':
            _, cx, cy, r, lw, color, fill, dash = it
            da = ' stroke-dasharray="3 1.5"' if dash == 'dash' else ''
            out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill if fill else "none"}" stroke="{color}" stroke-width="{lw}"{da}/>')
        else:
            _, x, y, s, size, anchor, bold, color = it
            fw = ' font-weight="bold"' if bold else ''
            out.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" fill="{color}"{fw}>{escape(s)}</text>')
    out.append('</svg>')
    return '\n'.join(out)


# ================= вывод VSDX =================
MM = 1 / 25.4


def _shape_poly(i, sh, pts, lw, color, dash, closed, fill):
    P = [(x * MM, (sh.h - y) * MM) for x, y in pts]
    minx, maxx = min(p[0] for p in P), max(p[0] for p in P)
    miny, maxy = min(p[1] for p in P), max(p[1] for p in P)
    w, h = max(maxx - minx, 0.0005), max(maxy - miny, 0.0005)
    pat = {'axis': 4, 'dash': 2, 'dot': 3}.get(dash, 1)
    cells = (f"<Cell N='PinX' V='{minx + w / 2:.5f}'/><Cell N='PinY' V='{miny + h / 2:.5f}'/>"
             f"<Cell N='Width' V='{w:.5f}'/><Cell N='Height' V='{h:.5f}'/>"
             f"<Cell N='LocPinX' V='{w / 2:.5f}' F='Width*0.5'/><Cell N='LocPinY' V='{h / 2:.5f}' F='Height*0.5'/>"
             f"<Cell N='LineColor' V='{color}'/><Cell N='LineWeight' V='{lw * MM:.5f}' U='MM'/><Cell N='LinePattern' V='{pat}'/>"
             f"<Cell N='Rounding' V='0'/>")
    if fill:
        cells += f"<Cell N='FillForegnd' V='{fill}'/><Cell N='FillPattern' V='1'/>"
    rows = [f"<Cell N='NoFill' V='{0 if (closed and fill) else 1}'/><Cell N='NoLine' V='0'/><Cell N='NoShow' V='0'/><Cell N='NoSnap' V='0'/>"]
    seq = list(P) + ([P[0]] if closed else [])
    for k, (x, y) in enumerate(seq):
        rows.append(f"<Row T='{'RelMoveTo' if k == 0 else 'RelLineTo'}' IX='{k + 1}'>"
                    f"<Cell N='X' V='{(x - minx) / w:.5f}'/><Cell N='Y' V='{(y - miny) / h:.5f}'/></Row>")
    return (f"<Shape ID='{i}' Type='Shape' LineStyle='3' FillStyle='3' TextStyle='3'>{cells}"
            f"<Section N='Geometry' IX='0'>{''.join(rows)}</Section></Shape>")


def _shape_circle(i, sh, cx, cy, r, lw, color, fill, dash):
    d = 2 * r * MM
    X, Y = cx * MM, (sh.h - cy) * MM
    fc = f"<Cell N='FillForegnd' V='{fill}'/><Cell N='FillPattern' V='1'/>" if fill else ''
    pat = 2 if dash == 'dash' else 1
    return (f"<Shape ID='{i}' Type='Shape' LineStyle='3' FillStyle='3' TextStyle='3'>"
            f"<Cell N='PinX' V='{X:.5f}'/><Cell N='PinY' V='{Y:.5f}'/><Cell N='Width' V='{d:.5f}'/><Cell N='Height' V='{d:.5f}'/>"
            f"<Cell N='LocPinX' V='{d / 2:.5f}' F='Width*0.5'/><Cell N='LocPinY' V='{d / 2:.5f}' F='Height*0.5'/>"
            f"<Cell N='LineColor' V='{color}'/><Cell N='LineWeight' V='{lw * MM:.5f}' U='MM'/><Cell N='LinePattern' V='{pat}'/>{fc}"
            f"<Section N='Geometry' IX='0'><Cell N='NoFill' V='{0 if fill else 1}'/><Cell N='NoLine' V='0'/><Cell N='NoShow' V='0'/><Cell N='NoSnap' V='0'/>"
            f"<Row T='Ellipse' IX='1'><Cell N='X' V='{d / 2:.5f}' F='Width*0.5'/><Cell N='Y' V='{d / 2:.5f}' F='Height*0.5'/>"
            f"<Cell N='A' V='{d:.5f}' F='Width*1'/><Cell N='B' V='{d / 2:.5f}' F='Height*0.5'/>"
            f"<Cell N='C' V='{d / 2:.5f}' F='Width*0.5'/><Cell N='D' V='{d:.5f}' F='Height*1'/></Row></Section></Shape>")


def _shape_text(i, sh, x, y, s, size, anchor, bold, color):
    sz = size * MM                       # высота шрифта ≈ кегль
    w = max(len(s), 1) * sz * 0.9 + 0.12
    h = sz * 1.45
    X = x * MM
    cx = {'start': X + w / 2, 'middle': X, 'end': X - w / 2}[anchor]
    cy = (sh.h - y) * MM + sz * 0.33
    ha = {'start': 0, 'middle': 1, 'end': 2}[anchor]
    return (f"<Shape ID='{i}' Type='Shape' LineStyle='3' FillStyle='3' TextStyle='3'>"
            f"<Cell N='PinX' V='{cx:.5f}'/><Cell N='PinY' V='{cy:.5f}'/><Cell N='Width' V='{w:.5f}'/><Cell N='Height' V='{h:.5f}'/>"
            f"<Cell N='LocPinX' V='{w / 2:.5f}' F='Width*0.5'/><Cell N='LocPinY' V='{h / 2:.5f}' F='Height*0.5'/>"
            f"<Cell N='LeftMargin' V='0'/><Cell N='RightMargin' V='0'/><Cell N='TopMargin' V='0'/><Cell N='BottomMargin' V='0'/>"
            f"<Cell N='VerticalAlign' V='1'/>"
            f"<Section N='Character'><Row IX='0'><Cell N='Font' V='Arial'/><Cell N='Color' V='{color}'/><Cell N='Size' V='{sz:.5f}' U='PT'/>"
            f"<Cell N='Style' V='{1 if bold else 0}'/></Row></Section>"
            f"<Section N='Paragraph'><Row IX='0'><Cell N='HorzAlign' V='{ha}'/></Row></Section>"
            f"<Text>{escape(s)}</Text></Shape>")


def to_vsdx(sheets, template, out):
    work = out + '.d'
    if os.path.exists(work):
        shutil.rmtree(work)
    shutil.copytree(template, work)
    ns = ("xmlns='http://schemas.microsoft.com/office/visio/2012/main' "
          "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships' xml:space='preserve'")
    pages_xml, rels, overrides = [], [], []
    for n, sh in enumerate(sheets, 1):
        shapes, i = [], 0
        for it in sh.ordered():
            i += 1
            if it[0] == 'poly':
                shapes.append(_shape_poly(i, sh, *it[1:]))
            elif it[0] == 'circle':
                shapes.append(_shape_circle(i, sh, *it[1:]))
            else:
                shapes.append(_shape_text(i, sh, *it[1:]))
        open(f'{work}/visio/pages/page{n}.xml', 'w', encoding='utf-8').write(
            f"<?xml version='1.0' encoding='utf-8' ?>\n<PageContents {ns}><Shapes>{''.join(shapes)}</Shapes></PageContents>")
        W, H = sh.w * MM, sh.h * MM
        pages_xml.append(
            f"<Page ID='{n - 1}' NameU='{escape(sh.name)}' Name='{escape(sh.name)}' ViewScale='-1' ViewCenterX='{W / 2:.4f}' ViewCenterY='{H / 2:.4f}'>"
            f"<PageSheet LineStyle='0' FillStyle='0' TextStyle='0'><Cell N='PageWidth' V='{W:.5f}'/><Cell N='PageHeight' V='{H:.5f}'/>"
            f"<Cell N='PageScale' V='0.03937007874015748' U='MM'/><Cell N='DrawingScale' V='0.03937007874015748' U='MM'/>"
            f"<Cell N='DrawingSizeType' V='0'/><Cell N='DrawingScaleType' V='0'/><Cell N='PrintPageOrientation' V='2'/></PageSheet>"
            f"<Rel r:id='rId{n}'/></Page>")
        rels.append(f'<Relationship Id="rId{n}" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page{n}.xml"/>')
        overrides.append(f'<Override PartName="/visio/pages/page{n}.xml" ContentType="application/vnd.ms-visio.page+xml"/>')
    open(f'{work}/visio/pages/pages.xml', 'w', encoding='utf-8').write(
        f"<?xml version='1.0' encoding='utf-8' ?>\n<Pages {ns}>{''.join(pages_xml)}</Pages>")
    open(f'{work}/visio/pages/_rels/pages.xml.rels', 'w', encoding='utf-8').write(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + ''.join(rels) + '</Relationships>')
    if os.path.exists(f'{work}/visio/pages/_rels/page1.xml.rels'):
        os.remove(f'{work}/visio/pages/_rels/page1.xml.rels')
    ct = open(f'{work}/[Content_Types].xml', encoding='utf-8').read()
    ct = ct.replace('<Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>', ''.join(overrides))
    ct = ct.replace('<Default Extension="emf" ContentType="image/x-emf"/>', '')
    open(f'{work}/[Content_Types].xml', 'w', encoding='utf-8').write(ct)
    ww = open(f'{work}/visio/windows.xml', encoding='utf-8').read()
    ww = re.sub(r"ViewScale='1' ViewCenterX='[^']*' ViewCenterY='[^']*'", "ViewScale='-1' ViewCenterX='8.27' ViewCenterY='5.85'", ww)
    open(f'{work}/visio/windows.xml', 'w', encoding='utf-8').write(ww)
    names = ''.join(f'<vt:lpstr>{escape(s.name)}</vt:lpstr>' for s in sheets)
    app = open(f'{work}/docProps/app.xml', encoding='utf-8').read()
    app = re.sub(r'<vt:lpstr>Pages</vt:lpstr></vt:variant><vt:variant><vt:i4>\d+</vt:i4>',
                 f'<vt:lpstr>Pages</vt:lpstr></vt:variant><vt:variant><vt:i4>{len(sheets)}</vt:i4>', app)
    app = re.sub(r'<TitlesOfParts><vt:vector size="\d+" baseType="lpstr">.*?</vt:vector>',
                 f'<TitlesOfParts><vt:vector size="{len(sheets) + 1}" baseType="lpstr">{names}<vt:lpstr>Dynamic connector</vt:lpstr></vt:vector>', app)
    open(f'{work}/docProps/app.xml', 'w', encoding='utf-8').write(app)
    r = open(f'{work}/_rels/.rels', encoding='utf-8').read()
    r = re.sub(r'<Relationship Id="rId2"[^>]*thumbnail[^>]*/>', '', r)
    open(f'{work}/_rels/.rels', 'w', encoding='utf-8').write(r)
    if os.path.exists(f'{work}/docProps/thumbnail.emf'):
        os.remove(f'{work}/docProps/thumbnail.emf')
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(f'{work}/[Content_Types].xml', '[Content_Types].xml')
        for dp, _, fs in os.walk(work):
            for f in fs:
                full = os.path.join(dp, f)
                arc = os.path.relpath(full, work)
                if arc != '[Content_Types].xml':
                    z.write(full, arc)
    shutil.rmtree(work)
