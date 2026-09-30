"""Лист «Условные обозначения» для технологической схемы и для монтажных чертежей (A3)."""
import math
from draw import Sheet, INK, RED, BLUE, GREY

GREEN = '#2e7d32'


def _table(s, items, x0, y0, draw_sym, widths=(30, 52, 104), rowh=11.0):
    """Таблица с общей сеткой: Обозначение | Наименование | Пояснение."""
    W = sum(widths); hh = 7.0
    H = hh + rowh * len(items)
    xs = [x0]
    for w in widths:
        xs.append(xs[-1] + w)
    s.rect(x0, y0, W, H, lw=0.5, color=INK, nc=True)
    s.rect(x0, y0, W, hh, lw=0.3, color=INK, fill='#eef1f2', nc=True)
    for xx in xs[1:-1]:
        s.line(xx, y0, xx, y0 + H, lw=0.3, color=INK, nc=True)
    for k, head in enumerate(('Обозначение', 'Наименование', 'Пояснение')):
        s.text(xs[k] + 2, y0 + 4.8, head, 2.4, bold=True, color=INK)
    for i, (key, title, text) in enumerate(items):
        y = y0 + hh + i * rowh
        if i:
            s.line(x0, y, x0 + W, y, lw=0.2, color='#8a9499', nc=True)
        draw_sym(s, key, xs[0] + widths[0] / 2, y + rowh / 2)
        s.text(xs[1] + 2, y + rowh / 2 + 0.9, title, 2.3, bold=True, color=INK)
        lines = [ln for ln in text if ln]
        yy = y + rowh / 2 + 0.9 - (len(lines) - 1) * 1.6
        for ln in lines:
            s.text(xs[2] + 2, yy, ln, 2.1, color='#2f3a3e')
            yy += 3.2
    return y0 + H


# ------------------------------------------------------------------ технологическая схема
SCHEME_LINES = [('amine', '#b4491b', 0.75, None, 'Газ CH₃NH₂', ['генератор → колонны → реактор']),
                ('aq', '#a07a12', 0.64, None, 'Водный метиламин', ['канистра V-1 → P-1 → G-1']),
                ('argon', '#2d6fb3', 0.64, None, 'Аргон', ['от баллона через ротаметр PR-1']),
                ('vent', '#7a4fa0', 0.75, None, 'Отдувка и сбросы', ['гребёнка → коллектор сбросов → вытяжка']),
                ('liq', '#2f6b3a', 0.81, None, 'Жидкость, продукт', ['дозирование, выгрузка, фасовка']),
                ('cool', '#0f8a8a', 0.64, 'dash', 'Теплоноситель', ['чиллер ↔ рубашка и E-1']),
                ('vac', '#37474f', 0.81, 'dash', 'Вакуум', ['VV-1 → вакуумный насос VP-1']),
                ('thin', '#5d666d', 0.29, None, 'Импульсная линия', ['к манометру, термометру'])]


