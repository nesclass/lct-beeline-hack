import pytest

from app import scenarios


def test_three_scenarios_are_registered():
    ids = {s["id"] for s in scenarios.listing()}
    assert ids == {"normal", "peak", "short-staffed"}


def test_listing_carries_counts_and_titles():
    normal = next(s for s in scenarios.listing() if s["id"] == "normal")
    assert normal["engineers"] == 12
    assert normal["requests"] == 59
    assert normal["title"]
    assert normal["description"]


def test_peak_has_more_requests_than_normal():
    by_id = {s["id"]: s for s in scenarios.listing()}
    assert by_id["peak"]["requests"] > by_id["normal"]["requests"]


def test_short_staffed_has_fewer_engineers():
    by_id = {s["id"]: s for s in scenarios.listing()}
    assert by_id["short-staffed"]["engineers"] < by_id["normal"]["engineers"]


def test_load_returns_full_dataset():
    ds = scenarios.load("normal")
    assert {"config", "dictionaries", "engineers", "requests", "events"} <= set(ds)
    assert ds["config"]["weights"] == {"P": 10000, "F": 60, "G": 15, "urgent_multiplier": 3}


def test_request_ids_are_unique_in_every_scenario():
    for s in scenarios.listing():
        ids = [r["id"] for r in scenarios.load(s["id"])["requests"]]
        assert len(ids) == len(set(ids)), s["id"]


def test_unknown_scenario_raises_key_error():
    with pytest.raises(KeyError):
        scenarios.load("нет-такого")


@pytest.mark.parametrize("bad", ["../secret", "normal/../../etc/passwd", "", "NORMAL", "a b", "normal\n"])
def test_identifier_must_be_a_plain_name(bad):
    """`scenario` приходит из тела запроса и становится именем файла — и здесь, и в кэше матриц."""
    with pytest.raises(KeyError):
        scenarios.load(bad)


@pytest.mark.parametrize("bad", ["../secret", "normal/../../etc/passwd", "", "NORMAL", "a b", "normal\n"])
def test_identifier_is_rejected_before_touching_the_filesystem(bad):
    """Имя отвергается самой проверкой, а не тем, что такого файла не нашлось."""
    with pytest.raises(KeyError):
        scenarios._path(bad)


def test_listing_counts_districts_and_names_the_area(client):
    rows = {r["id"]: r for r in client.get("/api/scenarios").json()}
    assert rows["normal"]["area"] == "ЮАО"
    assert rows["normal"]["districts"] >= 5
    assert rows["normal"]["uploaded"] is False
