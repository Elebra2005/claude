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

RU = {'inlet_barb': 'Вход гребёнки: ёлочка → кламп DN15', 'hose_E-1_to_manifold': 'Шланг E-1 → гребёнка', 'collector': 'Коллектор DN15', 'collector_clamps': 'Хомуты коллектора DN15', 'PI-4_gauge': 'PI-4 мановакуумметр 0–250 мбар', 'AV-1': 'AV-1 кран кламп DN15 (аргон)', 'AV-1_G12_adapter': 'AV-1 переходник кламп → G½″ → ¼″', 'NRV-1': 'NRV-1 обратный DN15 ≤30 мбар', 'reducer_DN15_DN25': 'Переход DN15/DN25', 'SV-3_barb': 'SV-3 ёлочка', 'SV-3_hose_to_hood': 'SV-3 шланг на атмосферу (вытяжка)', 'VV-1_barb': 'VV-1 ёлочка вакуумная', 'brackets': 'Уголки и консоли крепления гребёнки', 'vent_line': 'Сбросы PCV-1, PSV-1 → BU-1', 'BU-1_to_T-1': 'BU-1 → T-1', 'T-1_to_S-1': 'T-1 → S-1', 'E-1_barb': 'E-1 переходник кламп → ёлочка', 'A1_to_AV-1': 'A1 → гребёнка AV-1', 'NRV_A1': 'Обратный клапан A1', 'body': 'Корпус', 'jacket': 'Рубашка', 'lid': 'Крышка', 'swing_bolts': 'Откидные болты (8 шт.)', 'M_DN133': 'Штуцер M DN133 (мешалка)', 'lantern': 'Фонарь мешалки', 'motor_WB1800-C': 'Мотор WB1800-C', 'agitator': 'Мешалка, вал Ø26', 'N7_jacket_out': 'N7 рубашка выход DN25', 'N8_jacket_in': 'N8 рубашка вход DN25', 'trunnions': 'Цапфы', 'tilt_gearbox': 'Редуктор опрокидывания', 'L_DN38': 'L нижний слив DN38', 'frame': 'Рама Wiggens', 'control_cart': 'Тележка управления', 'control_box': 'Блок управления', 'E-1_shell_3in_L500': 'E-1 кожух DN65 (3″) L500', 'E-1_coil_stubs': 'E-1 выводы змеевика 12 мм', 'E-1_gas_outlet': 'E-1 отвод газа DN15', 'E-1_insulation': 'E-1 изоляция', 'collector_1in': 'Коллектор гребёнки DN25', 'collector_end_cap': 'Заглушка коллектора DN25', 'PI-4_tee': 'PI-4 тройник', 'PI-4_0-250mbar': 'PI-4 мановакуумметр 0–250 мбар', 'VV-1_tee': 'VV-1 тройник', 'VV-1': 'VV-1 кран кламп DN15 (вакуум)', 'vent_collector': 'Коллектор сбросов DN25', 'vent_hose_to_T-1': 'Сброс → T-1', 'T-1_buffer_4in_L300': 'T-1 буфер DN100 L300', 'T-1_stand': 'T-1 подставка', 'BU-1_bubbler': 'BU-1 барботёр', 'BU-1_stand': 'BU-1 подставка', 'T-1_to_BU-1': 'T-1 → BU-1', 'S-1_scrubber_20L': 'S-1 скруббер 20 л', 'BU-1_to_S-1': 'BU-1 → S-1', 'P2_joint': 'P2 кламп DN25', 'P2_thermowell_8x500': 'P2 заглушка DN25 с гильзой Ø8×500', 'P2_Pt100_head': 'P2 датчик Pt100', 'V-P3': 'V-P3 кран DN15', 'P3_tee_septum_cap': 'P3 тройник с септой и заглушкой', 'P3_dosing_tube': 'P3 трубка дозирования ¼″', 'P4_stack': 'P4 стояк DN25 (резерв, заглушка)', 'P4_sight_glass': 'P4 смотровой фонарь', 'PI-1': 'PI-1 мановакуумметр', 'T2_needle_valve': 'T2 игольчатый вентиль', 'T2_dip_tube': 'T2 погружная трубка ¼″', 'W-2_scale_60kg': 'W-2 весы 60 кг', 'ice_bath': 'Ванна со льдом', 'G-1_Atmaler_BK-40': 'G-1 бак Atmaler БК-40', 'G-1_fittings': 'G-1 штуцеры и манометр', 'column_stand': 'Штатив колонн', 'gas_G1_K1': 'Газ G-1 → K-1', 'gas_C2_to_T2': 'Газ C-2 → T2 реактора', 'NRV-3': 'NRV-3 обратный клапан', 'W-1_scale_30kg': 'W-1 весы 30 кг', 'V-1_MeNH2_aq_canister': 'V-1 канистра 38% MeNH₂', 'P-1_suction': 'P-1 всас', 'P-1_to_G-1': 'P-1 → G-1', 'P-1_needle_NRV': 'P-1 игольчатый вентиль и обратный клапан', 'AR-1_cylinder_40L': 'AR-1 баллон аргона 40 л', 'PR-1_regulator': 'PR-1 редуктор баллона', 'PR-2_FI-1_PSV-2_panel': 'Панель аргона', 'PR-2': 'PR-2 редуктор', 'FI-1_rotameter': 'FI-1 ротаметр', 'Ar_distributor': 'Раздаточная гребёнка аргона', 'Ar_supply': 'Аргон от баллона', 'Ar_PR2_FI1': 'Аргон PR-2 → FI-1', 'A1_to_P4': 'A1 → P4', 'NRV_A1': 'Обратный клапан A1', 'A2_to_G-1': 'A2 → G-1', 'G-1_Ar_inlet': 'G-1 ввод аргона', 'VP-1_vacuum_pump': 'VP-1 вакуумный насос', 'CT-1_separator': 'CT-1 склянка-сепаратор', 'vacuum_line': 'Вакуумная линия', 'trolley': 'Тележка дозирования', 'tray': 'Поддон', 'container': 'Тара MeSiCl₃ / PDMS-OH', 'cap_adapter': 'Крышка-переходник PTFE', 'dip_tube': 'Заборная трубка до дна', 'container_to_P-3': 'Тара → P-3', 'V-B1': 'V-B1 кран ¼″', 'A3_to_container': 'A3 → тара', 'W-4_scale_15kg': 'W-4 весы 15 кг', 'P-3_to_P3_tube': 'P-3 → P3 трубка ¼″', 'FV-1_needle': 'FV-1 игольчатый вентиль', 'NRV-4': 'NRV-4 обратный клапан', 'BV-1_Swagelok': 'BV-1 кран Swagelok', 'tee_KL50_elbow': 'Тройник DN38 с отводом', 'SP-1': 'SP-1 кран отбора проб', 'BV-1_to_P-2_hose': 'BV-1 → P-2 рукав', 'F-1_nutsche_DN350': 'F-1 нутч DN350', 'F-1_stand': 'F-1 опора', 'F-1_lid_fittings': 'F-1 штуцеры крышки', 'PI-5': 'PI-5 мановакуумметр', 'PSV-4_0.3bar': 'PSV-4 сбросной 0,3 бар', 'VV-2': 'VV-2 кран вакуума', 'V-F1_NRV-5': 'V-F1 кран и NRV-5', 'A4_to_F-1': 'A4 → F-1', 'PSV-4_to_T-1': 'PSV-4 → T-1', 'P-2_to_F-1_hose': 'P-2 → F-1 рукав', 'F-2_10in_housing': 'F-2 корпус фильтра 10″', 'F-2_stand': 'F-2 опора', 'F-1_to_F-2': 'F-1 → F-2', 'W-3_scale': 'W-3 весы', 'canister_20L': 'Канистра 20 л', 'F-2_to_canister': 'F-2 → канистра', 'TC-1_chiller': 'TC-1 чиллер', 'TC-1_panel': 'TC-1 панель', 'hose_to_N8': 'Рукав TC-1 → N8', 'hose_from_N7': 'Рукав N7 → TC-1', 'hose_to_E-1_in': 'Рукав TC-1 → E-1', 'hose_from_E-1_out': 'Рукав E-1 → TC-1', 'X1_X2_3way': 'X1, X2 трёхходовые краны', 'P-1_AODD': 'P-1 мембранный насос', 'P-2_AODD': 'P-2 мембранный насос', 'P-3_AODD': 'P-3 мембранный насос', 'PCV-1_spunding': 'PCV-1 шпунт-аппарат DN25', 'NRV-1_100mbar': 'NRV-1 обратный 100 мбар', 'PSV-1_200mbar': 'PSV-1 сбросной 200 мбар', 'NRV-2_KF25': 'NRV-2 KF25 перевёрнутый', 'K-1_knockout_300': 'K-1 каплеотбойник DN65 L300', 'C-1_3A_sieves_600': 'C-1 сита 3A DN65 L600', 'C-2_NaOH_600': 'C-2 NaOH DN65 L600'}
GR = {'R-1_Wiggens_50L': 'R-1 реактор Wiggens 50 л', 'Frame_Wiggens': 'Рама Wiggens и тележка управления', 'E-1_condenser': 'E-1 конденсатор', 'Manifold': 'Гребёнка, BU-1, T-1, S-1', 'Lid_nodes': 'Узлы крышки P2 P3 P4 T1 T2', 'Generator_G-1': 'Генератор G-1, колонны, P-1', 'Argon_Vacuum': 'Аргон и вакуум', 'Dosing_P-3': 'Дозирование MeSiCl₃ / PDMS-OH, P-3', 'Discharge_Filtration': 'Выгрузка: P-2, F-1, F-2', 'Thermostat_TC-1': 'Чиллер TC-1 и рукава'}


