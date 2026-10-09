"""Генерирует HTML-страницы схем для курса. Рендер в PNG — render.js."""
import os, sys

OUT = os.path.dirname(os.path.abspath(__file__))

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#1f1d1a;--muted:#6b665e;--line:#e2dbcf;--accent:#c2603e;--accent-soft:#fbeee8;
--teal:#2f6f6a;--teal-soft:#e6f1ef;--panel:#ffffff;--bg:#f8f4ee;--warn:#b7791f;--warn-soft:#fdf3df}
body{font-family:Inter,sans-serif;color:var(--ink);background:var(--bg)}
#card{width:1200px;height:675px;padding:44px 56px 40px;position:relative;background:var(--bg);overflow:hidden}
.kicker{font-size:15px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}
h1{font-family:'Inter Display',Inter,sans-serif;font-size:38px;font-weight:700;letter-spacing:-.01em;margin-top:6px;line-height:1.15}
.sub{font-size:18px;color:var(--muted);margin-top:8px}
.foot{position:absolute;left:56px;right:56px;bottom:28px;font-size:14px;color:var(--muted);display:flex;justify-content:space-between}
.box{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px 20px}
.row{display:flex;align-items:center}
.arr{flex:none;width:46px;display:flex;justify-content:center;color:var(--muted)}
.tag{display:inline-block;font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;border-radius:6px;padding:3px 8px}
.t-acc{background:var(--accent-soft);color:var(--accent)}
.t-teal{background:var(--teal-soft);color:var(--teal)}
.big{font-size:22px;font-weight:700;line-height:1.25}
.small{font-size:16px;color:var(--muted);line-height:1.4;margin-top:6px}
"""

ARROW = '<svg width="40" height="20" viewBox="0 0 40 20"><path d="M2 10h32M26 3l8 7-8 7" fill="none" stroke="#8a8378" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
ARROW_DOWN = '<svg width="20" height="34" viewBox="0 0 20 34"><path d="M10 2v26M3 21l7 8 7-8" fill="none" stroke="#8a8378" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'


def page(body, kicker, title, sub="", foot_left="Курс «ИИ в работе»"):
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>{CSS}</style></head>
<body><div id="card"><div class="kicker">{kicker}</div><h1>{title}</h1>{f'<div class="sub">{sub}</div>' if sub else ''}
{body}<div class="foot"><span>{foot_left}</span><span>Claude</span></div></div></body></html>"""


D = {}

# 01 — как работает Claude
D["d01_how_it_works"] = page(f"""
<div class="row" style="margin-top:46px;gap:0">
  <div class="box" style="width:230px;height:196px"><span class="tag t-teal">Вы</span><div class="big" style="margin-top:12px">Запрос и материалы</div><div class="small">задача, файлы, контекст</div></div>
  <div class="arr">{ARROW}</div>
  <div class="box" style="width:230px;height:196px;background:var(--ink);border-color:var(--ink);color:#fff"><span class="tag" style="background:#3a3632;color:#f3c9b8">Модель</span><div class="big" style="margin-top:12px">Claude</div><div class="small" style="color:#cfc8be">понимает задачу и формирует ответ</div></div>
  <div class="arr">{ARROW}</div>
  <div class="box" style="width:230px;height:196px"><span class="tag t-teal">Результат</span><div class="big" style="margin-top:12px">Ответ, документ, расчёт</div><div class="small">черновик для работы</div></div>
  <div class="arr">{ARROW}</div>
  <div class="box" style="width:230px;height:196px;border:2px solid var(--accent);background:var(--accent-soft)"><span class="tag t-acc">Обязательно</span><div class="big" style="margin-top:12px">Проверка человеком</div><div class="small">решение и ответственность — за вами</div></div>
</div>
<div class="row" style="margin-top:34px;gap:16px">
  <div class="box" style="flex:1"><div class="big" style="font-size:19px">Не поисковик</div><div class="small">без веб-поиска не ищет в интернете</div></div>
  <div class="box" style="flex:1"><div class="big" style="font-size:19px">Не справочник</div><div class="small">может ошибиться в цифрах и номерах норм</div></div>
  <div class="box" style="flex:1"><div class="big" style="font-size:19px">Не замена специалиста</div><div class="small">ускоряет работу, но не принимает решения</div></div>
</div>""", "Урок 1", "Как работает Claude", "Эрудированный стажёр: быстро делает черновик, вы проверяете и принимаете решение")

