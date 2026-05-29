"""Pure geometry and measurement maths.

No Qt, no I/O. Every function operates on plain floats and ``(x, y)`` sequences
so the measurement logic can be unit-tested without spinning up a GUI. The
viewer adapts its ``QPointF`` values to these signatures at the call sites.
"""
import math
from typing import Sequence, Tuple

Point = Tuple[float, float]


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    """Euclidean distance between two points."""
    return math.hypot(bx - ax, by - ay)


def dist_point_to_segment(px: float, py: float,
                          ax: float, ay: float,
                          bx: float, by: float) -> float:
    """Shortest distance from point P to the segment A→B."""
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def closest_point_on_segment(px: float, py: float,
                             ax: float, ay: float,
                             bx: float, by: float) -> Point:
    """Projection of P onto segment A→B, clamped to the endpoints."""
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if not denom:
        return ax, ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return ax + t * dx, ay + t * dy


def point_in_polygon(px: float, py: float, poly: Sequence[Point]) -> bool:
    """Ray-casting point-in-polygon test (even-odd rule)."""
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def polygon_area(poly: Sequence[Point]) -> float:
    """Unsigned polygon area via the shoelace formula (0.0 for < 3 vertices)."""
    n = len(poly)
    if n < 3:
        return 0.0
    acc = 0.0
    x0, y0 = poly[-1]
    for x1, y1 in poly:
        acc += x0 * y1 - x1 * y0
        x0, y0 = x1, y1
    return abs(acc) / 2.0


def polyline_length(poly: Sequence[Point]) -> float:
    """Total length of an open polyline (0.0 for < 2 vertices)."""
    return sum(
        math.hypot(poly[i + 1][0] - poly[i][0], poly[i + 1][1] - poly[i][1])
        for i in range(len(poly) - 1)
    )


def angle_deg(p1: Point, vertex: Point, p2: Point) -> float:
    """Angle in degrees at ``vertex`` between the rays to ``p1`` and ``p2``.

    Returns 0.0 for degenerate input (a zero-length ray).
    """
    v1x, v1y = p1[0] - vertex[0], p1[1] - vertex[1]
    v2x, v2y = p2[0] - vertex[0], p2[1] - vertex[1]
    mag = math.hypot(v1x, v1y) * math.hypot(v2x, v2y)
    if mag <= 0.0:
        return 0.0
    cos_t = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / mag))
    return math.degrees(math.acos(cos_t))


def snap_to_cardinal(bx: float, by: float, px: float, py: float) -> Point:
    """Snap P to the nearest 0/90/180/270° direction from base B, keeping its distance."""
    dx, dy = px - bx, py - by
    snapped = round(math.atan2(dy, dx) / (math.pi / 2)) * (math.pi / 2)
    dist = math.hypot(dx, dy)
    return bx + dist * math.cos(snapped), by + dist * math.sin(snapped)
