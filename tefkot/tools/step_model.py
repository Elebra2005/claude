"""STEP-модель установки ТЕФКОТ 770 на реакторе Wiggens 50 л.

Система координат: мм, Z вверх, начало — пол под осью реактора.
−Y — фронт (сторона оператора), +X — вправо (к чиллеру), +Y — к колонне рамы.

Размеры реактора и рамы — по чертежам Wiggens 8813650C-M1 (реактор и рама),
остальное — оценки (см. 3d/README.md, список «что замерить»).

Запуск:  python3 tools/step_model.py   →  3d/tefkot-770-ustanovka.step (+ .glb)
"""
import math
import os
import cadquery as cq
from cadquery import Vector as V, Color

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', '3d')

C = {
    'steel': Color(0.78, 0.80, 0.83), 'dark': Color(0.30, 0.32, 0.35), 'frame': Color(0.55, 0.57, 0.60),
    'ptfe': Color(0.96, 0.96, 0.94), 'argon': Color(0.15, 0.40, 0.80), 'vent': Color(0.50, 0.30, 0.65),
    'gas': Color(0.95, 0.55, 0.10), 'prod': Color(0.20, 0.55, 0.25), 'epdm': Color(0.08, 0.08, 0.08),
    'cool': Color(0.05, 0.55, 0.55), 'glass': Color(0.70, 0.88, 0.95, 0.45), 'pump': Color(0.25, 0.25, 0.28),
    'white': Color(0.93, 0.93, 0.93), 'red': Color(0.80, 0.15, 0.15), 'yellow': Color(0.95, 0.80, 0.10),
    'blue': Color(0.20, 0.35, 0.70), 'sieve': Color(0.85, 0.75, 0.55), 'poly': Color(0.90, 0.90, 0.80, 0.8),
}

ROOT = cq.Assembly(name='TEFKOT-770')
GROUPS = {}
_names = {}


def add(group, name, shape, color):
    if isinstance(shape, (list, tuple)):
        shape = cq.Compound.makeCompound(list(shape))
    g = GROUPS.get(group)
    if g is None:
        g = GROUPS[group] = cq.Assembly(name=group)
    k = _names.get((group, name), 0)
    _names[(group, name)] = k + 1
    g.add(shape, name=name if not k else f'{name}_{k}', color=C[color])


# ---------------------------------------------------------------- примитивы
def P(*a):
    return V(*a)


def cyl(p0, p1, d):
    p0, p1 = V(*p0), V(*p1)
    v = p1 - p0
    return cq.Solid.makeCylinder(d / 2, v.Length, p0, v.normalized())


def cone(p0, p1, d0, d1):
    p0, p1 = V(*p0), V(*p1)
    v = p1 - p0
    return cq.Solid.makeCone(d0 / 2, d1 / 2, v.Length, p0, v.normalized())