def _scheme_sym(s, key, cx, cy):
    K = 0.29
    if key.startswith('line:'):
        _, col, lw, dash = key.split(':')
        s.poly([(cx - 14, cy), (cx + 14, cy)], lw=float(lw), color=col, dash=dash or None, nc=True)
        return
    P = lambda pts: [(cx + a * K, cy + b * K) for a, b in pts]
    fg = '#1d2226'
    if key == 'bv':
        s.poly([(cx - 14, cy), (cx - 2.6, cy)], lw=0.64, color=GREY, nc=True); s.poly([(cx + 2.6, cy), (cx + 14, cy)], lw=0.64, color=GREY, nc=True)
        s.poly(P([(-9, -6), (9, 6), (9, -6), (-9, 6)]), lw=0.4, color=fg, closed=True, fill='#ffffff')
    elif key == 'nrv':
        s.poly([(cx - 14, cy), (cx - 2.3, cy)], lw=0.64, color=GREY, nc=True); s.poly([(cx + 2.3, cy), (cx + 14, cy)], lw=0.64, color=GREY, nc=True)
        s.poly(P([(-8, -6), (6, 0), (-8, 6)]), lw=0.4, color=fg, closed=True, fill=fg)
        s.poly(P([(8, -7), (8, 7)]), lw=0.6, color=fg, nc=True)
        s.arrow(cx + 12, cy - 4, 0, L=1.6, W=0.7)
    elif key == 'psv':
        s.poly([(cx, cy + 5), (cx, cy + 2.3)], lw=0.64, color=GREY, nc=True)
        s.rect(cx - 2.1, cy - 2.3, 4.2, 4.6, lw=0.45, color=fg, fill='#ffffff')
        s.poly([(cx, cy - 2.3), (cx, cy - 5)], lw=0.64, color=GREY, nc=True)
    elif key == 'psv1':
        s.rect(cx - 3.5, cy - 4.4, 7, 8.8, lw=0.45, color=fg, fill='#ffffff'); s.line(cx - 2.3, cy - 3.2, cx + 2.3, cy + 3.2, lw=0.29, color=fg)
    elif key == 'shp':
        s.rect(cx - 4, cy - 5.2, 8, 10.4, lw=0.45, color=fg, fill='#ffffff'); s.text(cx, cy + 1, 'ШП', 2.2, 'middle', color=fg)
    elif key in ('pi', 'ti', 'r'):
        s.circle(cx, cy, 3.2, lw=0.45, color=fg, fill='#ffffff'); s.text(cx, cy + 0.9, {'pi': 'PI', 'ti': 'TI', 'r': 'R'}[key], 2.2, 'middle', color=fg)
    elif key == 'pump':
        s.rect(cx - 8, cy - 4, 16, 8, lw=0.45, color=fg, fill='#ffffff'); s.text(cx, cy + 1, 'P-2', 2.4, 'middle', bold=True, color=fg)
    elif key == 'vp':
        s.circle(cx, cy, 4.9, lw=0.45, color=fg, fill='#ffffff'); s.line(cx - 3.5, cy, cx + 3.5, cy, lw=0.29); s.line(cx, cy - 3.5, cx, cy + 3.5, lw=0.29)
    elif key == 'rot':
        s.poly([(cx - 5, cy - 5), (cx + 5, cy - 5), (cx + 3, cy + 5), (cx - 3, cy + 5)], lw=0.45, color=fg, closed=True, fill='#ffffff')
    elif key == 'vessel':
        s.rect(cx - 7, cy - 4.5, 14, 9, lw=0.45, color=fg, fill='#ffffff')
    elif key == 'column':
        s.rect(cx - 3.5, cy - 4.8, 7, 9.6, lw=0.45, color=fg, fill='#eef3f5')
    elif key == 'coil':
        s.rect(cx - 4, cy - 4.8, 8, 9.6, lw=0.45, color=fg, fill='#ffffff')
        s.poly([(cx - 2, cy - 4), (cx + 2, cy - 2.5), (cx - 2, cy - 1), (cx + 2, cy + 0.5), (cx - 2, cy + 2), (cx + 2, cy + 3.5)], lw=0.3, color='#0f8a8a', nc=True)
    elif key == 'level':
        s.rect(cx - 7, cy - 4.5, 14, 9, lw=0.45, color=fg, fill='#ffffff')
        s.line(cx - 6, cy, cx + 6, cy, lw=0.3, dash='dash', color='#2f6b3a')
    elif key == 'arrow':
        s.poly([(cx - 12, cy), (cx + 8, cy)], lw=0.64, color='#7a4fa0', nc=True); s.arrow(cx + 11, cy, 0, L=3, W=1.3)
    elif key == 'lock':
        s.text(cx, cy + 1.5, 'SV-2*', 2.6, 'middle', color=fg)
    elif key == 'hop':
        s.poly([(cx - 12, cy), (cx - 2, cy), (cx - 1, cy - 2), (cx + 1, cy - 2), (cx + 2, cy), (cx + 12, cy)], lw=0.64, color='#2d6fb3', nc=True)
        s.poly([(cx, cy - 4.5), (cx, cy + 4.5)], lw=0.64, color='#7a4fa0', nc=True)
    elif key == 'dip':
        s.rect(cx - 7, cy - 3.5, 14, 8, lw=0.45, color=fg, fill='#eef3f5'); s.poly([(cx + 3, cy - 5), (cx + 3, cy + 3)], lw=0.75, color='#b4491b', nc=True)