# 02 — токены
chips = ["Рас", "счи", "тай", " мощ", "ность", " меш", "алки", " реак", "тора"]
cols = ["#fbeee8", "#e6f1ef", "#fdf3df", "#ece8f6"]
bord = ["#e7b9a6", "#a9cdc7", "#ead29d", "#c9bfe6"]
chip_html = "".join(
    f'<span style="display:inline-block;background:{cols[i%4]};border:1.5px solid {bord[i%4]};border-radius:10px;padding:10px 12px;margin:0 6px 10px 0;font-size:30px;font-weight:600;white-space:pre">{c}</span>'
    for i, c in enumerate(chips))
D["d02_tokens"] = page(f"""
<div class="box" style="margin-top:36px;padding:26px 28px">
  <div class="small" style="margin:0 0 14px">Фраза: «Рассчитай мощность мешалки реактора»</div>
  <div>{chip_html}</div>
  <div class="small" style="margin-top:6px">Каждый цветной фрагмент — один токен. Разбивка условная: реальные границы зависят от модели.</div>
</div>
<div class="row" style="margin-top:22px;gap:16px;align-items:stretch">
  <div class="box" style="flex:1"><span class="tag t-teal">В токенах измеряется</span><div class="small" style="font-size:18px;color:var(--ink)">объём контекста · лимиты · длина ответа</div></div>
  <div class="box" style="flex:1"><span class="tag t-acc">Учтите</span><div class="small" style="font-size:18px;color:var(--ink)">русский текст обычно «дороже» английского по числу токенов</div></div>
  <div class="box" style="flex:1"><span class="tag t-teal">Правило</span><div class="small" style="font-size:18px;color:var(--ink)">короче и точнее — экономнее и для лимита, и для качества</div></div>
</div>""", "Урок 2", "Как текст делится на токены")

# 03 — контекстное окно
def bubble(text, who, faded=False):
    me = who == "you"
    bg = "#fff" if not me else "#e6f1ef"
    op = "opacity:.38;" if faded else ""
    al = "margin-left:auto;" if me else ""
    return f'<div style="{op}{al}max-width:78%;background:{bg};border:1px solid var(--line);border-radius:12px;padding:8px 12px;font-size:16px;margin-bottom:8px">{text}</div>'
win = "".join([
    bubble("Сжато: обсуждали письмо поставщику…", "ai", True),
    bubble("…и расчёт объёма ёмкости", "you", True),
    bubble("Загружен файл: ТКП_1.pdf", "you"),
    bubble("Сравнительная таблица по ТКП готова", "ai"),
    bubble("Добавь столбец «Гарантия»", "you"),
    bubble("Таблица обновлена", "ai"),
])
D["d03_context"] = page(f"""
<div class="row" style="margin-top:30px;gap:28px;align-items:stretch">
  <div style="flex:1.25;position:relative">
    <div style="border:3px solid var(--teal);border-radius:18px;padding:18px 18px 10px;background:#fbfaf7;height:380px;position:relative;overflow:hidden">
      <span class="tag t-teal" style="position:absolute;top:-1px;right:16px;border-radius:0 0 8px 8px;z-index:2">Контекстное окно</span>
      <div style="margin-top:22px">{win}</div>
      <div style="position:absolute;left:0;right:0;top:0;height:110px;background:linear-gradient(#fbfaf7,rgba(251,250,247,0))"></div>
    </div>
    <div class="small" style="margin-top:8px">Ранние части длинного чата сжимаются — детали теряются</div>
  </div>
  <div style="flex:1;display:flex;flex-direction:column;gap:14px">
    <div class="box"><span class="tag t-acc">Другие чаты</span><div class="small" style="font-size:17px;color:var(--ink)">по умолчанию Claude их не видит: каждый новый чат — с чистого листа</div></div>
    <div class="box"><div class="big" style="font-size:20px">Одна задача — один чат</div></div>
    <div class="box"><div class="big" style="font-size:20px">Новая тема — новый чат</div></div>
    <div class="box"><div class="big" style="font-size:20px">Путается — резюме и новый чат</div><div class="small">«Сделай краткое резюме, чтобы продолжить в новом чате»</div></div>
  </div>
</div>""", "Урок 3", "Контекстное окно: что Claude «помнит»")