def box(x0, y0, z0, x1, y1, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cbox(c, sx, sy, sz):
    return box(c[0] - sx / 2, c[1] - sy / 2, c[2] - sz / 2, c[0] + sx / 2, c[1] + sy / 2, c[2] + sz / 2)


def sph(p, d):
    return cq.Solid.makeSphere(d / 2, V(*p), angleDegrees1=-90, angleDegrees2=90)


def run(pts, d, bend=True):
    """Трубопровод по ломаной: цилиндры + сферы в изломах."""
    parts = [cyl(a, b, d) for a, b in zip(pts, pts[1:]) if (V(*a) - V(*b)).Length > 0.01]
    if bend:
        parts += [sph(p, d) for p in pts[1:-1]]
    return parts


def revolve(profile, at=(0, 0, 0)):
    pr = [profile[0]]
    for q in profile[1:]:
        if abs(q[0] - pr[-1][0]) + abs(q[1] - pr[-1][1]) > 1e-6:
            pr.append(q)
    s = cq.Workplane('XZ').polyline(pr).close().revolve(360, (0, 0, 0), (0, 1, 0)).val()
    return s.translate(V(*at))


def unit(v):
    v = V(*v)
    return v.normalized()


def clampj(p, d, dferr):
    """Кламповое соединение: две ферулы + хомут; d — направление оси."""
    p, u = V(*p), unit(d)
    return [cyl(p - u * 3, p + u * 3, dferr), cyl(p - u * 7, p + u * 7, dferr + 10)]


def ball_valve(p, d, dn, lever=(0, 0, 1), L=None):
    """Шаровой кран: корпус вдоль d, рычаг по направлению lever."""
    p, u, w = V(*p), unit(d), unit(lever)
    L = L or dn * 2.6
    parts = [cyl(p - u * (L / 2), p + u * (L / 2), dn * 1.15), sph(p, dn * 1.7)]
    stem_top = p + w * (dn * 1.2)
    parts.append(cyl(p, stem_top, 8))
    tip = stem_top + u * (dn * 3.2)
    parts.append(cyl(stem_top, tip, 6))
    return parts


def gauge(p, face, dial=63):
    p, f = V(*p), unit(face)
    return [cyl(p - f * 12, p + f * 12, dial), cyl(p + f * 12, p + f * 14, dial - 6)]


def check_valve(p, d, dn):
    p, u = V(*p), unit(d)
    return [cyl(p - u * dn * 1.6, p + u * dn * 1.6, dn * 1.1), cyl(p - u * dn * 0.8, p + u * dn * 0.8, dn * 1.7)]


def pump(c, name, group):
    """Мембранный пневмонасос (габарит 1/2″-класса — уточнить модель)."""
    x, y, z = c
    parts = [box(x - 110, y - 70, z, x + 110, y + 70, z + 25)]
    parts.append(cyl((x - 85, y, z + 140), (x - 45, y, z + 140), 190))                   # камеры
    parts.append(cyl((x + 45, y, z + 140), (x + 85, y, z + 140), 190))
    parts.append(cbox((x, y, z + 140), 90, 110, 150))                                    # пневмоблок
    parts += run([(x - 65, y, z + 40), (x - 65, y, z + 25)], 30)
    parts.append(cbox((x, y, z + 32), 200, 40, 30))                                      # всасывающий коллектор
    parts.append(cbox((x, y, z + 250), 200, 40, 30))                                     # нагнетательный
    add(group, name, parts, 'pump')
    return (x, y, z + 32), (x, y, z + 250)       # всас (низ), нагнетание (верх)


# ---------------------------------------------------------------- реактор R-1
def dome_z(r):                       # высота крышки над плоскостью фланца на радиусе r
    return 1115 + math.sqrt(450 ** 2 - r ** 2) - math.sqrt(450 ** 2 - 203 ** 2)


def dish(rc, zc, R, n=14, down=True):
    zc0 = zc + math.sqrt(R * R - rc * rc)
    return [(rc * (1 - i / n), zc0 - math.sqrt(R * R - (rc * (1 - i / n)) ** 2)) for i in range(n + 1)]


BODY_R, JACK_R = 203, 278
Z_FL = 1100                          # разъём корпус/крышка
Z_CYL = 640                          # низ цилиндра корпуса
Z_JTOP = Z_FL - 89                   # верх рубашки (89 по чертежу)
Z_TRUN = 850                         # ось цапф (по чертежу рамы ≈ 850)

NOZ = {   # метка: (угол от +X против часовой, радиус, DN, наше обозначение)
    'N3': (60, 115, 25, 'P1'), 'N4': (0, 115, 25, 'P2'), 'N5': (-60, 115, 25, 'P3'),
    'N1': (180, 160, 25, 'P4'), 'N2': (120, 115, 8, 'T1'), 'N6': (-120, 115, 8, 'T2'),
}
Z_NOZ = 1200                         # торец штуцеров DN25 (оценка: ~50 мм над крышкой)


def nxy(tag):
    a, r = math.radians(NOZ[tag][0]), NOZ[tag][1]
    return r * math.cos(a), r * math.sin(a)


def reactor():
    g = 'R-1_Wiggens_50L'
    prof = [(0, 0)] + dish(BODY_R, Z_CYL, 400)[::-1][1:] + [(BODY_R, Z_FL - 15), (225, Z_FL - 15), (225, Z_FL), (0, Z_FL)]
    prof[0] = (0, dish(BODY_R, Z_CYL, 400)[-1][1])
    body = revolve(prof)
    jprof = [(0, dish(JACK_R, 620, 550)[-1][1])] + dish(JACK_R, 620, 550)[::-1][1:] + [(JACK_R, Z_JTOP), (0, Z_JTOP)]
    jacket = revolve(jprof).cut(body)
    add(g, 'body', body, 'steel')
    add(g, 'jacket', jacket, 'steel')
    lid = [(0, Z_FL), (225, Z_FL), (225, Z_FL + 15), (BODY_R, Z_FL + 15)] + \
          [(r, dome_z(r)) for r in range(BODY_R, -1, -29)] + [(0, dome_z(0))]
    add(g, 'lid', revolve(lid), 'steel')
    # откидные болты (8 шт.)
    bolts = []
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        c = (240 * math.cos(a), 240 * math.sin(a))
        bolts.append(cbox((c[0], c[1], Z_FL), 24, 24, 50))
        bolts.append(cyl((c[0], c[1], Z_FL + 25), (c[0], c[1], Z_FL + 45), 30))
    add(g, 'swing_bolts', bolts, 'dark')
    # штуцеры крышки
    for tag, (ang, r, dn, ours) in NOZ.items():
        x, y = nxy(tag)
        zb = dome_z(r) - 5
        if dn == 25:
            add(g, f'{tag}_DN25_{ours}', [cyl((x, y, zb), (x, y, Z_NOZ - 3), 33.7), cyl((x, y, Z_NOZ - 6), (x, y, Z_NOZ), 50.5)], 'steel')
        else:
            add(g, f'{tag}_8mm_{ours}', [cyl((x, y, zb), (x, y, 1180), 14)], 'steel')
    # мешалка: штуцер M DN133, фонарь, мотор WB1800-C, вал Ø26, лопастная мешалка
    zm = dome_z(0)
    add(g, 'M_DN133', [cyl((0, 0, zm - 5), (0, 0, zm + 15), 140), cyl((0, 0, zm + 15), (0, 0, zm + 30), 170)], 'steel')
    add(g, 'lantern', [cyl((0, 0, zm + 30), (0, 0, 1420), 130)], 'steel')
    add(g, 'motor_WB1800-C', [cyl((0, 0, 1420), (0, 0, 1440), 150), cyl((0, 0, 1440), (0, 0, 1620), 100)], 'dark')
    shaft = [cyl((0, 0, 660), (0, 0, zm), 26)]
    for k in range(3):
        a = math.radians(120 * k)
        blade = cbox((0, 0, 0), 85, 32, 5).rotate(V(0, 0, 0), V(1, 0, 0), 30)
        blade = blade.translate(V(55, 0, 670)).rotate(V(0, 0, 0), V(0, 0, 1), 120 * k)
        shaft.append(blade)
    shaft.append(cyl((0, 0, 655), (0, 0, 690), 40))
    add(g, 'agitator', shaft, 'steel')
    # рубашка: N7 выход (сзади, верх), N8 вход (фронт, низ) — ориентацию проверить
    add(g, 'N7_jacket_out', [cyl((0, JACK_R - 5, 800), (0, JACK_R + 100, 800), 33.7), cyl((0, JACK_R + 94, 800), (0, JACK_R + 100, 800), 50.5)], 'steel')
    add(g, 'N8_jacket_in', [cyl((0, -JACK_R + 5, 776), (0, -JACK_R - 100, 776), 33.7), cyl((0, -JACK_R - 94, 776), (0, -JACK_R - 100, 776), 50.5)], 'steel')
    # цапфы и редуктор опрокидывания
    add(g, 'trunnions', [cyl((-JACK_R + 5, 0, Z_TRUN), (-400, 0, Z_TRUN), 60), cyl((JACK_R - 5, 0, Z_TRUN), (400, 0, Z_TRUN), 60)], 'steel')
    add(g, 'tilt_gearbox', [box(-612, -100, 750, -400, 100, 960)], 'dark')
    # нижний слив L DN38 → BV-1 (Swagelok)
    zap = dish(BODY_R, Z_CYL, 400)[-1][1]
    add(g, 'L_DN38', [cyl((0, 0, zap + 5), (0, 0, 505), 42), cyl((0, 0, 499), (0, 0, 505), 50.5)], 'steel')
    return zap


# ---------------------------------------------------------------- рама Wiggens
def frame():
    g = 'Frame_Wiggens'
    t = 40
    parts = []
    xs, y_f, y_b = (-380, 380), -260, 500
    for x in xs:
        for y in (y_f, y_b):
            parts.append(cbox((x, y, 590), t, t, 940))
            parts.append(cbox((x, y, 60), 70, 70, 120))            # колёса
    for z in (150, 1055):
        parts.append(cbox((0, y_f, z), 800, t, t)); parts.append(cbox((0, y_b, z), 800, t, t))
        for x in xs:
            parts.append(cbox((x, (y_f + y_b) / 2, z), t, y_b - y_f, t))
    # задняя колонна до 2092,5
    for x in xs:
        parts.append(cbox((x, 700, 1106), t, t, 1972))
        parts.append(cbox((x, 700, 60), 70, 70, 120))
    parts.append(cbox((0, 700, 2072), 800, t, t))
    parts.append(cbox((0, 700, 150), 800, t, t))
    for x in xs:
        parts.append(cbox((x, 600, 150), t, 200, t)); parts.append(cbox((x, 600, 1055), t, 200, t))
    parts.append(box(-400, 718, 150, 400, 723, 2092))            # задняя панель
    # кронштейн мотора: две консоли и поперечина с хомутом
    for x in (-160, 160):
        parts.append(box(x - 15, 0, 1285, x + 15, 700, 1315))
    parts.append(box(-175, -15, 1285, 175, 15, 1315))
    parts.append(cyl((0, 0, 1285), (0, 0, 1315), 170).cut(cyl((0, 0, 1280), (0, 0, 1320), 132)))
    # опоры цапф
    for x in (-400, 400):
        parts.append(cbox((x, 0, (Z_TRUN + 1055) / 2 - 10), 60, 80, 1055 - Z_TRUN + 60))
    add(g, 'frame', parts, 'frame')
    # тележка управления 540×540×1055
    c = []
    for x in (440, 940):
        for y in (-260, 260):
            c.append(cbox((x, y, 590), t, t, 940)); c.append(cbox((x, y, 60), 70, 70, 120))
    c.append(box(420, -280, 1055, 960, 280, 1070))
    c.append(box(420, -280, 150, 960, 280, 165))
    add(g, 'control_cart', c, 'frame')
    add(g, 'control_box', [box(620, -60, 1070, 760, 60, 1330)], 'white')


# ---------------------------------------------------------------- E-1 и гребёнка
def condenser_and_manifold():
    g = 'E-1_condenser'
    x, y = nxy('N3')
    z0 = Z_NOZ
    parts = clampj((x, y, z0), (0, 0, 1), 50.5)
    parts.append(cone((x, y, z0 + 3), (x, y, z0 + 60), 33.7, 76.2))
    parts.append(cyl((x, y, z0 + 60), (x, y, z0 + 560), 76.2))
    parts += clampj((x, y, z0 + 563), (0, 0, 1), 91)
    parts.append(cyl((x, y, z0 + 566), (x, y, z0 + 578), 91))
    add(g, 'E-1_shell_3in_L500', parts, 'steel')
    add(g, 'E-1_coil_stubs', [cyl((x - 15, y, z0 + 578), (x - 15, y, z0 + 640), 12), cyl((x + 15, y, z0 + 578), (x + 15, y, z0 + 640), 12)], 'steel')
    zg = z0 + 520                               # отвод газа КЛ-25, в сторону +X
    add(g, 'E-1_gas_outlet', [cyl((x + 30, y, zg), (x + 90, y, zg), 25.4)] + clampj((x + 90, y, zg), (1, 0, 0), 50.5), 'steel')
    # изоляция
    add(g, 'E-1_insulation', [cyl((x, y, z0 + 70), (x, y, z0 + 500), 110).cut(cyl((x, y, z0 + 60), (x, y, z0 + 510), 78))], 'epdm')

    # ---- гребёнка безопасности: коллектор 1″ на уровне отвода E-1
    g = 'Safety_manifold'
    x0 = x + 97
    xe = 900
    zc = zg
    add(g, 'collector_1in', [cyl((x0, y, zc), (xe, y, zc), 25.4)], 'steel')
    add(g, 'collector_end_cap', clampj((xe, y, zc), (1, 0, 0), 50.5), 'steel')
    # PI-4 и тройник аргона/вакуума
    add(g, 'PI-4_tee', [cyl((230, y, zc), (230, y, zc + 60), 25.4)] + clampj((230, y, zc + 60), (0, 0, 1), 50.5), 'steel')
    add(g, 'PI-4_0-250mbar', gauge((230, y - 20, zc + 110), (0, -1, 0), 100) + [cyl((230, y, zc + 63), (230, y, zc + 110), 12)], 'white')
    add(g, 'VV-1_tee', [cyl((170, y, zc), (170, y, zc + 60), 25.4)] + clampj((170, y, zc + 60), (0, 0, 1), 50.5), 'steel')
    add(g, 'VV-1', ball_valve((170, y, zc + 105), (0, 0, 1), 25.4, lever=(0, -1, 0)), 'steel')
    devices = [('SV-1', 'PCV-1_spunding', 340), ('SV-2', 'NRV-1_100mbar', 480), ('SV-3', 'PSV-1_200mbar', 620), ('SV-4', 'NRV-2_KF25', 760)]
    zv = zc - 330                                # коллектор сбросов
    for sv, dev, xx in devices:
        add(g, f'{sv}_tee', [cyl((xx, y, zc), (xx, y, zc - 50), 25.4)] + clampj((xx, y, zc - 50), (0, 0, 1), 50.5), 'steel')
        add(g, sv, ball_valve((xx, y, zc - 100), (0, 0, 1), 25.4, lever=(0, -1, 0)), 'red' if sv == 'SV-3' else 'steel')
        add(g, f'{sv}_joint', clampj((xx, y, zc - 150), (0, 0, 1), 50.5), 'steel')
        if 'PCV' in dev:
            body = [cyl((xx, y, zc - 153), (xx, y, zc - 175), 25.4), cyl((xx, y, zc - 175), (xx, y, zc - 260), 60), cyl((xx, y, zc - 260), (xx, y, zc - 270), 25.4)]
        elif 'KF25' in dev:
            body = [cyl((xx, y, zc - 153), (xx, y, zc - 190), 25.4), cyl((xx, y, zc - 190), (xx, y, zc - 200), 40),
                    cyl((xx, y, zc - 200), (xx, y, zc - 240), 30), cyl((xx, y, zc - 240), (xx, y, zc - 250), 40), cyl((xx, y, zc - 250), (xx, y, zc - 270), 25.4)]
        else:
            body = [cyl((xx, y, zc - 153), (xx, y, zc - 165), 25.4), cyl((xx, y, zc - 165), (xx, y, zc - 255), 50), cyl((xx, y, zc - 255), (xx, y, zc - 270), 25.4)]
        add(g, dev, body, 'steel')
        add(g, f'{dev}_joint', clampj((xx, y, zc - 273), (0, 0, 1), 50.5), 'steel')
        add(g, f'{dev}_drop', [cyl((xx, y, zc - 276), (xx, y, zv), 25.4)], 'steel')
    add(g, 'vent_collector', [cyl((340 - 12.7, y, zv), (1000, y, zv), 25.4)], 'steel')
    # сброс → T-1 → BU-1 → S-1 (за тележкой, на полу)
    tx, ty = 1060, 520
    add(g, 'vent_hose_to_T-1', run([(1000, y, zv), (tx, y, zv), (tx, ty, zv), (tx, ty, 560)], 16), 'ptfe')
    add(g, 'T-1_buffer_4in_L300', [cyl((tx, ty, 200), (tx, ty, 500), 101.6), cyl((tx, ty, 500), (tx, ty, 515), 119), cyl((tx, ty, 185), (tx, ty, 200), 119), cyl((tx, ty, 515), (tx, ty, 560), 25.4)], 'steel')
    add(g, 'T-1_stand', [box(tx - 80, ty - 80, 0, tx + 80, ty + 80, 10), cyl((tx, ty, 10), (tx, ty, 185), 60)], 'dark')
    bx, by = 1200, 520
    add(g, 'BU-1_bubbler', [cyl((bx, by, 150), (bx, by, 450), 60)], 'glass')
    add(g, 'BU-1_stand', [box(bx - 60, by - 60, 0, bx + 60, by + 60, 10), cyl((bx, by, 10), (bx, by, 150), 40)], 'dark')
    add(g, 'T-1_to_BU-1', run([(tx + 30, ty, 480), (tx + 70, ty, 480), (tx + 70, ty, 520), (bx, by, 520), (bx, by, 450)], 8), 'ptfe')
    sx, sy = 1360, 540
    add(g, 'S-1_scrubber_20L', [box(sx - 120, sy - 120, 0, sx + 120, sy + 120, 380), cyl((sx, sy, 380), (sx, sy, 410), 50)], 'poly')
    add(g, 'BU-1_to_S-1', run([(bx, by, 450), (bx, by, 470), (bx + 60, by, 470), (sx, sy, 470), (sx, sy, 410)], 8), 'ptfe')
    return (x, y), zc, (tx, ty)


# ---------------------------------------------------------------- узлы P2, P3, P4, T1, T2
def lid_nodes():
    g = 'Lid_nodes'
    # P2: заглушка с термогильзой Ø8, L=500 (по 3D: при 15 л уровень ≈ z 730)
    x, y = nxy('N4')
    add(g, 'P2_joint', clampj((x, y, Z_NOZ), (0, 0, 1), 50.5), 'steel')
    add(g, 'P2_thermowell_8x500', [cyl((x, y, Z_NOZ + 3), (x, y, Z_NOZ + 8), 50.5), cyl((x, y, Z_NOZ + 3), (x, y, Z_NOZ - 500), 8)], 'steel')
    add(g, 'P2_Pt100_head', [cyl((x, y, Z_NOZ + 8), (x, y, Z_NOZ + 60), 22)], 'blue')
    # P3: кран V-P3, тройник с септой, заглушка с обжимом ¼″
    x, y = nxy('N5')
    parts = clampj((x, y, Z_NOZ), (0, 0, 1), 50.5)
    add(g, 'V-P3', ball_valve((x, y, Z_NOZ + 35), (0, 0, 1), 25.4, lever=(1, 0, 0), L=64), 'steel')
    parts += clampj((x, y, Z_NOZ + 70), (0, 0, 1), 50.5)
    parts.append(cyl((x, y, Z_NOZ + 73), (x, y, Z_NOZ + 150), 25.4))
    parts.append(cyl((x, y, Z_NOZ + 112), (x + 45, y, Z_NOZ + 112), 25.4))
    parts += clampj((x + 48, y, Z_NOZ + 112), (1, 0, 0), 50.5)
    parts += clampj((x, y, Z_NOZ + 153), (0, 0, 1), 50.5)
    parts.append(cyl((x, y, Z_NOZ + 156), (x, y, Z_NOZ + 162), 50.5))
    add(g, 'P3_tee_septum_cap', parts, 'steel')
    add(g, 'P3_dosing_tube', [cyl((x, y, Z_NOZ + 162), (x, y, 830), 6.35)], 'ptfe')
    p3_top = (x, y, Z_NOZ + 175)
    # P4: стояк Ar со смотровым фонарём
    x, y = nxy('N1')
    parts = clampj((x, y, Z_NOZ), (0, 0, 1), 50.5)
    parts.append(cyl((x, y, Z_NOZ + 3), (x, y, Z_NOZ + 30), 33.7))
    parts.append(cyl((x, y, Z_NOZ + 100), (x, y, Z_NOZ + 130), 33.7))
    parts += clampj((x, y, Z_NOZ + 133), (0, 0, 1), 50.5)
    parts.append(cyl((x, y, Z_NOZ + 136), (x, y, Z_NOZ + 142), 50.5))
    add(g, 'P4_stack', parts, 'steel')
    add(g, 'P4_sight_glass', [cyl((x, y, Z_NOZ + 30), (x, y, Z_NOZ + 100), 45)], 'glass')
    p4_top = (x, y, Z_NOZ + 142)
    # T1: манометр PI-1
    x, y = nxy('N2')
    add(g, 'PI-1', gauge((x, y - 15, 1225), (0, -1, 0), 63) + [cyl((x, y, 1180), (x, y, 1225), 8)], 'white')
    # T2: игольчатый вентиль + погружная трубка ¼″ до 40 мм от дна
    x, y = nxy('N6')
    add(g, 'T2_needle_valve', [cyl((x, y, 1180), (x, y, 1225), 18), cyl((x, y, 1210), (x - 30, y, 1210), 8), cyl((x - 30, y, 1203), (x - 30, y, 1217), 22)], 'steel')
    add(g, 'T2_dip_tube', [cyl((x, y, 1180), (x, y, 640), 6.35)], 'steel')
    return p3_top, p4_top, (x, y, 1225)


# ---------------------------------------------------------------- генератор G-1 и колонны
def generator(t2_top):
    g = 'Generator_G-1'
    gx, gy = -1400, -50
    add(g, 'W-2_scale_60kg', [box(gx - 260, gy - 260, 0, gx + 260, gy + 260, 70)], 'dark')
    tub = box(gx - 250, gy - 250, 70, gx + 250, gy + 250, 420).cut(box(gx - 240, gy - 240, 80, gx + 240, gy + 240, 430))
    add(g, 'ice_bath', tub, 'blue')
    add(g, 'G-1_Atmaler_BK-40', [cyl((gx, gy, 90), (gx, gy, 520), 360), cyl((gx, gy, 520), (gx, gy, 560), 300)], 'steel')
    add(g, 'G-1_fittings', [cyl((gx + 60, gy, 560), (gx + 60, gy, 620), 20), cyl((gx - 60, gy, 560), (gx - 60, gy, 600), 20)]
        + gauge((gx, gy - 80, 600), (0, -1, 0), 63), 'dark')
    # колонны на лабораторном штативе
    sx, sy = -1000, 150
    add(g, 'column_stand', [box(sx - 150, sy - 300, 0, sx + 150, sy + 300, 20), cyl((sx + 110, sy, 20), (sx + 110, sy, 1700), 16)], 'dark')
    cols = [('K-1_knockout_300', sy - 200, 300, 'steel'), ('C-1_3A_sieves_600', sy, 600, 'steel'), ('C-2_NaOH_600', sy + 200, 600, 'steel')]
    tops = []
    for name, cy_, L, col in cols:
        z0 = 850
        parts = [cyl((sx, cy_, z0), (sx, cy_, z0 + L), 76.2)]
        for zz in (z0, z0 + L):
            parts.append(cyl((sx, cy_, zz - 8), (sx, cy_, zz + 8), 101))
        parts.append(cone((sx, cy_, z0 - 8), (sx, cy_, z0 - 40), 91, 25.4))
        parts.append(cone((sx, cy_, z0 + L + 8), (sx, cy_, z0 + L + 40), 91, 25.4))
        add(g, name, parts, col)
        add(g, name + '_clamp_arm', [box(sx, cy_ - 10, z0 + L / 2 - 10, sx + 110, cy_ + 10, z0 + L / 2 + 10)], 'dark')
        tops.append(((sx, cy_, z0 - 40), (sx, cy_, z0 + L + 40)))
    # газовая линия ¼″ PTFE: G-1 → K-1 → C-1 → C-2 → NRV-3 → T2
    add(g, 'gas_G1_K1', run([(gx + 60, gy, 620), (gx + 60, gy, 700), (gx + 60, tops[0][0][1], 700), (sx, tops[0][0][1], 700), tops[0][0]], 6.35), 'gas')
    for a, b in ((0, 1), (1, 2)):
        ya, yb = tops[a][1][1], tops[b][0][1]
        add(g, f'gas_col{a}_col{b}', run([tops[a][1], (sx, ya, 1560 + 20 * a), (sx - 60 - 20 * a, ya, 1560 + 20 * a), (sx - 60 - 20 * a, ya, 780),
                                          (sx - 60 - 20 * a, yb, 780), (sx, yb, 780), tops[b][0]], 6.35), 'gas')
    zr = 1640
    route = [tops[2][1], (sx, tops[2][1][1], zr), (-600, tops[2][1][1], zr), (-600, t2_top[1], zr), (t2_top[0] - 30, t2_top[1], zr), (t2_top[0] - 30, t2_top[1], 1217)]
    add(g, 'gas_C2_to_T2', run(route, 6.35), 'gas')
    add(g, 'NRV-3', check_valve((-800, tops[2][1][1], zr), (1, 0, 0), 12), 'steel')
    # раствор метиламина: V-1 на W-1 → P-1 → G-1
    vx, vy = -1450, -650
    add(g, 'W-1_scale_30kg', [box(vx - 200, vy - 200, 0, vx + 200, vy + 200, 70)], 'dark')
    add(g, 'V-1_MeNH2_aq_canister', [box(vx - 115, vy - 150, 70, vx + 115, vy + 150, 400), cyl((vx, vy, 400), (vx, vy, 440), 50)], 'poly')
    suc, dis = pump((-1100, -650, 0), 'P-1_AODD', g)
    add(g, 'P-1_suction', run([(vx, vy, 440), (vx, vy, 470), (-1170, vy, 470), (-1170, vy, 32), (suc[0] - 100, vy, 32)], 10), 'ptfe')
    add(g, 'P-1_to_G-1', run([(dis[0] + 100, dis[1], dis[2]), (-1000, -650, 250), (-1000, -650, 680), (gx - 60, -650, 680), (gx - 60, gy, 680), (gx - 60, gy, 600)], 6.35), 'ptfe')
    add(g, 'P-1_needle_NRV', check_valve((-1000, -650, 450), (0, 0, 1), 10), 'steel')


# ---------------------------------------------------------------- аргон и вакуум
def argon_vacuum(p4_top, zc_e1, e1xy):
    g = 'Argon_Vacuum'
    ax, ay = -900, 620
    add(g, 'AR-1_cylinder_40L', [cyl((ax, ay, 0), (ax, ay, 1300), 230), sph((ax, ay, 1300), 230), cyl((ax, ay, 1400), (ax, ay, 1460), 40)], 'blue')
    add(g, 'PR-1_regulator', [cbox((ax, ay - 40, 1480), 60, 60, 60)] + gauge((ax - 50, ay - 40, 1510), (-1, 0, 0), 50) + gauge((ax + 50, ay - 40, 1510), (1, 0, 0), 50), 'steel')
    dx, dy, dz = -300, 660, 1500            # раздаточная гребёнка на колонне рамы
    add(g, 'PR-2_FI-1_PSV-2_panel', [box(dx - 250, dy + 30, dz - 120, dx + 250, dy + 45, dz + 120)], 'white')
    add(g, 'PR-2', [cbox((dx - 180, dy, dz), 50, 50, 50)] + gauge((dx - 180, dy - 35, dz + 50), (0, -1, 0), 50), 'steel')
    add(g, 'FI-1_rotameter', [cyl((dx - 100, dy, dz - 90), (dx - 100, dy, dz + 90), 30)], 'glass')
    add(g, 'Ar_distributor', [cyl((dx - 50, dy, dz), (dx + 200, dy, dz), 12)], 'steel')
    add(g, 'Ar_supply', run([(ax, ay - 40, 1510), (ax, ay - 40, 1580), (dx - 180, ay - 40, 1580), (dx - 180, dy, 1580), (dx - 180, dy, dz + 25)], 6.35), 'argon')
    add(g, 'Ar_PR2_FI1', run([(dx - 155, dy, dz), (dx - 100, dy, dz)], 6.35), 'argon')
    outs = {}
    for k, name in enumerate(('A1', 'A2', 'A3', 'A4')):
        xx = dx + 20 + 55 * k
        add(g, name, ball_valve((xx, dy, dz - 40), (0, 0, 1), 10, lever=(0, -1, 0), L=36), 'steel')
        add(g, name + '_drop', [cyl((xx, dy, dz), (xx, dy, dz - 22), 6.35)], 'argon')
        outs[name] = (xx, dy, dz - 58)
    # A1 → P4 (обратный клапан на крышке P4)
    x, y, z = p4_top
    add(g, 'A1_to_P4', run([outs['A1'], (outs['A1'][0], outs['A1'][1], 1400), (outs['A1'][0], y, 1400), (x, y, 1400), (x, y, z)], 6.35), 'argon')
    add(g, 'NRV_A1', check_valve((x, y, 1370), (0, 0, -1), 10), 'steel')
    # A2 → G-1 (продувка генератора)
    add(g, 'A2_to_G-1', run([outs['A2'], (outs['A2'][0], outs['A2'][1], 1380), (-1340, outs['A2'][1], 1380), (-1340, -50, 1380), (-1340, -50, 600)], 6.35), 'argon')
    add(g, 'G-1_Ar_inlet', [cyl((-1340, -50, 555), (-1340, -50, 600), 20)], 'dark')
    # вакуум: VV-1 на гребёнке → CT-1 → VP-1
    vx, vy = -650, 480
    add(g, 'VP-1_vacuum_pump', [box(vx - 175, vy - 125, 0, vx + 175, vy + 125, 260)], 'dark')
    add(g, 'CT-1_separator', [cyl((vx + 100, vy, 260), (vx + 100, vy, 460), 120)], 'glass')
    ex, ey = e1xy
    add(g, 'vacuum_line', run([(170, ey, zc_e1 + 128), (170, ey, 1900), (vx + 100, ey, 1900), (vx + 100, vy, 1900), (vx + 100, vy, 460)], 10), 'ptfe')
    return outs


# ---------------------------------------------------------------- дозирование D-1 / P-3
def dosing(p3_top, ar_outs):
    g = 'Dosing_D-1_P-3'
    tx, ty = -560, -560                     # тележка
    parts = []
    for x in (tx - 200, tx + 200):
        for y in (ty - 200, ty + 200):
            parts.append(cbox((x, y, 450), 25, 25, 900))
    parts += [box(tx - 215, ty - 215, 900, tx + 215, ty + 215, 915), box(tx - 215, ty - 215, 280, tx + 215, ty + 215, 295)]
    add(g, 'trolley', parts, 'frame')
    add(g, 'W-4_scale_15kg', [box(tx - 160, ty - 160, 915, tx + 160, ty + 160, 965)], 'dark')
    add(g, 'D-1_tripod', [cyl((tx + 90 * math.cos(math.radians(a)), ty + 90 * math.sin(math.radians(a)), 965),
                                (tx + 60 * math.cos(math.radians(a)), ty + 60 * math.sin(math.radians(a)), 1150), 12) for a in (90, 210, 330)]
        + [cyl((tx, ty, 1140), (tx, ty, 1150), 140).cut(cyl((tx, ty, 1130), (tx, ty, 1160), 104))], 'dark')
    zb, zt = 1150, 1550
    parts = [cyl((tx, ty, zb), (tx, ty, zt), 101.6)]
    for zz in (zb, zt):
        parts += clampj((tx, ty, zz), (0, 0, 1), 119)
    parts.append(cyl((tx, ty, zt + 3), (tx, ty, zt + 15), 119))
    parts.append(cone((tx, ty, zb - 3), (tx, ty, zb - 45), 119, 25.4))
    parts += clampj((tx, ty, zb - 48), (0, 0, 1), 50.5)
    parts.append(cyl((tx + 30, ty, zt + 15), (tx + 30, ty, zt + 50), 25.4))
    parts += clampj((tx + 30, ty, zt + 53), (0, 0, 1), 50.5)
    add(g, 'D-1_4in_L400_3L', parts, 'steel')
    add(g, 'D-1_fill_valve', ball_valve((tx + 30, ty, zt + 90), (0, 0, 1), 25.4, lever=(1, 0, 0), L=64), 'steel')
    add(g, 'V-D1', ball_valve((tx, ty, zb - 83), (0, 0, 1), 25.4, lever=(0, -1, 0), L=64), 'steel')
    suc, dis = pump((tx, ty, 295), 'P-3_AODD', g)
    add(g, 'D-1_to_P-3_hose', run([(tx, ty, zb - 118), (tx, ty, zb - 150), (tx - 150, ty, zb - 150), (tx - 150, ty, 330), (suc[0] - 100, ty, suc[2])], 16), 'ptfe')
    x, y, z = p3_top
    route = [(dis[0] + 100, dis[1], dis[2]), (tx + 160, ty, dis[2]), (tx + 160, ty, 1700), (x, ty, 1700), (x, y, 1700), (x, y, z)]
    add(g, 'P-3_to_P3_tube', run(route, 6.35), 'ptfe')
    add(g, 'FV-1_needle', [cbox((tx + 160, ty, 800), 30, 30, 50), cyl((tx + 160, ty, 800), (tx + 160, ty - 50, 800), 20)], 'steel')
    add(g, 'NRV-4', check_valve((tx + 160, ty, 1000), (0, 0, 1), 10), 'steel')
    # аргон A3 на крышку D-1
    a3 = ar_outs['A3']
    add(g, 'A3_to_D-1', run([a3, (a3[0], a3[1], 1760), (tx - 30, a3[1], 1760), (tx - 30, ty, 1760), (tx - 30, ty, zt + 15)], 6.35), 'argon')


# ---------------------------------------------------------------- выгрузка
def discharge(zap, ar_outs):
    g = 'Discharge_Filtration'
    # BV-1 Swagelok → тройник КЛ-50 с SP-1 → отвод → рукав на P-2
    add(g, 'BV-1_Swagelok', ball_valve((0, 0, 470), (0, 0, 1), 38, lever=(1, 0, 0), L=58), 'steel')
    parts = clampj((0, 0, 440), (0, 0, 1), 64)
    parts.append(cyl((0, 0, 437), (0, 0, 370), 50.8))
    parts.append(cyl((0, 0, 405), (70, 0, 405), 25.4))
    parts += clampj((73, 0, 405), (1, 0, 0), 50.5)
    parts += clampj((0, 0, 367), (0, 0, 1), 64)
    parts += run([(0, 0, 364), (0, 0, 330), (0, -60, 330)], 50.8)
    parts += clampj((0, -63, 330), (0, 1, 0), 64)
    add(g, 'tee_KL50_elbow', parts, 'steel')
    add(g, 'SP-1', ball_valve((115, 0, 405), (1, 0, 0), 25.4, lever=(0, 0, 1), L=64), 'steel')
    suc, dis = pump((300, -850, 0), 'P-2_AODD', g)
    add(g, 'BV-1_to_P-2_hose', run([(0, -66, 330), (0, -330, 330), (0, -600, 180), (0, -850, 32), (suc[0] - 100, -850, 32)], 32), 'ptfe')
    # нутч F-1 под аргоном
    fx, fy = 780, -900
    parts = [cyl((fx, fy, 520), (fx, fy, 870), 360), cone((fx, fy, 520), (fx, fy, 420), 360, 50), cyl((fx, fy, 420), (fx, fy, 380), 38)]
    parts.append(cyl((fx, fy, 870), (fx, fy, 890), 400))
    add(g, 'F-1_nutsche_DN350', parts, 'steel')
    add(g, 'F-1_stand', [cyl((fx + 170 * math.cos(math.radians(a)), fy + 170 * math.sin(math.radians(a)), 0),
                               (fx + 170 * math.cos(math.radians(a)), fy + 170 * math.sin(math.radians(a)), 560), 30) for a in (90, 210, 330)]
        + [cyl((fx, fy, 540), (fx, fy, 560), 420).cut(cyl((fx, fy, 530), (fx, fy, 570), 350))], 'dark')
    add(g, 'F-1_lid_fittings', [cyl((fx - 100, fy, 890), (fx - 100, fy, 940), 12), cyl((fx + 100, fy, 890), (fx + 100, fy, 930), 25.4),
                                cyl((fx, fy + 100, 890), (fx, fy + 100, 930), 12), cyl((fx, fy - 100, 890), (fx, fy - 100, 920), 12)], 'steel')
    add(g, 'PI-5', gauge((fx, fy - 100, 950), (0, -1, 0), 63), 'white')
    add(g, 'PSV-4_0.3bar', [cyl((fx + 100, fy, 930), (fx + 100, fy, 1010), 45)], 'steel')
    add(g, 'VV-2', ball_valve((fx, fy + 100, 960), (0, 0, 1), 10, lever=(1, 0, 0), L=36), 'steel')
    add(g, 'V-F1_NRV-5', ball_valve((fx - 100, fy, 980), (0, 0, 1), 10, lever=(-1, 0, 0), L=36) + check_valve((fx - 100, fy, 1050), (0, 0, -1), 10), 'steel')
    a4 = ar_outs['A4']
    add(g, 'A4_to_F-1', run([a4, (a4[0], a4[1], 1250), (a4[0], -150, 1250), (-300, -150, 1250), (-300, -1150, 1250), (fx - 100, -1150, 1250), (fx - 100, fy, 1250), (fx - 100, fy, 1080)], 6.35), 'argon')
    tx, ty = 1060, 520
    add(g, 'PSV-4_to_T-1', run([(fx + 100, fy, 1010), (fx + 100, fy, 1120), (1500, fy, 1120), (1500, ty, 1120), (tx + 60, ty, 1120), (tx + 60, ty, 420), (tx + 50, ty, 420)], 8), 'vent')
    add(g, 'P-2_to_F-1_hose', run([(dis[0] + 100, dis[1], dis[2]), (560, -850, 250), (560, -850, 800), (fx - 180, fy, 800)], 32), 'ptfe')
    # фильтр F-2 10″ и канистра на W-3
    f2x, f2y = 1150, -900
    add(g, 'F-2_10in_housing', [cyl((f2x, f2y, 300), (f2x, f2y, 620), 110), cyl((f2x, f2y, 620), (f2x, f2y, 660), 140)]
        + clampj((f2x - 70, f2y, 600), (1, 0, 0), 50.5) + clampj((f2x + 70, f2y, 600), (1, 0, 0), 50.5)
        + [cyl((f2x - 67, f2y, 600), (f2x - 55, f2y, 600), 25.4), cyl((f2x + 67, f2y, 600), (f2x + 55, f2y, 600), 25.4)], 'steel')
    add(g, 'F-2_stand', [box(f2x - 100, f2y - 100, 0, f2x + 100, f2y + 100, 10), cyl((f2x, f2y, 10), (f2x, f2y, 300), 50)], 'dark')
    add(g, 'F-1_to_F-2', run([(fx, fy, 380), (fx, fy, 330), (fx + 160, fy, 330), (f2x - 150, fy, 330), (f2x - 150, fy, 600), (f2x - 73, f2y, 600)], 25.4), 'ptfe')
    cx, cy = 1450, -900
    add(g, 'W-3_scale', [box(cx - 200, cy - 200, 0, cx + 200, cy + 200, 70)], 'dark')
    add(g, 'canister_20L', [box(cx - 130, cy - 150, 70, cx + 130, cy + 150, 440), cyl((cx, cy, 440), (cx, cy, 470), 50)], 'poly')
    add(g, 'F-2_to_canister', run([(f2x + 73, f2y, 600), (cx, f2y, 600), (cx, cy, 600), (cx, cy, 100)], 12), 'steel')


# ---------------------------------------------------------------- термостатирование
def thermostat(e1xy, zc_e1):
    g = 'Thermostat_TC-1'
    x0, x1, y0, y1 = 1100, 1600, -300, 300
    add(g, 'TC-1_chiller', [box(x0, y0, 0, x1, y1, 800)], 'white')
    add(g, 'TC-1_panel', [box(x0 + 50, y0 - 5, 600, x0 + 250, y0, 760)], 'dark')
    ex, ey = e1xy
    # рубашка: TC-1 → N8 (вход снизу, фронт); N7 (выход сверху, сзади) → TC-1
    add(g, 'hose_to_N8', run([(x0, -200, 300), (1000, -200, 300), (1000, -420, 300), (1000, -420, 776), (0, -420, 776), (0, -JACK_R - 100, 776)], 30), 'epdm')
    add(g, 'hose_from_N7', run([(0, JACK_R + 100, 800), (0, 420, 800), (1000, 420, 800), (1000, 420, 650), (1000, 200, 650), (x0, 200, 650)], 30), 'epdm')
    # E-1: TC-1 ↔ змеевик (с 3-ходовыми X1/X2 для IW-1 на стадии 7)
    zt = Z_NOZ + 640
    add(g, 'hose_to_E-1_in', run([(x1 - 100, -100, 800), (x1 - 100, -100, 1950), (ex - 15, -100, 1950), (ex - 15, ey, 1950), (ex - 15, ey, zt)], 16), 'epdm')
    add(g, 'hose_from_E-1_out', run([(ex + 15, ey, zt), (ex + 15, ey, 1990), (x1 - 150, ey, 1990), (x1 - 150, 100, 1990), (x1 - 150, 100, 800)], 16), 'epdm')
    add(g, 'X1_X2_3way', [cbox((x1 - 100, -100, 1300), 50, 50, 60), cbox((x1 - 150, 100, 1300), 50, 50, 60)], 'steel')


def glb_to_gltf_json(src, dst):
    """GLB → glTF с встроенным буфером (для просмотрщика: .glb артефакт не отдаёт)."""
    import base64, json, struct
    b = open(src, 'rb').read()
    length, off, js, binary = struct.unpack('<III', b[:12])[2], 12, None, None
    while off < length:
        cl, ct = struct.unpack('<II', b[off:off + 8])
        d = b[off + 8:off + 8 + cl]
        off += 8 + cl
        if ct == 0x4E4F534A:
            js = json.loads(d)
        elif ct == 0x004E4942:
            binary = d
    js['buffers'][0]['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(binary).decode()
    with open(dst, 'w') as f:
        json.dump(js, f, separators=(',', ':'))


def build():
    zap = reactor()
    frame()
    e1xy, zc, _ = condenser_and_manifold()
    p3_top, p4_top, t2_top = lid_nodes()
    generator(t2_top)
    outs = argon_vacuum(p4_top, zc, e1xy)
    dosing(p3_top, outs)
    discharge(zap, outs)
    thermostat(e1xy, zc)
    for name, g in GROUPS.items():
        ROOT.add(g, name=name)
    return ROOT


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    a = build()
    step = os.path.join(OUT, 'tefkot-770-ustanovka.step')
    a.save(step)
    try:
        a.save(os.path.join(OUT, 'tefkot-770-ustanovka.glb'), tolerance=0.8, angularTolerance=0.4)
        glb_to_gltf_json(os.path.join(OUT, 'tefkot-770-ustanovka.glb'), os.path.join(OUT, 'tefkot-770-ustanovka.gltf.json'))
    except Exception as e:                                           # noqa: BLE001
        print('glb:', e)
    print('ok', step, os.path.getsize(step) // 1024, 'KB')
