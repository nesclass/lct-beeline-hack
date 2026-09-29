from app.geo.osrm import Osrm

A = (55.622, 37.712)
B = (55.590, 37.675)
POINTS = {"E01": A, "R001": B}


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeHttp:
    """Подставной HTTP: отдаёт заранее заданные ответы, помнит запросы."""

    def __init__(self, payload=None, boom=False):
        self.payload = payload
        self.boom = boom
        self.urls = []

    def get(self, url, params=None, timeout=None):
        self.urls.append(url)
        if self.boom:
            raise OSError("connection refused")
        return Response(self.payload)


TABLE = {"durations": [[0, 900], [780, 0]], "distances": [[0, 7000], [6800, 0]]}


def test_car_minutes_come_from_osrm():
    m = Osrm(http=FakeHttp(TABLE)).matrix(POINTS)
    assert m["min"][("E01", "R001", "car")] == 15
    assert m["min"][("R001", "E01", "car")] == 13
    assert m["source"] == "osrm"


def test_kilometres_come_from_osrm():
    m = Osrm(http=FakeHttp(TABLE)).matrix(POINTS)
    assert abs(m["km"][("E01", "R001")] - 7.0) < 1e-9


def test_other_modes_use_road_distance():
    m = Osrm(http=FakeHttp(TABLE)).matrix(POINTS)
    # пешком по дороге 7 км при 5 км/ч — 84 минуты
    assert m["min"][("E01", "R001", "foot")] == 84


def test_falls_back_when_osrm_is_down():
    m = Osrm(http=FakeHttp(boom=True)).matrix(POINTS)
    assert m["source"] == "haversine"
    assert m["min"][("E01", "R001", "car")] > 0


def test_falls_back_when_the_table_is_the_wrong_size():
    """OSRM ответил 200, но таблица не той размерности — тоже беда, тоже откат."""
    m = Osrm(http=FakeHttp({"durations": [[0]], "distances": [[0]]})).matrix(POINTS)
    assert m["source"] == "haversine"
    assert m["min"][("E01", "R001", "car")] > 0


def test_falls_back_when_the_answer_has_no_table():
    m = Osrm(http=FakeHttp({"code": "Ok"})).matrix(POINTS)
    assert m["source"] == "haversine"
    assert m["min"][("E01", "R001", "car")] > 0


def test_table_is_requested_once():
    http = FakeHttp(TABLE)
    Osrm(http=http).matrix(POINTS)
    assert len(http.urls) == 1
    assert "/table/v1/driving/" in http.urls[0]


def test_line_is_decoded_from_geojson():
    route = {"routes": [{"geometry": {"coordinates": [[37.712, 55.622], [37.675, 55.590]]}}]}
    assert Osrm(http=FakeHttp(route)).line(A, B, "car") == [A, B]


def test_line_falls_back_to_straight_segment():
    assert Osrm(http=FakeHttp(boom=True)).line(A, B, "car") == [A, B]


def test_line_for_non_car_does_not_call_osrm():
    http = FakeHttp(None)
    assert Osrm(http=http).line(A, B, "foot") == [A, B]
    assert http.urls == []
