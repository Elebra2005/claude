"""Пересобрать из сметы (tools/smeta-data.json): смету XLSX, раздел «Спецификация» в документе установки
и таблицу заказа в zakaz-grossner.html. Запуск: python3 tools/sync_docs.py"""
import html
import json
import os
import re
import subprocess
import sys

T = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
E = html.escape
d = json.load(open(os.path.join(T, 'tools/smeta-data.json'), encoding='utf-8'))
ALL = d['groups'] + [g for ex in d.get('extra_sheets', []) for g in ex['groups']]

# 1. смета XLSX
subprocess.run([sys.executable, os.path.join(T, '../skills/montazhnye-chertezhi/scripts/smeta_xlsx.py'),
                os.path.join(T, 'tools/smeta-data.json'), os.path.join(T, 'itog/tefkot-770-smeta.xlsx')], check=True)

# 2. спецификация в документе установки
CLS = {'КУПИТЬ': 'y', 'УТОЧНИТЬ': 'h', 'ЕСТЬ': 'h', 'ЭТАП 2': 'c'}
rows = []
for g in ALL:
    rows.append(f'<tr class="sec"><td colspan="7">{E(g["title"])}</td></tr>')
    for r in g['rows']:
        nm = E(r['name']) + (f' — <b>{E(r["size"])}</b>' if r['size'] else '')
        link = f'<a href="{E(r["url"])}" target="_blank" rel="noopener">{E(r["shop"])}</a>' if r.get('url') else E(r['shop'])
        if r.get('extra_url'):
            link += f'<br><a href="{E(r["extra_url"])}" target="_blank" rel="noopener">доп. ссылка</a>'
        rows.append(f'<tr><td class="pos">{E(r["pos"])}</td><td>{nm}</td><td>{E(r["purpose"])}</td><td class="n">{E(r["qty_scheme"])}</td>'
                    f'<td class="n"><b>{E(r["qty_buy"])}</b></td><td><span class="buy {CLS.get(r["status"], "y")}">{r["status"]}</span></td><td class="buy-l">{link}</td></tr>')
p = os.path.join(T, 'tefkot-770-reaktor-50l.html')
s = open(p, encoding='utf-8').read()
a = s.index('<tbody>', s.index('<h2 id="s14">')) + len('<tbody>')
b = s.index('</tbody>', a)
s = s[:a] + '\n' + '\n'.join(rows) + '\n' + s[b:]
open(p, 'w', encoding='utf-8').write(s)

# 3. заказ Гросснер
rows, n = [], 0
for g in ALL:
    gr = [r for r in g['rows'] if r['shop'].startswith('Гросснер') and r['status'] not in ('ЕСТЬ', 'ЭТАП 2')]
    if not gr:
        continue
    rows.append(f'      <tr class="grp"><td colspan="5">{E(g["title"])}</td></tr>')
    for r in gr:
        n += 1
        st = '' if r['status'] == 'КУПИТЬ' else ' <span class="st hold">уточнить</span>'
        rows.append(f'      <tr><td><a href="{E(r["url"])}" target="_blank" rel="noopener">{E(r["name"])}</a>{st}</td><td class="pos">{E(r["size"])}</td>'
                    f'<td class="where">{(E(r["pos"]) + ": ") if r["pos"] else ""}{E(r["purpose"])}</td><td class="n">{E(r["qty_scheme"])}</td><td class="q">{E(r["qty_buy"])}</td></tr>')
p = os.path.join(T, 'zakaz-grossner.html')
s = open(p, encoding='utf-8').read()
a = s.index('<tbody>', s.index('id="partA"')) + len('<tbody>')
b = s.index('</tbody>', a)
s = s[:a] + '\n' + '\n'.join(rows) + '\n    ' + s[b:]
s = re.sub(r'позиций: <b>\d+</b>', f'позиций: <b>{n}</b>', s)
open(p, 'w', encoding='utf-8').write(s)
print(f'спецификация и заказ обновлены: Гросснер {n} позиций')
