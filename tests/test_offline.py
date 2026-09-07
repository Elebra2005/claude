"""Автономные проверки: парсинг ЦБ, аналитика, хранилище, тексты.
Сеть не нужна — XML подставляем вручную.

Запуск:  python -m tests.test_offline
"""

import os
import sys
import tempfile
from datetime import date, timedelta

os.environ.setdefault("RATES_BOT_TOKEN", "test:token")

from rates_bot import analytics, chart, formatting  # noqa: E402
from rates_bot.cbr import _parse_xml, _unit_rate  # noqa: E402
from rates_bot.dolgov import extract, to_text  # noqa: E402
from rates_bot.storage import Storage  # noqa: E402

FAILED: list[str] = []


def check(name: str, condition: bool, extra: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name} {extra}")


DAILY_XML = (
    '<?xml version="1.0" encoding="windows-1251"?>'
    '<ValCurs Date="05.09.2026" name="Foreign Currency Market">'
    "<Valute ID=\"R01235\"><NumCode>840</NumCode><CharCode>USD</CharCode>"
    "<Nominal>1</Nominal><Name>Доллар США</Name><Value>81,5043</Value>"
    "<VunitRate>81,5043</VunitRate></Valute>"
    "<Valute ID=\"R01375\"><NumCode>156</NumCode><CharCode>CNY</CharCode>"
    "<Nominal>1</Nominal><Name>Китайский юань</Name><Value>11,4321</Value>"
    "<VunitRate>11,4321</VunitRate></Valute>"
    "<Valute ID=\"R01820\"><NumCode>392</NumCode><CharCode>JPY</CharCode>"
    "<Nominal>100</Nominal><Name>Японских иен</Name><Value>55,1000</Value></Valute>"
    "</ValCurs>"
).encode("cp1251")


def test_parsing() -> None:
    print("\nПарсинг ответа ЦБ")
    root = _parse_xml(DAILY_XML)
    check("дата документа", root.get("Date") == "05.09.2026")

    by_code = {v.findtext("CharCode"): v for v in root.findall("Valute")}
    check("юань разобран", abs(_unit_rate(by_code["CNY"]) - 11.4321) < 1e-9)
    check("кириллица не побилась", by_code["CNY"].findtext("Name") == "Китайский юань")
    # У иены Nominal=100 и нет VunitRate — курс обязан делиться на номинал.
    check(
        "номинал учтён (JPY)",
        abs(_unit_rate(by_code["JPY"]) - 0.551) < 1e-9,
        f"получено {_unit_rate(by_code['JPY'])}",
    )


def build_series(values: list[float], end: date | None = None):
    end = end or date(2026, 9, 5)
    return [(end - timedelta(days=len(values) - 1 - i), v) for i, v in enumerate(values)]


def test_stats() -> None:
    print("\nСтатистика ряда")
    # 60 дней около 12,0, затем резкое падение до 11,0.
    values = [12.0 + (i % 5) * 0.02 for i in range(60)] + [11.0]
    stats = analytics.compute("CNY", build_series(values), ma_window=30, low_window=30)

    check("есть результат", stats is not None)
    check("текущее значение", abs(stats.value - 11.0) < 1e-9)
    check("падение за день отрицательное", stats.change_1d_pct < -7)
    check("минимум окна найден", stats.is_window_low)
    check("ниже средней", stats.below_ma_pct > 5)
    check("позиция у нижней границы", stats.position_90 is not None and stats.position_90 < 1)

    flat = analytics.compute("CNY", build_series([12.0] * 40), ma_window=30, low_window=30)
    check("на ровном ряду нет деления на ноль", flat.position_90 == 50.0)
    check("на ровном ряду изменение нулевое", abs(flat.change_1d_pct) < 1e-9)

    check("пустой ряд не падает", analytics.compute("CNY", [], ma_window=30, low_window=30) is None)
    single = analytics.compute("CNY", build_series([12.0]), ma_window=30, low_window=30)
    check("ряд из одного значения", single is not None and single.change_1d_pct is None)


def test_dips() -> None:
    print("\nДетектор просадок")
    values = [12.0 + (i % 5) * 0.02 for i in range(60)] + [11.0]
    stats = analytics.compute("CNY", build_series(values), ma_window=30, low_window=30)
    dips = analytics.detect(stats, daily_drop_pct=0.8, below_ma_pct=2.0)
    rules = {d.rule for d in dips}
    check("сработало падение за день", "daily_drop" in rules)
    check("сработал минимум окна", "window_low" in rules)
    check("сработала средняя", "below_ma" in rules)
    check("ключ дедупликации = дата", all(d.ref == stats.on_date.isoformat() for d in dips))

    # Рост: просадок быть не должно.
    up = analytics.compute("CNY", build_series([12.0] * 60 + [12.5]), ma_window=30, low_window=30)
    check("на росте просадок нет", analytics.detect(up, daily_drop_pct=0.8, below_ma_pct=2.0) == [])