# 07 — конфиденциальность
def items(lst, color):
    return "".join(f'<div style="display:flex;gap:12px;align-items:flex-start;margin:11px 0;font-size:19px;line-height:1.35"><span style="flex:none;width:10px;height:10px;border-radius:50%;background:{color};margin-top:8px"></span><span>{t}</span></div>' for t in lst)
D["d07_privacy"] = page(f"""
<div class="row" style="margin-top:28px;gap:22px;align-items:stretch">
  <div class="box" style="flex:1;border-top:6px solid var(--teal)"><div class="big" style="color:var(--teal)">Можно</div>
  {items(["Общедоступные нормативы и справочники", "Свои черновики, письма, шаблоны без чувствительных данных", "Обезличенные документы: «Заказчик» вместо названия, условные цифры", "Учебные и тестовые примеры"], "var(--teal)")}</div>
  <div class="box" style="flex:1;border-top:6px solid var(--accent)"><div class="big" style="color:var(--accent)">Нельзя</div>
  {items(["Пароли, ключи доступа, банковские данные", "Персональные данные сотрудников и клиентов", "Рецептуры, режимы, ноу-хау — без разрешения руководства", "Документы с грифом и данные заказчиков под NDA"], "var(--accent)")}</div>
</div>
<div class="box" style="margin-top:18px;background:var(--warn-soft);border-color:#ecd7a6;font-size:19px"><b>Сомневаетесь?</b> Спросите в канале до загрузки, а не после. Тест: можно ли передать это внешнему подрядчику?</div>
""", "Урок 7", "Что можно и что нельзя загружать в Claude")

# 08 — анатомия промта
parts = [
    ("Роль", "кем быть", "«Ты — инженер-технолог полимерного производства»"),
    ("Контекст", "что, для кого, зачем", "«Письмо заказчику, срок сорван на 2 недели»"),
    ("Задача", "что сделать — глаголом", "«Найди противоречия между разделами 2 и 4»"),
    ("Исходные данные", "файлы и цифры", "«Прикладываю ТКП и спецификацию»"),
    ("Требования", "нормы, стиль, объём", "«Только по приложенному СП, без канцелярита»"),
    ("Формат", "вид результата", "«Таблица: № | Замечание | Пункт | Критичность»"),
]
tiles = "".join(
    f'<div class="box" style="display:flex;gap:16px;align-items:flex-start;padding:18px"><div style="flex:none;width:44px;height:44px;border-radius:12px;background:var(--accent);color:#fff;font-weight:700;font-size:22px;display:flex;align-items:center;justify-content:center">{i+1}</div><div><div class="big" style="font-size:21px">{a}</div><div class="small" style="margin-top:2px">{b}</div><div style="font-size:15px;color:var(--teal);margin-top:8px;line-height:1.35">{c}</div></div></div>'
    for i, (a, b, c) in enumerate(parts))
D["d08_prompt_anatomy"] = page(f"""
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:28px">{tiles}</div>
<div class="box" style="margin-top:18px;background:var(--accent-soft);border-color:#efc9b9;font-size:19px"><b>Тест промта:</b> понял бы новый сотрудник задание без дополнительных вопросов?</div>
""", "Урок 8", "Шесть частей хорошего промта")

# 19 — Chat и Code
rows = [
    ("Что делает", "Отвечает в переписке, советует", "Выполняет работу в папке на компьютере"),
    ("Ваши файлы", "Только те, что вы приложили", "Читает и правит файлы выбранной папки"),
    ("Расчёты", "Может считать, но результат остаётся в чате", "Считает кодом, сохраняет в Excel и отчёты"),
    ("Ход работы", "Один ответ на сообщение", "Много шагов: делает → проверяет → исправляет"),
    ("Когда использовать", "Быстрый вопрос, правка пары фраз", "Документы, расчёты, чертежи, обработка файлов"),
]
tr = "".join(
    f'<tr><td style="padding:13px 16px;font-weight:700;font-size:17px;border-top:1px solid var(--line);width:22%">{a}</td><td style="padding:13px 16px;font-size:17px;border-top:1px solid var(--line);color:var(--muted)">{b}</td><td style="padding:13px 16px;font-size:17px;border-top:1px solid var(--line);background:var(--teal-soft)">{c}</td></tr>'
    for a, b, c in rows)