def ru(name):
    """Русское имя детали для дерева STEP."""
    import re
    if name in RU:
        return RU[name]
    m = re.match(r'^(N\d)_(DN25|8mm)_(\w+)$', name)
    if m:
        return f'Штуцер {m.group(1)} {"DN25" if m.group(2) == "DN25" else "8 мм"} ({m.group(3)})'
    m = re.match(r'^gas_col(\d)_col(\d)$', name)
    if m:
        cols = ['K-1', 'C-1', 'C-2']
        return f'Газ {cols[int(m.group(1))]} → {cols[int(m.group(2))]}'
    for suf, txt in (('_tee', 'тройник'), ('_joint', 'кламп'), ('_drop', 'опуск на коллектор сбросов'), ('_clamp_arm', 'держатель')):
        if name.endswith(suf):
            base = name[:-len(suf)]
            return f'{RU.get(base, base).split(" ")[0]} {txt}'
    if re.match(r'^SV-\d$', name):
        return f'{name} кран DN25'
    return name


ROOT = cq.Assembly(name='ТЕФКОТ 770 установка')
GROUPS = {}
_names = {}


def add(group, name, shape, color):
    if isinstance(shape, (list, tuple)):
        shape = cq.Compound.makeCompound(list(shape))
    group, name = GR.get(group, group), ru(name)
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
    zg = z0 + 520                               # отвод газа DN15 (кламп 25), назад (+Y) к гребёнке
    add(g, 'E-1_gas_outlet', [cyl((x, y + 30, zg), (x, y + 90, zg), 19)] + clampj((x, y + 90, zg), (0, 1, 0), 25), 'steel')
    add(g, 'E-1_barb', [cone((x, y + 93, zg), (x, y + 130, zg), 25, 12)], 'steel')
    # изоляция
    add(g, 'E-1_insulation', [cyl((x, y, z0 + 70), (x, y, z0 + 500), 110).cut(cyl((x, y, z0 + 60), (x, y, z0 + 510), 78))], 'epdm')

    # ---- гребёнка: отдельно, на уголках к колонне рамы; к E-1 — шлангом на ёлочках
    g = 'Manifold'
    my, zc = 620, 1400                          # ось коллектора DN15 (кламп 25)
    X = {'PI': 0, 'AR': 90, 'SH': 180, 'PS': 270, 'AT': 360, 'VAC': 450}
    D = 19                                      # труба ¾″
    add(g, 'inlet_barb', [cone((-100, my, zc), (-62, my, zc), 12, 25)] + clampj((-59, my, zc), (1, 0, 0), 25), 'steel')
    add(g, 'hose_E-1_to_manifold', run([(x, y + 130, zg), (x, 400, zg), (-150, 400, zg), (-150, my, zg), (-150, my, zc), (-100, my, zc)], 16), 'ptfe')
    add(g, 'collector', [cyl((-56, my, zc), (X['VAC'], my, zc), D), sph((X['VAC'], my, zc), D)], 'steel')
    joints = []
    for a_, b_ in (('PI', 'AR'), ('AR', 'SH'), ('SH', 'PS'), ('PS', 'AT'), ('AT', 'VAC')):
        joints += clampj(((X[a_] + X[b_]) / 2, my, zc), (1, 0, 0), 25)
    add(g, 'collector_clamps', joints, 'steel')

    def branch(xx, name, top_extra):
        add(g, f'{name}_tee', [cyl((xx, my, zc), (xx, my, zc + 40), D)] + clampj((xx, my, zc + 40), (0, 0, 1), 25), 'steel')
        if name == 'PI-4':
            return zc + 43
        add(g, name, ball_valve((xx, my, zc + 80), (0, 0, 1), D, lever=(0, -1, 0), L=70), 'red' if name == 'SV-2' else 'steel')
        add(g, f'{name}_joint', clampj((xx, my, zc + 118), (0, 0, 1), 25), 'steel')
        return zc + 121
    z = branch(X['PI'], 'PI-4', 0)
    add(g, 'PI-4_gauge', [cyl((X['PI'], my, z), (X['PI'], my, z + 50), 12)] + gauge((X['PI'], my - 20, z + 95), (0, -1, 0), 100), 'white')
    z = branch(X['AR'], 'AV-1', 0)
    add(g, 'AV-1_G12_adapter', [cyl((X['AR'], my, z), (X['AR'], my, z + 25), 28), cyl((X['AR'], my, z + 25), (X['AR'], my, z + 45), 14)], 'steel')
    av_top = (X['AR'], my, z + 45)
    xx = X['SH']
    z = branch(xx, 'SV-1', 0)
    add(g, 'NRV-1', check_valve((xx, my, z + 30), (0, 0, 1), D), 'steel')
    add(g, 'NRV-1_joint', clampj((xx, my, z + 63), (0, 0, 1), 25), 'steel')
    add(g, 'reducer_DN15_DN25', [cone((xx, my, z + 66), (xx, my, z + 100), D, 33.7)] + clampj((xx, my, z + 103), (0, 0, 1), 50.5), 'steel')
    add(g, 'PCV-1_spunding', [cyl((xx, my, z + 106), (xx, my, z + 200), 60), cyl((xx, my, z + 200), (xx, my, z + 220), D)]
        + gauge((xx + 45, my, z + 160), (1, 0, 0), 63) + [cyl((xx + 30, my, z + 160), (xx + 33, my, z + 160), 10)], 'steel')
    sh_top = (xx, my, z + 220)
    xx = X['PS']
    z = branch(xx, 'SV-2', 0)
    add(g, 'PSV-1_200mbar', [cyl((xx, my, z), (xx, my, z + 95), 45), cyl((xx, my, z + 95), (xx, my, z + 110), D)], 'steel')
    ps_top = (xx, my, z + 110)
    xx = X['AT']
    z = branch(xx, 'SV-3', 0)
    add(g, 'SV-3_barb', [cone((xx, my, z), (xx, my, z + 35), 25, 12)], 'steel')
    add(g, 'SV-3_hose_to_hood', [cyl((xx, my, z + 35), (xx, my, z + 300), 16)], 'ptfe')
    xx = X['VAC']
    z = branch(xx, 'VV-1', 0)
    add(g, 'VV-1_barb', [cone((xx, my, z), (xx, my, z + 35), 25, 12)], 'steel')
    vac_top = (xx, my, z + 35)
    # крепление: уголок поперёк колонны рамы + две консоли с хомутами-держателями
    add(g, 'brackets', [box(-380, 668, zc - 70, 380, 690, zc - 40), box(-380, 668, zc - 70, 380, 690 - 18, zc - 66)]
        + [box(xb - 15, my, zc - 70, xb + 15, 668, zc - 40) for xb in (40, 315)]
        + [cyl((xb - 10, my, zc), (xb + 10, my, zc), 40).cut(cyl((xb - 12, my, zc), (xb + 12, my, zc), D)) for xb in (40, 315)]
        + [box(xb - 6, my - 6, zc - 40, xb + 6, my + 6, zc - 20) for xb in (40, 315)], 'frame')
    # сбросы PCV-1 и PSV-1 → BU-1 → T-1 → S-1 (на полу за тележкой)
    bx, by = 1060, 520
    vz = 1860
    add(g, 'vent_line', run([sh_top, (sh_top[0], my, vz), (bx, my, vz), (bx, by, vz), (bx, by, 470)], 12)
        + run([ps_top, (ps_top[0], my, vz)], 12), 'vent')
    add(g, 'BU-1_bubbler', [cyl((bx, by, 150), (bx, by, 450), 60), cyl((bx, by, 450), (bx, by, 470), 30)], 'glass')
    add(g, 'BU-1_stand', [box(bx - 60, by - 60, 0, bx + 60, by + 60, 10), cyl((bx, by, 10), (bx, by, 150), 40)], 'dark')
    tx, ty = 1200, 520
    add(g, 'T-1_buffer_4in_L300', [cyl((tx, ty, 200), (tx, ty, 500), 101.6), cyl((tx, ty, 500), (tx, ty, 515), 119), cyl((tx, ty, 185), (tx, ty, 200), 119), cyl((tx, ty, 515), (tx, ty, 560), 25.4)], 'steel')
    add(g, 'T-1_stand', [box(tx - 80, ty - 80, 0, tx + 80, ty + 80, 10), cyl((tx, ty, 10), (tx, ty, 185), 60)], 'dark')
    add(g, 'BU-1_to_T-1', run([(bx + 20, by, 460), (bx + 20, by, 600), (tx, ty, 600), (tx, ty, 560)], 8), 'ptfe')
    sx, sy = 1360, 540
    add(g, 'S-1_scrubber_20L', [box(sx - 120, sy - 120, 0, sx + 120, sy + 120, 380), cyl((sx, sy, 380), (sx, sy, 410), 50)], 'poly')
    add(g, 'T-1_to_S-1', run([(tx + 50, ty, 470), (tx + 110, ty, 470), (sx, sy, 470), (sx, sy, 410)], 8), 'ptfe')
    return (x, y), zc, {'av_top': av_top, 'vac_top': vac_top}


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
    # P4: стояк со смотровым фонарём — резерв, глухая заглушка
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
def argon_vacuum(p4_top, zc_e1, e1xy, M):
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
    # A1 → гребёнка, кран AV-1 (G½″), обратный клапан на линии
    x, y, z = M['av_top']
    a1 = outs['A1']
    add(g, 'A1_to_AV-1', run([a1, (a1[0], 580, a1[2]), (x, 580, a1[2]), (x, 580, z + 60), (x, y, z + 60), (x, y, z)], 6.35), 'argon')
    add(g, 'NRV_A1', check_valve((-100, 580, a1[2]), (1, 0, 0), 10), 'steel')
    # A2 → G-1 (продувка генератора)
    add(g, 'A2_to_G-1', run([outs['A2'], (outs['A2'][0], outs['A2'][1], 1380), (-1340, outs['A2'][1], 1380), (-1340, -50, 1380), (-1340, -50, 600)], 6.35), 'argon')
    add(g, 'G-1_Ar_inlet', [cyl((-1340, -50, 555), (-1340, -50, 600), 20)], 'dark')
    # вакуум: VV-1 на гребёнке → CT-1 → VP-1
    vx, vy = -650, 480
    add(g, 'VP-1_vacuum_pump', [box(vx - 175, vy - 125, 0, vx + 175, vy + 125, 260)], 'dark')
    add(g, 'CT-1_separator', [cyl((vx + 100, vy, 260), (vx + 100, vy, 460), 120)], 'glass')
    x, y, z = M['vac_top']
    add(g, 'vacuum_line', run([(x, y, z), (x, y, 1900), (vx + 100, y, 1900), (vx + 100, vy, 1900), (vx + 100, vy, 460)], 16), 'ptfe')
    return outs


