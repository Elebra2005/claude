"""Автопроверка чертежей: стыки символов с линиями, висящие концы линий, наложения подписей."""
import math, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import cherteg

TOL = 0.8


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def text_box(it):
    _, x, y, s, size, anchor, bold, color = it
    w = len(s) * size * (0.58 if bold else 0.53)
    x0 = {'start': x, 'middle': x - w / 2, 'end': x - w}[anchor]
    return (x0, y - size * 0.75, x0 + w, y + size * 0.15)


def overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w > 0.25 and h > 0.25


def check_sheet(sh, only=None):
    items = sh.items
    segs, circs = [], []
    for i, it in enumerate(items):
        if it[0] == 'poly':
            if not it[5] and (it[4] == 'axis' or it[2] < 0.25):      # осевые, размерные, выноски — не соединения
                continue
            pts = it[1] + ([it[1][0]] if it[5] else [])
            for a, b in zip(pts, pts[1:]):
                segs.append((a, b, i))
        elif it[0] == 'circle':
            circs.append((it[1], it[2], it[3], i))
    sym_owner = {}
    for k, sym in enumerate(sh.symbols):
        for i in range(sym[5], sym[6]):
            sym_owner[i] = k

    def touches(px, py, excl):
        for a, b, i in segs:
            if i in excl:
                continue
            if seg_dist(px, py, *a, *b) < TOL:
                return True
        for cx, cy, r, i in circs:
            if i in excl:
                continue
            if abs(math.hypot(px - cx, py - cy) - r) < TOL:
                return True
        return False

    problems = []
    # 1. символы: обе стороны вдоль оси должны касаться линии/аппарата
    for kind, x, y, axis, half, i0, i1 in sh.symbols:
        excl = set(range(i0, i1))
        if kind == 'flange':
            if not any(i not in excl and seg_dist(x, y, *a, *b) < TOL for a, b, i in segs):
                problems.append(f'фланцевый кламп не на стыке ({x:.1f},{y:.1f})')
            continue
        if kind == 'gauge':
            if not touches(x, y, excl):
                problems.append(f'манометр висит ({x:.1f},{y:.1f})')
            continue
        d = half + 0.3
        pts = [(x - d, y), (x + d, y)] if axis == 'h' else [(x, y - d), (x, y + d)]
        miss = [p for p in pts if not touches(*p, excl)]
        if miss:
            problems.append(f'{kind} {axis} ({x:.1f},{y:.1f}) не присоединён: ' + ', '.join(f'({p[0]:.1f},{p[1]:.1f})' for p in miss))
    # 2. концы линий (трубы/трубки/рукава)
    texts = [(i, it) for i, it in enumerate(items) if it[0] == 'text']
    inside_boxes = list(getattr(sh, 'vessels', []))
    for i, it in enumerate(items):
        if it[0] != 'poly' or it[5] or it[2] < 0.44 or it[4] == 'axis' or i in sym_owner or i in sh.nocheck:
            continue
        for (px, py) in (it[1][0], it[1][-1]):
            if touches(px, py, {i}):
                continue
            if any(f[0] + 0.5 < px < f[2] - 0.5 and f[1] + 0.5 < py < f[3] - 0.5 for f in inside_boxes):
                continue          # конец внутри аппарата (погружная трубка, сифон)
            near_txt = any(math.hypot(t[1] - px, t[2] - py) < 5 or (t[5] == 'end' and abs(t[1] - px) < 3 and abs(t[2] - py) < 4) or (t[5] == 'start' and abs(t[1] - px) < 4 and abs(t[2] - py) < 4) for _, t in texts)
            if not near_txt:
                problems.append(f'висит конец линии ({px:.1f},{py:.1f})')
    # 3. наложения подписей (кроме таблиц и штампа)
    W, H = sh.w, sh.h
    tb = (W - 190, H - 60, W, H)
    boxes = []
    for i, it in enumerate(texts):
        b = text_box(it[1])
        if not it[1][3].strip():
            continue
        if b[0] > tb[0] and b[1] > tb[1]:
            continue
        boxes.append((b, it[1][3]))
    tags = [(c[0] - c[2], c[1] - c[2], c[0] + c[2], c[1] + c[2]) for c in circs if abs(c[2] - 2.9) < 0.01]
    for a in range(len(boxes)):
        for b in range(a + 1, len(boxes)):
            if overlap(boxes[a][0], boxes[b][0]):
                problems.append(f'подписи накладываются: «{boxes[a][1]}» / «{boxes[b][1]}»')
    tagtexts = set()
    for tg in tags:
        for bx, s in boxes:
            if overlap(tg, bx) and not s.isdigit():
                problems.append(f'номер соединения закрывает подпись «{s}» ({tg[0]+2.9:.1f},{tg[1]+2.9:.1f})')
    for a in range(len(tags)):
        for b in range(a + 1, len(tags)):
            if overlap(tags[a], tags[b]):
                problems.append(f'номера соединений накладываются ({tags[a][0]+2.9:.1f},{tags[a][1]+2.9:.1f})')
    # 3б. подписи на символах арматуры
    for kind, x, y, axis, half, i0, i1 in sh.symbols:
        xs, ys = [], []
        for j in range(i0, i1):
            it = items[j]
            if it[0] == 'poly':
                xs += [p[0] for p in it[1]]; ys += [p[1] for p in it[1]]
            elif it[0] == 'circle' and abs(it[3] - 2.9) > 0.01:
                xs += [it[1] - it[3], it[1] + it[3]]; ys += [it[2] - it[3], it[2] + it[3]]
        if not xs:
            continue
        sb = (min(xs), min(ys), max(xs), max(ys))
        for bx, txt in boxes:
            if overlap(sb, bx) and not txt.isdigit() and txt not in ('PI', 'P', 'PI-4', 'PI-1'):
                problems.append(f'подпись «{txt}» заходит на символ {kind} ({x:.1f},{y:.1f})')
    filled = []
    for it in items:
        if it[0] == 'poly' and it[5] and it[6]:
            xs = [p[0] for p in it[1]]; ys = [p[1] for p in it[1]]
            filled.append((min(xs), min(ys), max(xs), max(ys)))
    # 4. подписи, лежащие на трубопроводах
    def seg_hits_box(a, b, bx):
        x0, y0, x1, y1 = bx[0] + 0.2, bx[1] + 0.2, bx[2] - 0.2, bx[3] - 0.2
        for t in [k / 20 for k in range(21)]:
            px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            if x0 < px < x1 and y0 < py < y1:
                return True
        return False
    for i, it in enumerate(items):
        if it[0] != 'poly' or it[5] or it[2] < 0.44 or i in sym_owner or i in sh.nocheck:
            continue
        for bx, txt in boxes:
            cxm, cym = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
            if any(f[0] < cxm < f[2] and f[1] < cym < f[3] for f in filled):
                continue          # подпись внутри аппарата/символа с заливкой — линия под ним
            for a, b in zip(it[1], it[1][1:]):
                if seg_hits_box(a, b, bx):
                    problems.append(f'подпись «{txt}» лежит на линии')
                    break
    return problems


if __name__ == '__main__':
    sheets = cherteg.build()
    total = 0
    for sh in sheets:
        pr = check_sheet(sh)
        total += len(pr)
        print(f'=== {sh.name}: {len(pr)}')
        for p in pr:
            print('  ', p)
    print('ИТОГО замечаний:', total)