D["d19_chat_vs_code"] = page(f"""
<div class="box" style="margin-top:26px;padding:0;overflow:hidden">
<table style="width:100%;border-collapse:collapse">
<tr><th style="padding:14px 16px;text-align:left;font-size:15px;color:var(--muted);font-weight:600"></th>
<th style="padding:14px 16px;text-align:left;font-size:22px">Chat <span style="font-size:16px;color:var(--muted);font-weight:500">— советует</span></th>
<th style="padding:14px 16px;text-align:left;font-size:22px;background:var(--teal);color:#fff">Code <span style="font-size:16px;font-weight:500;color:#d4ebe7">— делает</span></th></tr>
{tr}</table></div>
<div class="small" style="margin-top:14px;font-size:17px">Для рабочих задач — вкладка Code в приложении Claude на компьютере (режим «Локально»).</div>
""", "Урок 19", "Chat или Code: где работать")

# 25 — CLAUDE.md
md = """<span style="color:#c2603e"># Проект: модернизация линии экструзии</span>

<span style="color:#2f6f6a">## О проекте</span>
Папка рабочих материалов по модернизации линии экструзии.

<span style="color:#2f6f6a">## Правила оформления</span>
- Документы — по шаблону Шаблон.docx
- Единицы измерения — СИ, вязкость в Па·с

<span style="color:#2f6f6a">## Термины</span>
- Р-101 — реактор (не «ёмкость»)

<span style="color:#2f6f6a">## Порядок работы</span>
- Расчёты выполнять кодом, допущения — в начало
- Ссылки на нормы — только с цитатой из приложенного текста
- Не изменять файлы в папке «Архив»"""
D["d25_claude_md"] = page(f"""
<div style="margin-top:18px;border-radius:14px;overflow:hidden;border:1px solid #d9d1c4;box-shadow:0 10px 30px rgba(60,40,20,.08)">
  <div style="background:#ece6dc;padding:10px 16px;display:flex;align-items:center;gap:8px;font-size:15px;color:var(--muted)">
    <span style="width:12px;height:12px;border-radius:50%;background:#e0a090"></span><span style="width:12px;height:12px;border-radius:50%;background:#e6cf8f"></span><span style="width:12px;height:12px;border-radius:50%;background:#9fcaa0"></span>
    <span style="margin-left:10px;font-weight:600;color:var(--ink)">CLAUDE.md</span><span>— в корне рабочей папки</span></div>
  <pre style="background:#fffdf9;margin:0;padding:18px 24px;font-family:'DejaVu Sans Mono',monospace;font-size:15px;line-height:1.42;white-space:pre-wrap">{md}</pre>
</div>""", "Урок 25", "Пример файла CLAUDE.md", "Claude читает этот файл в начале каждой сессии в папке")

# 27 — подключения
cx, cy = 600, 405
nodes = [("Почта", 290, 250), ("Облачный диск", 910, 250), ("Календарь", 230, 410),
         ("Таблицы", 970, 410), ("Системы задач", 330, 565), ("Корпоративные системы", 870, 565)]
lines = "".join(
    f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" stroke="{"#c2603e" if i==5 else "#b9b0a3"}" stroke-width="2.5" {"stroke-dasharray=\"8 7\"" if i==5 else ""}/>'
    for i, (_, x, y) in enumerate(nodes))
nd = "".join(
    f'<div class="box" style="position:absolute;left:{x-115}px;top:{y-32}px;width:230px;height:64px;display:flex;align-items:center;justify-content:center;text-align:center;font-size:19px;font-weight:600;{"border:2px dashed var(--accent);background:var(--accent-soft)" if i==5 else ""}">{t}</div>'
    for i, (t, x, y) in enumerate(nodes))
