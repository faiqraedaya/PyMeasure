"""Unit tests for pymeasure.core.geometry (pure maths, no Qt required).

Run with ``pytest`` from the repo root, or directly: ``python -m tests.test_geometry``.
"""
import math

from pymeasure.core.geometry import (
    angle_deg, closest_point_on_segment, dist_point_to_segment, distance,
    point_in_polygon, polygon_area, polyline_length, snap_to_cardinal,
)

SQUARE = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]


def test_distance():
    assert distance(0, 0, 3, 4) == 5.0


def test_dist_point_to_segment_perpendicular():
    assert dist_point_to_segment(2, 3, 0, 0, 4, 0) == 3.0


def test_dist_point_to_segment_clamps_to_endpoint():
    # Projection falls before A, so the nearest point is A itself.
    assert dist_point_to_segment(-3, 4, 0, 0, 4, 0) == 5.0


def test_dist_point_to_segment_degenerate():
    # Zero-length segment → distance to the single point (√13).
    assert math.isclose(dist_point_to_segment(3, 4, 1, 1, 1, 1), math.hypot(2, 3))


def test_closest_point_on_segment_midpoint():
    assert closest_point_on_segment(2, 5, 0, 0, 4, 0) == (2.0, 0.0)


def test_closest_point_on_segment_clamps():
    assert closest_point_on_segment(99, 0, 0, 0, 4, 0) == (4.0, 0.0)


def test_closest_point_on_segment_degenerate():
    assert closest_point_on_segment(2, 5, 1, 1, 1, 1) == (1.0, 1.0)


def test_point_in_polygon_inside():
    assert point_in_polygon(2, 2, SQUARE) is True


def test_point_in_polygon_outside():
    assert point_in_polygon(5, 5, SQUARE) is False


def test_polygon_area_square():
    assert polygon_area(SQUARE) == 16.0


def test_polygon_area_triangle():
    assert polygon_area([(0, 0), (4, 0), (0, 3)]) == 6.0


def test_polygon_area_winding_independent():
    assert polygon_area(list(reversed(SQUARE))) == 16.0


def test_polygon_area_too_few_points():
    assert polygon_area([(0, 0), (1, 1)]) == 0.0


def test_polyline_length():
    assert polyline_length([(0, 0), (3, 4), (3, 4)]) == 5.0


def test_polyline_length_single_point():
    assert polyline_length([(1, 1)]) == 0.0


def test_angle_right():
    assert math.isclose(angle_deg((1, 0), (0, 0), (0, 1)), 90.0)


def test_angle_straight():
    assert math.isclose(angle_deg((-1, 0), (0, 0), (1, 0)), 180.0)


def test_angle_degenerate():
    assert angle_deg((0, 0), (0, 0), (1, 0)) == 0.0


def test_snap_to_cardinal_horizontal():
    sx, sy = snap_to_cardinal(0, 0, 10, 1)  # mostly +x → snaps to the x-axis
    assert math.isclose(sx, math.hypot(10, 1))
    assert math.isclose(sy, 0.0, abs_tol=1e-9)


def test_snap_to_cardinal_vertical():
    sx, sy = snap_to_cardinal(0, 0, 1, -10)  # mostly -y → snaps to the y-axis
    assert math.isclose(sx, 0.0, abs_tol=1e-9)
    assert math.isclose(sy, -math.hypot(1, 10))


def _run():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"{len(tests)} geometry tests passed")


if __name__ == "__main__":
    _run()