# ---------------------------------------------------------------- дозирование P-3 из тары
def dosing(p3_top, ar_outs):
    g = 'Dosing_P-3'
    tx, ty = -560, -560                     # тележка
    parts = []
    for x in (tx - 200, tx + 200):
        for y in (ty - 200, ty + 200):
            parts.append(cbox((x, y, 450), 25, 25, 900))
    parts += [box(tx - 215, ty - 215, 900, tx + 215, ty + 215, 915), box(tx - 215, ty - 215, 280, tx + 215, ty + 215, 295)]
    add(g, 'trolley', parts, 'frame')
    add(g, 'W-4_scale_15kg', [box(tx - 160, ty - 160, 915, tx + 160, ty + 160, 965)], 'dark')
    add(g, 'tray', [box(tx - 110, ty - 110, 965, tx + 110, ty + 110, 1025).cut(box(tx - 104, ty - 104, 971, tx + 104, ty + 104, 1030))], 'poly')
    z0 = 971                                   # тара поставщика (бутыль 2,5 л — размеры уточнить)
    zc = z0 + 330
    add(g, 'container', [cyl((tx, ty, z0), (tx, ty, z0 + 250), 140), cone((tx, ty, z0 + 250), (tx, ty, z0 + 300), 140, 50),
                         cyl((tx, ty, z0 + 300), (tx, ty, zc - 20), 50)], 'glass')
    add(g, 'cap_adapter', [cyl((tx, ty, zc - 20), (tx, ty, zc), 60)], 'ptfe')
    add(g, 'dip_tube', [cyl((tx + 12, ty, zc + 40), (tx + 12, ty, z0 + 8), 8)], 'ptfe')
    suc, dis = pump((tx, ty, 295), 'P-3_AODD', g)
    add(g, 'container_to_P-3', run([(tx + 12, ty, zc + 40), (tx + 12, ty, zc + 70), (tx - 250, ty, zc + 70), (tx - 250, ty, suc[2]), (suc[0] - 100, ty, suc[2])], 8), 'ptfe')
    add(g, 'V-B1', ball_valve((tx - 250, ty, 700), (0, 0, 1), 10, lever=(0, -1, 0), L=36), 'steel')
    x, y, z = p3_top
    route = [(dis[0] + 100, dis[1], dis[2]), (tx + 160, ty, dis[2]), (tx + 160, ty, 1700), (x, ty, 1700), (x, y, 1700), (x, y, z)]
    add(g, 'P-3_to_P3_tube', run(route, 6.35), 'ptfe')
    add(g, 'FV-1_needle', [cbox((tx + 160, ty, 800), 30, 30, 50), cyl((tx + 160, ty, 800), (tx + 160, ty - 50, 800), 20)], 'steel')
    add(g, 'NRV-4', check_valve((tx + 160, ty, 1000), (0, 0, 1), 10), 'steel')
    # аргон A3 на крышку-переходник тары
    a3 = ar_outs['A3']
    add(g, 'A3_to_container', run([a3, (a3[0], a3[1], 1760), (tx - 12, a3[1], 1760), (tx - 12, ty, 1760), (tx - 12, ty, zc)], 6.35), 'argon')


