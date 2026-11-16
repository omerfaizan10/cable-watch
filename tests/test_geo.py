import math

from cablewatch.geo import (
    angle_diff_deg, circular_std_deg, deg_to_dm, haversine_m, initial_bearing_deg,
    point_polyline_distance_m, segments_cross, track_crosses_polyline,
)
from conftest import TEST_CABLE


def test_haversine_one_degree_latitude():
    # One degree of latitude on the mean-radius sphere is 111.195 km.
    assert abs(haversine_m(55.0, 15.0, 56.0, 15.0) - 111_195) < 5


def test_haversine_longitude_shrinks_with_cos_lat():
    d = haversine_m(55.0, 15.0, 55.0, 16.0)
    assert abs(d - 111_195 * math.cos(math.radians(55.0))) < 150


def test_bearing_cardinal():
    assert abs(initial_bearing_deg(55, 15, 56, 15) - 0) < 1e-6
    assert abs(initial_bearing_deg(55, 15, 55, 16) - 90) < 0.5
    assert abs(initial_bearing_deg(55, 15, 54, 15) - 180) < 1e-6


def test_angle_diff_wraps():
    assert angle_diff_deg(350, 10) == 20
    assert angle_diff_deg(10, 350) == -20
    assert angle_diff_deg(0, 180) == 180


def test_circular_std():
    assert circular_std_deg([90, 90, 90]) < 1e-6
    assert circular_std_deg([359, 1]) < 2  # wraps across north, not 179
    assert circular_std_deg([0, 90, 180, 270]) == 180.0


def test_point_polyline_distance_against_haversine():
    # 0.01 deg of longitude east of the cable at 55.1 N
    d = point_polyline_distance_m(55.1, 15.01, TEST_CABLE.line)
    assert abs(d - haversine_m(55.1, 15.0, 55.1, 15.01)) < 1.0


def test_point_beyond_end_measures_to_endpoint():
    d = point_polyline_distance_m(55.5, 15.0, TEST_CABLE.line)
    assert abs(d - haversine_m(55.5, 15.0, 55.4, 15.0)) < 1.0


def test_segments_cross():
    assert segments_cross((0, 0), (2, 2), (0, 2), (2, 0))
    assert not segments_cross((0, 0), (1, 1), (2, 2), (3, 0))
    assert segments_cross((0, 0), (2, 0), (1, 0), (1, 5))  # touching counts


def test_track_crossing_cable():
    assert track_crosses_polyline((55.1, 14.99), (55.1, 15.01), TEST_CABLE.line)
    assert not track_crosses_polyline((55.1, 15.01), (55.1, 15.02), TEST_CABLE.line)
    assert not track_crosses_polyline((55.5, 14.99), (55.5, 15.01), TEST_CABLE.line)  # past the end


def test_deg_to_dm():
    assert deg_to_dm(55.5, True) == "55°30.000'N"
    assert deg_to_dm(-12.25, False) == "012°15.000'W"
    assert deg_to_dm(14.999999, False) == "015°00.000'E"


def test_index_candidates_cover_buffer(index):
    # Points just inside the 1.5 km buffer must be candidates and be measured as near.
    for dlon in (0.0, 0.01, 0.02):  # 0.02 deg ~ 1.27 km at 55 N
        cid, d = index.nearest(55.1, 15.0 + dlon)
        assert cid == "test#0" and d < 1500
    cid, _ = index.nearest(55.1, 15.05)  # ~3.2 km away
    assert cid is None
