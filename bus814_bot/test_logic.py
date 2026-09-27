import os
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1:test")
os.environ.setdefault("STOP_ID", "stop__1")

from datetime import datetime
from bot import MSK, DepartureDetector, in_active_window
from yandex_transport import Arrival, parse_arrivals

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


def test_detector():
    d = DepartureDetector(180)
    assert d.update([]) is None                         # стоит на конечной
    assert d.update([Arrival(600, "a")]) is None        # ещё далеко
    assert d.update([Arrival(170, "a")]).vehicle_id == "a"  # тронулся
    assert d.update([Arrival(90, "a")]) is None          # без повторов
    assert d.update([Arrival(20, "a"), Arrival(150, "b")]) is None
    assert d.update([Arrival(140, "b")]).vehicle_id == "b"  # следующий
    assert d.update([]) is None
    assert d.update([Arrival(100, None)]).eta_sec == 100  # без vehicleId
    assert d.update([Arrival(50, None)]) is None


def test_window():
    assert in_active_window(datetime(2026, 9, 28, 7, 30, tzinfo=MSK))      # пн
    assert not in_active_window(datetime(2026, 9, 28, 10, 0, tzinfo=MSK))
    assert not in_active_window(datetime(2026, 9, 27, 7, 30, tzinfo=MSK))  # вс


if __name__ == "__main__":
    test_parse(); test_detector(); test_window(); print("OK")