# ---------------------------------------------------------------- выгрузка
def discharge(zap, ar_outs):
    g = 'Discharge_Filtration'
    # BV-1 Swagelok → тройник DN25 с SP-1 → отвод → рукав на P-2
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
    tx, ty = 1200, 520
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
    """Чиним двойную кодировку имён в GLB и пишем glTF с встроенным буфером
    (для просмотрщика: .glb артефакт не отдаёт)."""
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
    for key in ('nodes', 'meshes', 'materials', 'scenes'):
        for item in js.get(key, []):
            if 'name' in item:
                try:
                    item['name'] = item['name'].encode('latin-1').decode('utf-8')
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
    jb = json.dumps(js, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    jb += b' ' * (-len(jb) % 4)
    binary += b'\0' * (-len(binary) % 4)
    body = struct.pack('<II', len(jb), 0x4E4F534A) + jb + struct.pack('<II', len(binary), 0x004E4942) + binary
    open(src, 'wb').write(struct.pack('<III', 0x46546C67, 2, 12 + len(body)) + body)
    js['buffers'][0]['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(binary).decode()
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(js, f, ensure_ascii=False, separators=(',', ':'))


def fix_step_names(path):
    """OCCT пишет имена в STEP дважды закодированным UTF-8. Перекодируем в стандартный
    для STEP вид \\X2\\hhhh\\X0\\ (ISO 10303-21), его читают КОМПАС, SolidWorks, FreeCAD."""
    import re
    raw = open(path, 'rb').read().decode('utf-8')
    try:
        txt = raw.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        txt = raw
    def enc(m):
        return '\\X2\\' + ''.join('%04X' % ord(c) for c in m.group(0)) + '\\X0\\'
    txt = re.sub(r'[^\x00-\x7f]+', enc, txt)
    open(path, 'w', encoding='ascii').write(txt)


def build():
    zap = reactor()
    frame()
    e1xy, zc, M = condenser_and_manifold()
    p3_top, p4_top, t2_top = lid_nodes()
    generator(t2_top)
    outs = argon_vacuum(p4_top, zc, e1xy, M)
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
    fix_step_names(step)
    try:
        a.save(os.path.join(OUT, 'tefkot-770-ustanovka.glb'), tolerance=0.8, angularTolerance=0.4)
        glb_to_gltf_json(os.path.join(OUT, 'tefkot-770-ustanovka.glb'), os.path.join(OUT, 'tefkot-770-ustanovka.gltf.json'))
    except Exception as e:                                           # noqa: BLE001
        print('glb:', e)
    print('ok', step, os.path.getsize(step) // 1024, 'KB')
