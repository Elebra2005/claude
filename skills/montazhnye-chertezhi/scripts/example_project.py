"""Пример проекта монтажных чертежей — стартовый шаблон. Скопируйте в папку проекта и правьте.

Запуск:  python3 example_project.py [папка_вывода]
Выход:   list-N.svg на каждый лист, chertezhi.vsdx (все листы), sborka.vsdx и sborka.svg (чистовой лист сборки)
Проверка: python3 check.py example_project.py   (должно быть «ИТОГО замечаний: 0»)

Координаты в мм, ось Y вниз. A3 = 420×297, A1 = 841×594.
"""
import os, re, sys, zipfile, tempfile, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import draw
from draw import Sheet, to_svg, to_vsdx, INK, GREY, BLUE
from place import place_sizes

draw.ORG = 'ООО «Пример»'                     # штамп: организация
draw.PROJECT = 'Обвязка ёмкости V-1'          # штамп: строка проекта
CODE = 'ПР.001-00.00'
N_SHEETS = 3

# ---------------------------------------------------------------- ведомость соединений
JOINTS = []            # (номер, лист, место, размер, прокладка)


def J(sh, sheet_no, x, y, orient, size, gasket, where, side=1, w=None):
    """Новое кламповое соединение: рисует клампы, присваивает номер <лист><NN>, пишет строку в ведомость.
    size начинается с ферулы (K25, K50,5 …) — по ней считаются хомуты и прокладки."""
    n = f'{sheet_no}{sum(1 for j in JOINTS if j[1] == sheet_no) + 1:02d}'
    JOINTS.append((n, sheet_no, where, size, gasket))
    sh.clamp(x, y, orient, n, side, w, size.split()[0])
    return n


def JR(sh, x, y, orient, where, side=1, w=None):
    """То же соединение на другом листе (сборка, вид): номер берётся по тексту `where`, в ведомость не пишется."""
    n, size = next((j[0], j[3]) for j in JOINTS if j[2] == where)
    sh.clamp(x, y, orient, n, side, w, size.split()[0])
    return n


def pipe(sh, pts, lw=1.6):      # кламповый трубопровод (толстая линия)
    sh.poly(pts, lw=lw)


def hose(sh, pts):               # гибкий рукав — штрих
    sh.poly(pts, lw=0.9, color='#333333', dash='dash')


def tube(sh, pts):               # трубка PTFE / нерж. малого диаметра
    sh.poly(pts, lw=0.45, color='#333333')


# ---------------------------------------------------------------- геометрия узла (общая для детального листа и сборки)
def outlet_node(s, x, y0, ref):
    """Ёмкость → кран → насос. ref=None — детальный лист (J), иначе функция-ссылка (JR) для сборки."""
    mk = (lambda *a, **k: J(s, 1, *a, **k)) if ref is None else (lambda x_, y_, o, size, g, where, **k: ref(s, x_, y_, o, where, **k))
    s.rect(x - 30, y0 - 70, 60, 70, lw=0.7, fill='#ffffff'); s.text(x - 28, y0 - 64, 'V-1', 3.0, bold=True)
    s.vessels = getattr(s, 'vessels', []) + [(x - 30, y0 - 70, x + 30, y0)]
    pipe(s, [(x, y0), (x, y0 + 6.2)])
    mk(x, y0 + 8, 'v', 'K50,5', 'PTFE', 'V-1 низ → переход 50,5/½″', side=-1)
    s.reducer(x, y0 + 9.8, 'v', 6.4, 3.2, 6)
    pipe(s, [(x, y0 + 15.8), (x, y0 + 18.2)], lw=1.2)
    mk(x, y0 + 20, 'v', 'K25', 'PTFE', 'переход → кран V-2', side=-1)
    pipe(s, [(x, y0 + 21.8), (x, y0 + 34.2)], lw=1.2)
    s.ball_valve(x, y0 + 28, 'v'); s.text(x + 5, y0 + 29, 'V-2', 2.2, bold=True)
    mk(x, y0 + 36, 'v', 'K25', 'PTFE', 'кран V-2 → рукав на P-1', side=-1)
    hose(s, [(x, y0 + 37.8), (x, y0 + 45), (x + 48.2, y0 + 45)])
    mk(x + 50, y0 + 45, 'h', 'K25', 'PTFE', 'рукав → P-1 вход', side=1)
    pipe(s, [(x + 51.8, y0 + 45), (x + 56, y0 + 45)], lw=1.2)
    s.rect(x + 56, y0 + 37, 18, 16, lw=0.6, fill='#f2f2f2'); s.text(x + 65, y0 + 46, 'P-1', 2.6, 'middle', bold=True)
    pipe(s, [(x + 74, y0 + 45), (x + 78.2, y0 + 45)], lw=1.2)
    mk(x + 80, y0 + 45, 'h', 'K25', 'PTFE', 'P-1 выход → линия', side=1)
    pipe(s, [(x + 81.8, y0 + 45), (x + 100, y0 + 45)], lw=1.2); s.stub_arrow(x + 100, y0 + 45, 'right')
    s.text(x + 90, y0 + 51, 'на нутч', 1.9, 'middle')