D["d27_connectors"] = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>{CSS}</style></head><body><div id="card">
<div class="kicker">Урок 27</div><h1>Подключения к сервисам</h1><div class="sub">Claude получает данные из сервисов сам — без копирования и вставки</div>
<svg width="1200" height="675" style="position:absolute;left:0;top:0">{lines}</svg>
{nd}
<div style="position:absolute;left:{cx-85}px;top:{cy-85}px;width:170px;height:170px;border-radius:50%;background:var(--ink);color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:28px;font-weight:700">Claude<span style="font-size:15px;font-weight:500;color:#cfc8be;margin-top:4px">коннекторы (MCP)</span></div>
<div style="position:absolute;right:56px;top:52px;font-size:15px;color:var(--accent);font-weight:600;display:flex;align-items:center;gap:8px"><svg width="40" height="6"><line x1="0" y1="3" x2="40" y2="3" stroke="#c2603e" stroke-width="2.5" stroke-dasharray="8 7"/></svg>только по согласованию</div>
<div class="foot"><span>Курс «ИИ в работе»</span><span>Claude</span></div></div></body></html>"""

# 29 — агент и субагенты
def step(t, s, col="var(--panel)"):
    return f'<div class="box" style="width:210px;text-align:center;background:{col}"><div class="big" style="font-size:21px">{t}</div><div class="small" style="margin-top:2px">{s}</div></div>'
D["d29_agent"] = page(f"""
<div class="row" style="margin-top:30px;gap:34px;align-items:flex-start">
  <div style="flex:1">
    <span class="tag t-teal">Цикл агента</span>
    <div style="display:flex;flex-direction:column;align-items:center;margin-top:14px;position:relative">
      {step("План", "разбить задачу на шаги")}
      <div style="margin:4px 0">{ARROW_DOWN}</div>
      {step("Действие", "читать, считать, писать")}
      <div style="margin:4px 0">{ARROW_DOWN}</div>
      {step("Проверка", "сверить с задачей", "var(--accent-soft)")}
      <svg width="140" height="340" style="position:absolute;left:calc(50% + 105px);top:30px"><path d="M0 327 H70 V10 H8" fill="none" stroke="#c2603e" stroke-width="2.5" stroke-dasharray="7 6"/><path d="M16 3 L6 10 L16 17" fill="none" stroke="#c2603e" stroke-width="2.5"/></svg>
      <div style="position:absolute;left:calc(50% + 185px);top:150px;font-size:15px;color:var(--accent);font-weight:600;width:110px">ошибка — исправить и повторить</div>
    </div>
  </div>
  <div style="flex:1.15">
    <span class="tag t-acc">Субагенты</span>
    <div style="display:flex;flex-direction:column;align-items:center;margin-top:14px">
      <div class="box" style="width:300px;text-align:center;background:var(--ink);color:#fff;border-color:var(--ink)"><div class="big" style="font-size:21px">Главный агент</div><div class="small" style="color:#cfc8be;margin-top:2px">держит общую картину</div></div>
      <div class="row" style="gap:44px;margin:10px 0;font-size:15px;color:var(--muted)"><span>задача ↓</span><span>↑ только итог</span></div>
      <div class="row" style="gap:12px">
        <div class="box" style="width:170px;height:118px;text-align:center;display:flex;flex-direction:column;justify-content:center"><div style="font-weight:700;font-size:17px">Анализ протоколов</div><div class="small" style="font-size:14px">свой контекст</div></div>
        <div class="box" style="width:170px;height:118px;text-align:center;display:flex;flex-direction:column;justify-content:center"><div style="font-weight:700;font-size:17px">Поиск в нормах</div><div class="small" style="font-size:14px">свой контекст</div></div>
        <div class="box" style="width:170px;height:118px;text-align:center;display:flex;flex-direction:column;justify-content:center"><div style="font-weight:700;font-size:17px">Проверка</div><div class="small" style="font-size:14px">свой контекст</div></div>
      </div>
      <div class="small" style="margin-top:14px;text-align:center;font-size:16px">Каждому субагенту — своя роль, инструменты и модель. Независимые части выполняются параллельно.</div>
    </div>
  </div>
