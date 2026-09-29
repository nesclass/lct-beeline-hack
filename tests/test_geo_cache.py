import pytest

from app.geo import cache
from app.geo.haversine import Haversine

A = (55.622, 37.712)
B = (55.590, 37.675)
POINTS = {"E01": A, "R001": B}


@pytest.fixture
def tmp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DIR", tmp_path)
    monkeypatch.setattr(cache, "_memo", {})
    return tmp_path


class Counting:
    """Провайдер, считающий обращения к себе; source — как назвать полученную матрицу."""

    def __init__(self, source="haversine"):
        self.calls = 0
        self.source = source
        self.inner = Haversine()

    def matrix(self, points):
        self.calls += 1
        return {**self.inner.matrix(points), "source": self.source}


def test_key_changes_when_coordinates_change():
    assert cache.key(POINTS) != cache.key({"E01": A, "R001": (55.6, 37.7)})


def test_key_ignores_insertion_order():
    assert cache.key(POINTS) == cache.key({"R001": B, "E01": A})


def test_round_trip_preserves_values(tmp_dir):
    m = Haversine().matrix(POINTS)
    cache.save("demo", POINTS, m)
    back = cache.load("demo", POINTS)
    assert back["km"] == m["km"]
    assert back["min"] == m["min"]
    assert back["source"] == "haversine"


def test_load_returns_none_for_other_coordinates(tmp_dir):
    cache.save("demo", POINTS, Haversine().matrix(POINTS))
    assert cache.load("demo", {"E01": A, "R001": (55.6, 37.7)}) is None


def test_get_computes_once(tmp_dir):
    p = Counting()
    first = cache.get("demo", POINTS, p)
    second = cache.get("demo", POINTS, p)
    assert p.calls == 1
    assert first["min"] == second["min"]


def test_estimate_is_not_written_to_disk(tmp_dir):
    """Оценка по прямой — это временный отказ OSRM, а не ответ: на диск её класть нельзя,
    иначе сценарий навсегда останется без дорог."""
    cache.get("demo", POINTS, Counting())
    assert not (tmp_dir / "demo.json").exists()


def test_estimate_is_remembered_in_memory(tmp_dir):
    """Без памяти процесса каждый GET при заблокированном OSRM ждал бы таймаут."""
    p = Counting()
    cache.get("demo", POINTS, p)
    cache.get("demo", POINTS, p)
    assert p.calls == 1


def test_osrm_matrix_is_written_to_disk(tmp_dir):
    cache.get("demo", POINTS, Counting("osrm"))
    back = cache.load("demo", POINTS)
    assert back is not None and back["source"] == "osrm"


def test_corrupt_file_is_treated_as_missing(tmp_dir):
    (tmp_dir / "demo.json").write_text("{не json", encoding="utf-8")
    assert cache.load("demo", POINTS) is None
    p = Counting("osrm")
    assert cache.get("demo", POINTS, p)["source"] == "osrm"
    assert p.calls == 1


def test_file_without_tables_is_treated_as_missing(tmp_dir):
    (tmp_dir / "demo.json").write_text('{"key": "%s"}' % cache.key(POINTS), encoding="utf-8")
    assert cache.load("demo", POINTS) is None


def test_save_leaves_no_temporary_files(tmp_dir):
    cache.save("demo", POINTS, Counting("osrm").matrix(POINTS))
    assert [f.name for f in tmp_dir.iterdir()] == ["demo.json"]


def test_concurrent_saves_do_not_trip_over_each_other(tmp_dir):
    """Два запроса на холодном кэше пишут одновременно: общий временный файл уводил
    из-под второго писателя его же файл, и тот падал на os.replace."""
    import threading
    m = {**Haversine().matrix(POINTS), "source": "osrm"}
    errors = []

    def write():
        try:
            for _ in range(100):
                cache.save("demo", POINTS, m)
        except Exception as ex:          # noqa: BLE001 — ловим любое, чтобы тест его показал
            errors.append(ex)

    threads = [threading.Thread(target=write) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors[:1]
    assert cache.load("demo", POINTS) is not None
    assert not list(tmp_dir.glob("*.tmp*")), "временные файлы остались"


def test_estimate_left_on_disk_by_older_code_is_not_trusted(tmp_dir):
    """Кэш, записанный до правила «на диск только OSRM», иначе держал бы сценарий
    на оценке по прямой вечно."""
    cache.save("demo", POINTS, {**Haversine().matrix(POINTS), "source": "haversine"})
    prov = Counting(source="osrm")
    assert cache.get("demo", POINTS, prov)["source"] == "osrm"
    assert prov.calls == 1