def scheme_legend():
    s = Sheet('Условные обозначения', 420.0, 297.0)
    s.keep_order = True
    s.rect(0.2, 0.2, 419.6, 296.6, lw=0.1, color='#bbbbbb', nc=True)
    s.text(12, 16, 'Технологическая схема ТЕФКОТ 770 — условные обозначения', 4.2, bold=True, color=INK)
    s.text(12, 23, 'Позиции (R-1, G-1, SV-1 …) совпадают со спецификацией и монтажными чертежами ИНУМ.770-50.00', 2.6, color=GREY)
    lines = [(f'line:{c}:{w}:{d or ""}', t, x) for _, c, w, d, t, x in SCHEME_LINES]
    items = [('bv', 'Кран шаровой', ['открыт/закрыт вручную;', 'обозначения SV-, AV-, VV-, V-, CV-']),
             ('nrv', 'Обратный клапан', ['пропускает только по стрелке; NRV-1 на гребёнке —', 'аварийный сброс ≈0,2 бар, без крана']),
             ('psv', 'Предохранительный клапан', ['PSV-2, -3, -4: открывается при превышении', 'уставки, сброс по трубке']),
             ('shp', 'Шпунт-аппарат PCV-1', ['держит в реакторе 50–80 мбар,', 'излишек газа выпускает']),
             ('pi', 'Манометр (мановакуумметр)', ['PI-1 … PI-5 — давление', 'в аппарате или линии']),
             ('ti', 'Термометр', ['TI — Pt100 в термогильзе', 'реактора']),
             ('r', 'Редуктор баллона', ['снижает давление аргона', 'до 0,2–0,3 бар']),
             ('rot', 'Ротаметр с вентилем PR-1', ['задаёт расход аргона,', '0,1 … 10 л/мин']),
             ('pump', 'Насос мембранный пневм.', ['P-1, P-2, P-3; привод', 'сжатым воздухом, не искрит']),
             ('vp', 'Вакуумный насос VP-1', ['мембранный, ≤ 10 мбар;', 'выхлоп в вытяжку']),
             ('vessel', 'Аппарат, ёмкость', ['реактор, генератор, нутч,', 'канистры']),
             ('column', 'Колонна с засыпкой', ['C-1 — сита 3A, C-2 — NaOH/KOH;', 'газ идёт снизу вверх']),
             ('coil', 'Конденсатор со змеевиком', ['E-1: змеевик охлаждается', 'теплоносителем −25 °C']),
             ('level', 'Уровень жидкости', ['штрих — уровень жидкости', 'в аппарате']),
             ('dip', 'Погружная / сифонная трубка', ['вход ниже уровня или до дна', 'аппарата']),
             ('arrow', 'Выход наружу', ['стрелка — в вытяжку', 'или на другой узел']),
             ('hop', 'Пересечение без соединения', ['мостик — линии не', 'соединены'])]
    allr = lines + items
    half = (len(allr) + 1) // 2
    _table(s, allr[:half], 12, 30, _scheme_sym)
    _table(s, allr[half:], 214, 30, _scheme_sym)
    return s