</div>""", "Урок 29", "Агент и субагенты")

# 30 — команда
specs = [("Технолог", "балансы, режимы"), ("Механик", "подбор оборудования"), ("Сметчик", "оценка стоимости"), ("Нормоконтролёр", "проверка по нормам")]
spec_html = "".join(f'<div style="display:flex;flex-direction:column;align-items:center;position:relative"><div style="width:2px;height:26px;background:#b9b0a3"></div><div class="box" style="width:230px;text-align:center{";border:2px solid var(--accent);background:var(--accent-soft)" if i==3 else ""}"><div class="big" style="font-size:21px">{a}</div><div class="small" style="margin-top:2px">{b}</div></div></div>' for i, (a, b) in enumerate(specs))
D["d30_team"] = page(f"""
<div style="display:flex;flex-direction:column;align-items:center;margin-top:22px">
  <div class="box" style="width:300px;text-align:center;border:2px solid var(--teal);background:var(--teal-soft)"><div class="big">Вы</div><div class="small" style="margin-top:2px">ставите задачу, утверждаете план и результат</div></div>
  <div class="row" style="gap:70px;font-size:15px;color:var(--muted);margin:4px 0"><span>задача ↓</span><span>↑ отчёт и вопросы</span></div>
  <div class="box" style="width:340px;text-align:center;background:var(--ink);color:#fff;border-color:var(--ink)"><div class="big">Агент-тимлид</div><div class="small" style="color:#cfc8be;margin-top:2px">планирует, распределяет, собирает итог</div></div>
  <div style="width:2px;height:22px;background:#b9b0a3"></div>
  <div style="position:relative;width:830px;height:2px;background:#b9b0a3"></div>
  <div class="row" style="gap:28px;align-items:flex-start;width:1060px;justify-content:space-between">{spec_html}</div>
</div>""", "Урок 30", "Команда агентов: «Claude-завод»")

# 31 — конвейер
stages = [("ТЗ", "задача и материалы", "n"), ("План", "тимлид предлагает", "n"), ("Утверждение", "человек", "h"),
          ("Работа", "агенты-исполнители", "n"), ("Проверка", "агент-проверяющий", "c"), ("Приёмка", "человек", "h"), ("Результат", "комплект документов", "r")]
def st(t, s, kind):
    style = {"h": "border:2px solid var(--teal);background:var(--teal-soft)", "c": "border:2px solid var(--accent);background:var(--accent-soft)",
             "r": "background:var(--ink);color:#fff;border-color:var(--ink)", "n": ""}[kind]
    sc = "color:#cfc8be" if kind == "r" else ""
    return f'<div class="box" style="width:132px;height:112px;padding:14px 10px;text-align:center;{style}"><div style="font-weight:700;font-size:16px">{t}</div><div class="small" style="font-size:14px;{sc}">{s}</div></div>'
sarr = '<div style="flex:none;width:22px;display:flex;justify-content:center"><svg width="20" height="16" viewBox="0 0 20 16"><path d="M1 8h14M10 2l6 6-6 6" fill="none" stroke="#8a8378" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>'
pipe = sarr.join(st(*x) for x in stages)
D["d31_pipeline"] = page(f"""
<div style="position:relative;margin-top:58px">
  <div class="row" style="justify-content:space-between">{pipe}</div>
  <svg width="1088" height="70" style="position:absolute;left:0;top:112px"><path d="M{4*154+66} 4 V46 H{3*154+66} V12" fill="none" stroke="#c2603e" stroke-width="2.5" stroke-dasharray="7 6"/><path d="M{3*154+59} 20 L{3*154+66} 9 L{3*154+73} 20" fill="none" stroke="#c2603e" stroke-width="2.5"/></svg>
  <div style="position:absolute;left:{3*154+80}px;top:166px;font-size:15px;color:var(--accent);font-weight:600">замечания — на доработку</div>
</div>
<div class="row" style="gap:16px;margin-top:92px;align-items:stretch">
  <div class="box" style="flex:1"><span class="tag t-teal">Человек</span><div class="small" style="font-size:17px;color:var(--ink)">утверждает план и принимает результат</div></div>
  <div class="box" style="flex:1"><span class="tag t-acc">Проверяющий</span><div class="small" style="font-size:17px;color:var(--ink)">отдельный агент ищет ошибки, а не соглашается</div></div>
  <div class="box" style="flex:1"><span class="tag" style="background:#efebe4;color:var(--muted)">Расход</span><div class="small" style="font-size:17px;color:var(--ink)">простые подзадачи — быстрым моделям, анализ — мощным</div></div>
</div>""", "Урок 31", "Конвейер с контролем качества", "Агенты делают, проверяющий ищет ошибки, человек утверждает")

if __name__ == "__main__":
    for name, html in D.items():
        with open(os.path.join(OUT, name + ".html"), "w", encoding="utf-8") as f:
            f.write(html)
    print(len(D), "diagrams")
