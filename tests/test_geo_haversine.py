from app.geo.haversine import Haversine, haversine_km

ORE = (55.622, 37.712)          # Орехово-Борисово Северное
BIR = (55.590, 37.675)          # Бирюлёво Восточное


def test_diagonal_is_zero():
    m = Haversine().matrix({"A": ORE, "B": BIR})
    assert m["km"][("A", "A")] == 0.0
    assert m["min"][("A", "A", "car")] == 0


def test_one_degree_of_latitude_is_111_km():
    assert 111.0 < haversine_km((55.0, 37.0), (56.0, 37.0)) < 111.4


def test_detour_factor_applies():
    straight = haversine_km(ORE, BIR)
    m = Haversine(detour=1.3).matrix({"A": ORE, "B": BIR})
    assert abs(m["km"][("A", "B")] - straight * 1.3) < 1e-9


def test_car_is_faster_than_foot():
    m = Haversine().matrix({"A": ORE, "B": BIR})
    assert m["min"][("A", "B", "car")] < m["min"][("A", "B", "foot")]


def test_minutes_are_integers():
    m = Haversine().matrix({"A": ORE, "B": BIR})
    assert all(isinstance(v, int) for v in m["min"].values())


def test_line_between_two_points_is_a_straight_segment():
    assert Haversine().line(ORE, BIR, "foot") == [ORE, BIR]