# ------------------------------------------------------------------ монтажные чертежи
def _draw_sym(s, key, cx, cy):
    if key == 'pipe':
        s.poly([(cx - 14, cy), (cx + 14, cy)], lw=1.2, nc=True)
    elif key == 'tube':
        s.poly([(cx - 14, cy), (cx + 14, cy)], lw=0.45, color='#333333', nc=True)
    elif key == 'hose':
        s.poly([(cx - 14, cy), (cx + 14, cy)], lw=0.9, color='#333333', dash='dash', nc=True)
    elif key == 'ground':
        s.poly([(cx - 14, cy), (cx + 10, cy)], lw=0.4, color=GREEN, dash='dash', nc=True)
        s.line(cx + 10, cy, cx + 10, cy + 3, lw=0.4, color=GREEN); s.line(cx + 7, cy + 3, cx + 13, cy + 3, lw=0.5, color=GREEN)
        s.line(cx + 8, cy + 4.3, cx + 12, cy + 4.3, lw=0.4, color=GREEN); s.line(cx + 9, cy + 5.6, cx + 11, cy + 5.6, lw=0.3, color=GREEN)
    elif key == 'clamp':
        s.poly([(cx - 14, cy), (cx + 5, cy)], lw=1.2, nc=True)
        s.clamp(cx - 3, cy, 'h')
        s.jtag(cx + 9, cy, '412')
    elif key == 'valve':
        s.poly([(cx - 14, cy), (cx - 3.2, cy)], lw=1.2, nc=True); s.poly([(cx + 3.2, cy), (cx + 14, cy)], lw=1.2, nc=True)
        s._ball_valve(cx, cy, 'h', 3.2)
    elif key == 'check':
        s.poly([(cx - 14, cy), (cx - 2.4, cy)], lw=1.2, nc=True); s.poly([(cx + 2.4, cy), (cx + 14, cy)], lw=1.2, nc=True)
        s._check_valve(cx, cy, 'right', 3.0)
    elif key == 'gauge':
        s.poly([(cx - 14, cy + 4), (cx + 14, cy + 4)], lw=1.2, nc=True)
        s._gauge(cx, cy + 4, 3.2, True, 'PI')
    elif key == 'reducer':
        s.poly([(cx - 14, cy), (cx - 3, cy)], lw=1.6, nc=True); s.poly([(cx + 3, cy), (cx + 14, cy)], lw=1.0, nc=True)
        s._reducer(cx - 3, cy, 'h', 6.4, 3.2, 6)
    elif key == 'psv':
        s.poly([(cx, cy + 5), (cx, cy + 3)], lw=0.45, color='#333333', nc=True)
        s.rect(cx - 3, cy - 3, 6, 6, lw=0.4, fill='#ffffff')
        s.poly([(cx, cy - 3), (cx, cy - 5)], lw=0.45, color='#333333', nc=True)
    elif key == 'barb':
        s.poly([(cx - 14, cy), (cx - 3, cy)], lw=1.2, nc=True)
        s.poly([(cx - 3, cy - 2.4), (cx - 3, cy + 2.4), (cx + 2, cy + 1.4), (cx + 2, cy - 1.4)], lw=0.35, closed=True, fill='#ffffff')
        s.poly([(cx + 2, cy), (cx + 14, cy)], lw=0.9, color='#333333', dash='dash', nc=True)
    elif key == 'stub':
        s.poly([(cx - 14, cy), (cx + 6, cy)], lw=0.45, color='#333333', nc=True); s.stub_arrow(cx + 6, cy, 'right')
    elif key == 'q':
        s.text(cx, cy + 1, 'L = ?', 2.6, 'middle', color=RED)
    elif key == 'dim':
        s.dim(cx - 12, cy + 2, cx + 12, cy + 2, 0, '600', 2.2)
    elif key == 'mesh':
        s.rect(cx - 5, cy - 4.5, 10, 9, lw=0.6, fill='#f7f7f7'); s.line(cx - 5, cy + 2, cx + 6, cy + 3, lw=0.25, dash='dot')
    elif key == 'dip':
        s.rect(cx - 7, cy - 3.5, 14, 8, lw=0.5, fill='#f4f8fb'); s.line(cx - 6, cy + 1, cx + 6, cy + 1, lw=0.2, dash='dash', color=BLUE)
        s.poly([(cx - 2, cy - 5), (cx - 2, cy + 3.5)], lw=0.45, color='#333333', nc=True)
    elif key == 'hop':
        s.poly([(cx - 12, cy), (cx - 2.4, cy), (cx - 1.1, cy - 2.2), (cx + 1.1, cy - 2.2), (cx + 2.4, cy), (cx + 12, cy)], lw=0.45, color='#333333', nc=True)
        s.poly([(cx, cy - 4.5), (cx, cy + 4.5)], lw=0.45, color='#333333', nc=True)
    elif key == 'xvalve':
        s.poly([(cx - 14, cy), (cx - 3, cy)], lw=0.8, nc=True); s.poly([(cx + 3, cy), (cx + 14, cy)], lw=0.8, nc=True)
        s.circle(cx, cy, 3, lw=0.4, fill='#ffffff'); s.poly([(cx, cy + 3), (cx, cy + 8)], lw=0.8, nc=True)


