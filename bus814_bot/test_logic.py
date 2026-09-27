import os
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1:test")
os.environ.setdefault("STOP_ID", "stop__1")

from datetime import datetime
from bot import MSK, ArrivalDetector, in_active_window
from yandex_transport import Arrival, parse_arrivals, parse_scheduled

NOW = 1_800_000_000


def payload(*events):
    return {"data": {"transports": [
        {"name": "814", "type": "bus", "threads": [{"BriefSchedule": {"Events": [
            {"Scheduled": {"value": str(NOW + 900)},
             **({"Estimated": {"value": str(NOW + eta)}, "vehicleId": vid} if eta is not None else {})}
            for eta, vid in events
        ]}}]},
        {"name": "813", "type": "bus", "threads": [{"BriefSchedule": {"Events": [
            {"Estimated": {"value": str(NOW + 30)}, "vehicleId": "x"}]}}]},
    ]}}


def test_parse():
    arr = parse_arrivals(payload((400, "b"), (120, "a"), (None, None)), "814", now=NOW)
    assert [(a.eta_sec, a.vehicle_id) for a in arr] == [(120, "a"), (400, "b")]
    assert parse_arrivals(payload(), "814", now=NOW) == []
    assert parse_scheduled(payload((None, None), (120, "a")), "814", now=NOW) == [NOW + 900]


def test_detector():
    d = ArrivalDetector(60, 100)
    assert d.update([]) is None                          # автобусов нет
    assert d.update([Arrival(420, "a")]) is None         # ещё далеко
    assert d.update([Arrival(50, "a")]).vehicle_id == "a"  # подъехал
    assert d.update([Arrival(0, "a")]) is None           # без повторов
    assert d.update([Arrival(1800, "b")]) is None        # уехал, следующий далеко
    assert d.update([Arrival(40, "b")]).vehicle_id == "b"


def test_detector_missed_between_polls():
    d = ArrivalDetector(60, 100)
    assert d.update([Arrival(90, "a"), Arrival(1500, "b")]) is None
    hit = d.update([Arrival(1480, "b")])                 # "a" проскочил между опросами
    assert hit is not None and hit.vehicle_id == "a"
    assert d.update([Arrival(1460, "b")]) is None


def test_detector_without_vehicle_id():
    d = ArrivalDetector(60, 100)
    assert d.update([Arrival(45, None)]).eta_sec == 45
    assert d.update([Arrival(10, None)]) is None
    assert d.update([Arrival(1400, None)]) is None       # уже сработали, не дублируем
    assert d.update([Arrival(80, None)]) is None
    assert d.update([Arrival(1300, None)]).eta_sec == 0  # проскочил


def test_window():
    assert in_active_window(datetime(2026, 9, 28, 7, 30, tzinfo=MSK))      # пн
    assert not in_active_window(datetime(2026, 9, 28, 10, 0, tzinfo=MSK))
    assert not in_active_window(datetime(2026, 9, 27, 7, 30, tzinfo=MSK))  # вс


if __name__ == "__main__":
    test_parse(); test_detector(); test_detector_missed_between_polls(); test_detector_without_vehicle_id(); test_window(); print("OK")
