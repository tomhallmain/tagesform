import pytest

from app.utils.geo import haversine_miles

pytestmark = pytest.mark.unit


def test_haversine_miles_same_point_is_zero():
    assert haversine_miles(40.0, -75.0, 40.0, -75.0) == 0.0


def test_haversine_miles_matches_known_distance():
    """Anchorage, AK to Fairbanks, AK -- real-world distance is ~260 miles."""
    distance = haversine_miles(61.21806, -149.90028, 64.83778, -147.71639)
    assert 255 < distance < 265


def test_haversine_miles_is_symmetric():
    a = haversine_miles(40.0, -75.0, 41.0, -76.0)
    b = haversine_miles(41.0, -76.0, 40.0, -75.0)
    assert a == pytest.approx(b)
