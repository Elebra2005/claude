# 3D-модель установки: STEP + GLB

Рабочий пример — `scripts/examples/example_3d_model.py` (копия `tefkot/tools/step_model.py`) (≈900 строк, установка ТЕФКОТ 770): реактор по чертежу производителя, рама, гребёнка, генератор, колонны, аргон, дозирование, выгрузка, нутч, фильтр, чиллеры. **Новый проект начинай с копии этого файла**: примитивы и экспорт переиспользуются как есть, меняются только функции узлов.

## Как устроено
- CadQuery (`import cadquery as cq`), всё в миллиметрах, ось Z вверх, начало — ось реактора на полу.
- Примитивы: `cyl(a, b, D)`, `cone(a, b, D1, D2)`, `box(x0,y0,z0,x1,y1,z1)`, `cbox(c, dx, dy, dz)`, `sph(c, D)`, `run(points, D)` — труба/рукав по ломаной со скруглёнными стыками.
- Арматура: `clampj(c, dir, ферула)` — кламповое соединение (2 ферулы + хомут), `ball_valve(c, dir, D, lever, L)`, `check_valve(c, dir, D)`, `gauge(c, dir, D)`, `pump(...)`, `peri_pump(...)`.
- `add(группа, имя, [детали], цвет)` — деталь в сборку. Имя латиницей с позицией (`'SV-G1'`, `'F-1_tee45'`), а русское описание — в словаре описаний в начале файла: оно попадает в названия деталей STEP/GLB (то, что видно в дереве КОМПАС/FreeCAD). **Каждой новой детали — строка в словаре.**
- Группы = узлы схемы (Reactor, Manifold, Generator_G-1, Argon_Vacuum, Dosing, Discharge_Filtration, Thermostat) — в viewer они включаются/выключаются чекбоксами.

## Выход (`python3 tools/step_model.py`)
- `3d/<name>.step` — имена в Windows-1251 (КОМПАС читает только так), `<name>-utf8.step` — для FreeCAD и др., `<name>-step.zip` — оба (при пересылке как текст cp1251 портится, в zip — нет).
- `3d/<name>.glb` и `<name>.gltf.json` (glTF со встроенным буфером — для веб-просмотрщика).
- `3d/viewer.html` — просмотрщик three.js (шаблон — `assets/viewer.html`): виды `?view=iso|front|side|top`, разрез `&sec=1`, цель/дистанция `&t=x,y,z&d=мм`.

## Рендеры для отчёта
```
cd skills/montazhnye-chertezhi/scripts/render3d && npm i   # один раз (three@0.160)
node shot3d.js ../../../../tefkot/3d <out> iso,top
node shot3d.js ../../../../tefkot/3d <out> front:sec "t=0,0,900&d=2400"
```
PNG → JPG (Pillow, quality 88) в `3d/izometriya.jpg`, `vid-sverhu.jpg`, `razrez-reaktora.jpg`. Обязательно открой изометрию глазами: висящие трубы, детали внутри друг друга, кириллица в панели.

## Правило синхронизации
3D — третье представление той же схемы. После любой правки обвязки (новый кран, тройник, переход, снятый клапан) правь **все три**: P&ID (`scheme_vsdx.py` / SVG в HTML), монтажные чертежи (`cherteg.py`), 3D (`step_model.py`) — и смету. Перед выдачей пройдись grep'ом по старым позициям (`grep -n "PSV-3" tools/*.py *.html`) — 3D и документ отстают чаще всего.
