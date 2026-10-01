"""Размещение подписей размера у номеров клампов: ищем свободное место вокруг номера."""
import math
from draw import BLUE

SIZE = 1.7


def _text_box(x, y, s, size, anchor, bold=False):
    w = len(s) * size * (0.58 if bold else 0.53)
    x0 = {'start': x, 'middle': x - w / 2, 'end': x - w}[anchor]
    return (x0, y - size * 0.75, x0 + w, y + size * 0.15)


def _overlap(a, b, m=0.0):
    return min(a[2], b[2]) - max(a[0], b[0]) > -m and min(a[3], b[3]) - max(a[1], b[1]) > -m


def _seg_hits(a, b, bx, m=0.3):
    x0, y0, x1, y1 = bx[0] - m, bx[1] - m, bx[2] + m, bx[3] + m
    n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.3))
    for k in range(n + 1):
        t = k / n
        px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        if x0 < px < x1 and y0 < py < y1:
            return True
    return False


def _circle_hits(cx, cy, r, bx, m=0.3):
    near = math.hypot(max(bx[0] - cx, 0, cx - bx[2]), max(bx[1] - cy, 0, cy - bx[3]))
    return near < r + m


def place_sizes(sh):
    pend = getattr(sh, 'pending_sizes', [])
    if not pend:
        return
    segs, circs, boxes = [], [], []
    for it in sh.items:
        if it[0] == 'poly':
            pts = it[1] + ([it[1][0]] if it[5] else [])
            segs += list(zip(pts, pts[1:]))
        elif it[0] == 'circle':
            circs.append((it[1], it[2], it[3]))
        elif it[0] == 'text' and it[3].strip():
            boxes.append(_text_box(it[1], it[2], it[3], it[4], it[5], it[6]))
    for kind, x, y, axis, half, i0, i1 in sh.symbols:
        xs, ys = [], []
        for j in range(i0, i1):
            it = sh.items[j]
            if it[0] == 'poly':
                xs += [p[0] for p in it[1]]; ys += [p[1] for p in it[1]]
        if xs:
            boxes.append((min(xs), min(ys), max(xs), max(ys)))

    def free(bx):
        if bx[0] < 12 or bx[1] < 8 or bx[2] > sh.w - 8 or bx[3] > sh.h - 8:
            return False
        if any(_overlap(bx, b, 0.6) for b in boxes):
            return False
        if any(_circle_hits(cx, cy, r, bx) for cx, cy, r in circs):
            return False
        return not any(_seg_hits(a, b, bx, 0.6) for a, b in segs)

    for tx, ty, s in pend:
        c = [(tx + 3.4, ty + 0.6, 'start'), (tx - 3.4, ty + 0.6, 'end'), (tx, ty + 4.9, 'middle'), (tx, ty - 3.6, 'middle'),
             (tx + 3.2, ty + 3.6, 'start'), (tx + 3.2, ty - 2.4, 'start'), (tx - 3.2, ty + 3.6, 'end'), (tx - 3.2, ty - 2.4, 'end'),
             (tx + 5.5, ty + 0.6, 'start'), (tx - 5.5, ty + 0.6, 'end'), (tx, ty + 7.0, 'middle'), (tx, ty - 5.6, 'middle'),
             (tx - 4.5, ty + 5.5, 'end'), (tx - 4.5, ty - 4.0, 'end'), (tx + 4.5, ty + 5.5, 'start'), (tx + 4.5, ty - 4.0, 'start'),
             (tx - 8.0, ty + 0.6, 'end'), (tx + 8.0, ty + 0.6, 'start')]
        best = next((p for p in c if free(_text_box(p[0], p[1], s, SIZE, p[2]))), None)
        if best is None:
            print(f'  {sh.name}: нет места для «{s}» у номера ({tx:.1f},{ty:.1f})')
            best = c[0]
        sh.text(best[0], best[1], s, SIZE, best[2], color=BLUE)
        boxes.append(_text_box(best[0], best[1], s, SIZE, best[2]))
    sh.pending_sizes = []