def drawings_legend(sheet_no, n_sheets, code):
    s = Sheet(f'{sheet_no} Условные обозначения', 420.0, 297.0)
    s.frame('Условные обозначения', code, sheet_no, n_sheets)
    s.text(25, 14, 'УСЛОВНЫЕ ОБОЗНАЧЕНИЯ МОНТАЖНЫХ ЧЕРТЕЖЕЙ (листы 1–8)', 3.2, bold=True)
    items = [('pipe', 'Кламповый трубопровод', ['патрубки, тройники, отводы', 'нерж. AISI 316L']),
             ('tube', 'Трубка PTFE', ['10×12 (газ) или 6×8 (аргон)', 'на обжимных фитингах']),
             ('hose', 'Гибкий рукав', ['PTFE в оплётке (продукт)', 'или EPDM (вода, теплоноситель)']),
             ('clamp', 'Кламповое соединение', ['две ферулы + хомут + прокладка;', 'номер — строка ведомости, лист 8']),
             ('valve', 'Кран шаровой', ['кламп DN15 или ¼″ обжим;', 'короткая черта — рукоятка']),
             ('check', 'Обратный клапан', ['остриё и черта — по потоку;', 'назад не пропускает']),
             ('gauge', 'Манометр', ['PI — мановакуумметр', 'на отводе линии']),
             ('reducer', 'Переход концентрический', ['с большего DN на меньший,', 'напр. DN38 → DN15']),
             ('psv', 'Предохранительный клапан', ['PSV: сброс при превышении', 'уставки, выход трубкой']),
             ('barb', 'Штуцер-ёлочка', ['переход с клампа', 'на шланг']),
             ('xvalve', 'Кран трёхходовой', ['X1, X2: переключение', 'теплоносителя']),
             ('stub', 'Продолжение линии', ['на другом листе или', 'выход в вытяжку']),
             ('dip', 'Погружная трубка', ['вход газа или жидкости', 'ниже уровня в аппарате']),
             ('mesh', 'Сетчатая прокладка', ['пунктир — опора засыпки', 'в колонне']),
             ('hop', 'Пересечение без соединения', ['мостик — линии', 'не соединены']),
             ('ground', 'Шина заземления', ['все аппараты, насосы,', 'канистры и бочки']),
             ('dim', 'Размер', ['в миллиметрах', '']),
             ('q', 'Красный текст с «?»', ['размер или параметр', 'замерить / уточнить'])]
    half = (len(items) + 1) // 2
    _table(s, items[:half], 25, 22, _draw_sym, widths=(30, 50, 110))
    _table(s, items[half:], 222, 22, _draw_sym, widths=(30, 50, 110))
    s.nocheck.update(range(len(s.items)))     # образцы символов, а не трубопровод
    s.text(25, 250, 'Позиции (R-1, G-1, P-2, SV-1 …) — перечень позиций на листе 1; размеры клампов по DN: DN15 — ферула 25 мм, DN25 и DN38 — 50,5, DN65 — 91.', 2.2, color=GREY)
    return s