# ---------------------------------------------------------------- листы
def sheet_detail():
    s = Sheet('1 Узел выгрузки V-1')
    s.frame('Узел выгрузки V-1', CODE + '.01', 1, N_SHEETS)
    s.text(25, 13, 'УЗЕЛ ВЫГРУЗКИ V-1 → P-1, б/м', 3.0, bold=True)
    outlet_node(s, 120, 120, None)
    s.text(120 - 30, 112 + 60, 'H слива = ?', 2.2)            # «?» → красным: замерить по месту
    return s


def sheet_ledger():
    s = Sheet('2 Ведомость соединений')
    s.frame('Ведомость кламповых соединений', CODE + '.02', 2, N_SHEETS)
    s.text(25, 13, 'ВЕДОМОСТЬ КЛАМПОВЫХ СОЕДИНЕНИЙ', 3.0, bold=True)
    rows = [['№', 'Л.', 'Место', 'Размер', 'Прокл.']] + [[n, str(sh), w, sz, g] for n, sh, w, sz, g in JOINTS]
    s.table(24, 17, [9, 6, 118, 25, 13], rows, rowh=4.6, size=1.85)
    cnt = collections.Counter((sz.split()[0], g) for _, _, _, sz, g in JOINTS)
    y0 = 17 + 4.6 * len(rows) + 10
    s.text(24, y0, 'СВОДКА: хомуты и прокладки = по схеме + 2 шт. каждого размера', 2.6, bold=True)
    srows = [['Ферула', 'Соед.', 'Хомутов', 'PTFE', 'EPDM']]
    for fer in sorted({k[0] for k in cnt}):
        pt, ep = cnt[(fer, 'PTFE')], cnt[(fer, 'EPDM')]
        srows.append([fer, str(pt + ep), str(pt + ep + 2), str(pt + 2) if pt else '—', str(ep + 2) if ep else '—'])
    s.table(24, y0 + 2, [18, 14, 18, 14, 14], srows, rowh=4.6, size=1.9)
    return s


def sheet_assembly(clean=False):
    """Сборка: те же соединения через JR. clean=True — чистовой лист без рамки, заголовков, ссылок «(лист N)» и «?»."""
    s = Sheet('3 Сборка', 420.0, 297.0)
    if not clean:
        s.frame('Установка в сборе', CODE + '.03', 3, N_SHEETS)
        s.text(25, 13, 'УСТАНОВКА В СБОРЕ (лист 1 — узел выгрузки)', 3.0, bold=True)
    outlet_node(s, 160, 140, JR)
    return s


def clean_sheet(sh):
    """Убрать красные «?» и ссылки «(лист N)». Удалённые подписи становятся пустыми — индексы символов не сдвигаются."""
    for i, it in enumerate(sh.items):
        if it[0] == 'text':
            s = '' if it[7] == draw.RED else re.sub(r'\s*\(лист[^)]*\)', '', it[3]).strip()
            sh.items[i] = it[:3] + (s,) + it[4:]
    return sh


def build():
    JOINTS.clear()
    sheets = [sheet_detail(), sheet_ledger(), sheet_assembly()]
    for sh in sheets:
        place_sizes(sh)            # подписи размеров ферул у номеров соединений — в свободное место
    return sheets


def main(outdir='out'):
    os.makedirs(outdir, exist_ok=True)
    sheets = build()
    for i, sh in enumerate(sheets, 1):
        open(os.path.join(outdir, f'list-{i}.svg'), 'w', encoding='utf-8').write(to_svg(sh))
    tpl = tempfile.mkdtemp()
    with zipfile.ZipFile(os.path.join(HERE, '..', 'assets', 'visio-template.vsdx')) as z:
        z.extractall(tpl)
    to_vsdx(sheets, tpl, os.path.join(outdir, 'chertezhi.vsdx'))
    sb = sheet_assembly(clean=True); place_sizes(sb); clean_sheet(sb)
    open(os.path.join(outdir, 'sborka.svg'), 'w', encoding='utf-8').write(to_svg(sb))
    to_vsdx([sb], tpl, os.path.join(outdir, 'sborka.vsdx'))
    print('листов:', len(sheets), ' соединений:', len(JOINTS), ' →', outdir)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'out')