def test_seasonality() -> None:
    print("\nСезонность")
    series = []
    value = 10.0
    for year in (2022, 2023, 2024, 2025):
        for month in range(1, 13):
            # Март дешевеет на 3%, август дорожает на 3%, прочие месяцы ровные.
            value *= 0.97 if month == 3 else (1.03 if month == 8 else 1.0)
            last_day = date(year + (month // 12), (month % 12) + 1, 1) - timedelta(days=1)
            series.append((last_day, value))

    months = analytics.monthly_seasonality(series)
    by_month = {m.month: m for m in months}
    check("посчитаны все месяцы", len(months) == 12, f"получено {len(months)}")
    check("март в минусе", by_month[3].mean_pct < -2.9)
    check("август в плюсе", by_month[8].mean_pct > 2.9)
    check("март дешевел всегда", by_month[3].share_down == 100.0)
    check("выборка по годам", by_month[3].samples == 4, f"samples={by_month[3].samples}")

    since = analytics.monthly_seasonality(series, since_year=2024)
    check("фильтр по году сузил выборку", {m.month: m for m in since}[3].samples == 2)
    check("разрыв в данных не ломает", analytics.monthly_seasonality([]) == [])


def test_storage() -> None:
    print("\nХранилище")
    with tempfile.TemporaryDirectory() as tmp:
        store = Storage(os.path.join(tmp, "sub", "test.db"))

        store.save_rates("CNY", [(date(2026, 9, 1), 11.5), (date(2026, 9, 2), 11.4)])
        store.save_rates("CNY", [(date(2026, 9, 2), 11.45)])  # перезапись
        series = store.series("CNY")
        check("две записи, дубль перезаписан", len(series) == 2)
        check("порядок по возрастанию даты", series[0][0] < series[1][0])
        check("значение обновилось", abs(series[-1][1] - 11.45) < 1e-9)
        check("latest отдаёт свежее", store.latest("CNY") == (date(2026, 9, 2), 11.45))
        check("limit режет от свежих", store.series("CNY", 1)[0][0] == date(2026, 9, 2))

        store.upsert_subscriber(777)
        check("подписчик активен", store.subscriber(777).active)
        store.set_flag(777, "alerts_enabled", False)
        check("флаг снят", store.subscriber(777).alerts_enabled is False)
        store.set_digest_time(777, 9, 30)
        check("время сводки сохранено", store.subscriber(777).digest_hour == 9)

        store.set_target(777, "CNY", 10.9)
        store.set_target(777, "CNY", 10.5)  # перезапись цели
        check("цель одна на валюту", len(store.targets(777)) == 1)
        check("цель обновлена", store.targets(777)[0][2] == 10.5)
        check("цель снимается", store.drop_target(777, "CNY"))
        check("повторное снятие — False", store.drop_target(777, "CNY") is False)

        check("первая отметка проходит", store.mark_alert(777, "CNY", "window_low", "2026-09-02"))
        check(
            "повторная отметка блокируется",
            store.mark_alert(777, "CNY", "window_low", "2026-09-02") is False,
        )
        check("другая дата проходит", store.mark_alert(777, "CNY", "window_low", "2026-09-03"))
        check("первая сводка проходит", store.mark_digest(777, date(2026, 9, 2)))
        check("вторая сводка за день блокируется", store.mark_digest(777, date(2026, 9, 2)) is False)

        store.set_flag(777, "active", False)
        check("отписанный не в рассылке", store.active_subscribers() == [])
        store.purge_old_marks(0)
        store.close()


def test_formatting() -> None:
    print("\nТексты")
    values = [12.0 + (i % 5) * 0.02 for i in range(60)] + [11.0]
    stats = analytics.compute("CNY", build_series(values), ma_window=30, low_window=30)

    text = formatting.digest(stats.on_date, [stats], None, [("CNY", 10.5)])
    check("десятичная запятая", "11,0000" in text, text[:200])
    check("дата в шапке", "05.09.2026" in text)
    check("цель показана", "CNY ≤ 10,50" in text)
    check("теги парные", text.count("<b>") == text.count("</b>"))

    alert = formatting.dip_alert(
        analytics.detect(stats, daily_drop_pct=0.8, below_ma_pct=2.0), {"CNY": stats}
    )
    check("в алерте есть заголовок", "Просадка" in alert)
    check("в алерте есть минимум окна", "минимум за 30 дней" in alert)

    seasonal = formatting.seasonality("CNY", analytics.monthly_seasonality(build_month_series()), "2022–2025")
    check("таблица сезонности в pre", "<pre>" in seasonal and "</pre>" in seasonal)
    check("есть вывод по месяцам", "Дешевле всего" in seasonal)

    check("процент со знаком", formatting.signed_pct(-1.234) == "−1,23%")
    check("процент None", formatting.signed_pct(None) == "—")
    check("шкала диапазона", len(formatting.range_bar(0.0)) == 10)
    check("шкала на 100% не выходит за край", formatting.range_bar(100.0)[-1] == "●")
    check("вердикт для низа", "дёшево" in formatting.verdict(5.0))
    # Имя валюты подставляется как есть — проверяем, что HTML не ломается.
    check("экранирование кода валюты", "&lt;" in formatting.title("<b>"))


def build_month_series():
    series = []
    value = 10.0
    for year in (2022, 2023, 2024, 2025):
        for month in range(1, 13):
            value *= 0.97 if month == 3 else 1.0
            last_day = date(year + (month // 12), (month % 12) + 1, 1) - timedelta(days=1)
            series.append((last_day, value))
    return series


def parse_page(html: str, pattern: str | None = None):
    value, candidates, _ = extract(
        to_text(html), low=5.0, high=30.0, pattern=pattern, raw=html
    )
    return value, candidates


def test_dolgov() -> None:
    """Реальную страницу Долгова отсюда не видно, поэтому гоняем парсер на
    правдоподобных вариантах вёрстки — включая ловушки."""
    print("\nПарсер курса Долгова")

    value, _ = parse_page('<div class="rate"><span>Курс юаня</span><b>12,15 ₽</b></div>')
    check("курс после слова «юань»", value == 12.15, f"получено {value}")

    value, _ = parse_page("<p>Курс: <b>12.4</b> руб. за юань</p>")
    check("курс до слова «юань»", value == 12.4, f"получено {value}")

    value, _ = parse_page('<td>CNY</td><td>11,98</td>')
    check("курс по коду CNY", value == 11.98, f"получено {value}")

    value, _ = parse_page("<div>¥ 1 = 12,07 ₽</div>")
    check("курс по символу ¥", value == 12.07, f"получено {value}")

    # Цены машин рядом с «юань» не должны победить: фильтр диапазона.
    value, _ = parse_page(
        "<div>Автомобиль за 1 250 000 рублей, оплата в юанях по курсу 12,33</div>"
    )
    check("цена авто не спутана с курсом", value == 12.33, f"получено {value}")

    # Целое число рядом проигрывает дробному — у курса всегда копейки.
    value, _ = parse_page("<div>Юань 7 дней доставки, курс 12,60 ₽</div>")
    check("дробное предпочтительнее целого", value == 12.6, f"получено {value}")

    # Скрипты выкидываются до разбора.
    value, _ = parse_page(
        '<script>var cny = 99.9; // юань</script><div>Курс юаня 12,20</div>'
    )
    check("содержимое script игнорируется", value == 12.2, f"получено {value}")

    value, candidates = parse_page("<div>Автомобили из Китая под ключ</div>")
    check("нет упоминаний — нет курса", value is None)
    check("кандидатов тоже нет", candidates == [])

    value, _ = parse_page("<div>Курс юаня 1200</div>")
    check("значение вне диапазона отброшено", value is None, f"получено {value}")

    value, _ = parse_page(
        '<div data-rate="12,88">курс</div>', pattern=r'data-rate="([\d.,]+)"'
    )
    check("ручной DOLGOV_REGEX перебивает эвристику", value == 12.88, f"получено {value}")

    value, _ = parse_page("<div>Курс юаня 12,15</div>", pattern=r"нетакого=([\d.,]+)")
    check("нерабочий regex не откатывается на эвристику", value is None)

    value, _ = parse_page(
        '<script>window.rates={"cny":12.71};</script><div>Курс юаня 9,99</div>',
        pattern=r'"cny"\s*:\s*([\d.]+)',
    )
    check("regex достаёт число из JS-блока", value == 12.71, f"получено {value}")

    text = to_text("<p>Курс&nbsp;юаня &mdash; 12,15&nbsp;₽</p>")
    check("сущности и пробелы нормализованы", "юаня" in text and "12,15" in text, text)


def test_chart() -> None:
    print("\nГрафик")
    today = date.today()
    cbr = [(today - timedelta(days=i), 12.0 - i * 0.01) for i in range(60, -1, -1)]
    dolgov = [(day, value * 1.03) for day, value in cbr[-20:]]

    png = chart.render(cbr, dolgov, days=60)
    check("PNG отрисован", png is not None and png[:8] == b"\x89PNG\r\n\x1a\n")
    check("размер разумный", 10_000 < len(png) < 900_000, f"{len(png)} байт")

    solo = chart.render(cbr, [], days=60)
    check("без данных Долгова тоже рисует", solo is not None and solo[:4] == b"\x89PNG")

    one_point = chart.render(cbr, [(today, 12.5)], days=60)
    check("одна точка Долгова не ломает", one_point is not None)

    check("пустые данные — None", chart.render([], [], days=60) is None)


def main() -> int:
    test_parsing()
    test_stats()
    test_dips()
    test_seasonality()
    test_storage()
    test_formatting()
    test_dolgov()
    test_chart()
    print()
    if FAILED:
        print(f"ПРОВАЛЕНО: {len(FAILED)} — {', '.join(FAILED)}")
        return 1
    print("Все проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
