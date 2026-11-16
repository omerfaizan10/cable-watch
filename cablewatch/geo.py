"""Geo math: great-circle distance, bearings, point-to-polyline distance, segment crossing,
and an H3 index that turns "which cables are near this fix?" into a set lookup.

Distances below a few tens of km are computed in a local equirectangular projection
centred on the query point. At Baltic latitudes (54 to 66 N) the error of that
approximation over 5 km is well under 1 m, far below AIS position noise (~10 m).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import h3

EARTH_R_M = 6_371_008.8
M_PER_NM = 1852.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_M * math.asin(min(1.0, math.sqrt(a)))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def angle_diff_deg(a: float, b: float) -> float:
    """Smallest signed difference b - a in degrees, in (-180, 180]."""
    d = (b - a + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def circular_std_deg(angles: list[float]) -> float:
    """Circular standard deviation in degrees (0 for identical angles)."""
    if not angles:
        return 0.0
    s = sum(math.sin(math.radians(a)) for a in angles) / len(angles)
    c = sum(math.cos(math.radians(a)) for a in angles) / len(angles)
    r = min(1.0, math.hypot(s, c))
    if r <= 1e-12:
        return 180.0
    return math.degrees(math.sqrt(-2.0 * math.log(r)))


def to_local_xy(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    """Metres east/north of (lat0, lon0) in an equirectangular projection."""
    x = math.radians(lon - lon0) * math.cos(math.radians(lat0)) * EARTH_R_M
    y = math.radians(lat - lat0) * EARTH_R_M
    return x, y


def point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def point_polyline_distance_m(lat: float, lon: float, line: list[tuple[float, float]]) -> float:
    """Distance in metres from a point to a polyline given as [(lat, lon), ...]."""
    if len(line) == 1:
        return haversine_m(lat, lon, line[0][0], line[0][1])
    best = math.inf
    prev = to_local_xy(lat, lon, *line[0])
    for la, lo in line[1:]:
        cur = to_local_xy(lat, lon, la, lo)
        d = point_segment_distance(0.0, 0.0, prev[0], prev[1], cur[0], cur[1])
        if d < best:
            best = d
        prev = cur
    return best


def _orient(ax, ay, bx, by, cx, cy) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def segments_cross(p1, p2, q1, q2) -> bool:
    """Proper intersection test for 2D segments p1p2 and q1q2 (touching counts)."""
    o1 = _orient(*p1, *p2, *q1)
    o2 = _orient(*p1, *p2, *q2)
    o3 = _orient(*q1, *q2, *p1)
    o4 = _orient(*q1, *q2, *p2)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0) and o1 != 0 and o2 != 0:
        return True
    eps = 1e-9
    def on_seg(a, b, c):
        return min(a[0], b[0]) - eps <= c[0] <= max(a[0], b[0]) + eps and min(a[1], b[1]) - eps <= c[1] <= max(a[1], b[1]) + eps
    if abs(o1) < eps and on_seg(p1, p2, q1):
        return True
    if abs(o2) < eps and on_seg(p1, p2, q2):
        return True
    if abs(o3) < eps and on_seg(q1, q2, p1):
        return True
    if abs(o4) < eps and on_seg(q1, q2, p2):
        return True
    return False


def track_crosses_polyline(a: tuple[float, float], b: tuple[float, float], line: list[tuple[float, float]]) -> bool:
    """Does the ship's move from fix a to fix b (lat, lon) cross the cable polyline?"""
    lat0, lon0 = a
    pa = (0.0, 0.0)
    pb = to_local_xy(lat0, lon0, *b)
    prev = to_local_xy(lat0, lon0, *line[0])
    for la, lo in line[1:]:
        cur = to_local_xy(lat0, lon0, la, lo)
        if segments_cross(pa, pb, prev, cur):
            return True
        prev = cur
    return False


def densify(line: list[tuple[float, float]], step_m: float) -> list[tuple[float, float]]:
    """Insert points so no gap exceeds step_m (linear in lat/lon, fine at these scales)."""
    out = [line[0]]
    for (la1, lo1), (la2, lo2) in zip(line, line[1:]):
        d = haversine_m(la1, lo1, la2, lo2)
        n = max(1, int(math.ceil(d / step_m)))
        for i in range(1, n + 1):
            t = i / n
            out.append((la1 + (la2 - la1) * t, lo1 + (lo2 - lo1) * t))
    return out


@dataclass
class Cable:
    cable_id: str
    name: str
    kind: str  # "power" or "telecom"
    source: str  # e.g. "EMODnet emodnet:bshcontiscables"
    line: list[tuple[float, float]]  # (lat, lon)

    @property
    def endpoints(self) -> list[tuple[float, float]]:
        return [self.line[0], self.line[-1]]


@dataclass
class CableIndex:
    """H3 cells covering each cable segment's buffer. A fix whose cell is in the index is a
    candidate; the exact distance is then computed only against the segments registered in
    that cell, so a 2,000-vertex pipeline costs the same per fix as a 2-vertex cable."""

    cables: dict[str, Cable]
    buffer_m: float
    res: int = 8
    cells: dict[str, dict[str, set[int]]] = field(default_factory=dict)  # cell -> cable_id -> segment idx

    @classmethod
    def build(cls, cables: list[Cable], buffer_m: float, res: int = 8) -> "CableIndex":
        idx = cls({c.cable_id: c for c in cables}, buffer_m, res)
        edge = h3.average_hexagon_edge_length(res, "m")
        # A hexagon's circumradius equals its edge length; ring k reaches ~1.5*k*edge.
        k = int(math.ceil((buffer_m + edge) / (1.5 * edge))) + 1
        disk_cache: dict[str, list[str]] = {}
        for c in cables:
            for i, (a, b) in enumerate(zip(c.line, c.line[1:])):
                seen: set[str] = set()
                for la, lo in densify([a, b], edge):
                    base = h3.latlng_to_cell(la, lo, res)
                    if base in seen:
                        continue
                    seen.add(base)
                    disk = disk_cache.get(base)
                    if disk is None:
                        disk = disk_cache[base] = h3.grid_disk(base, k)
                    for cell in disk:
                        idx.cells.setdefault(cell, {}).setdefault(c.cable_id, set()).add(i)
        return idx

    def _cell(self, lat: float, lon: float) -> dict[str, set[int]]:
        return self.cells.get(h3.latlng_to_cell(lat, lon, self.res), {})

    def candidates(self, lat: float, lon: float) -> set[str]:
        return set(self._cell(lat, lon))

    def candidate_segments(self, lat: float, lon: float) -> dict[str, set[int]]:
        return self._cell(lat, lon)

    def nearest(self, lat: float, lon: float) -> tuple[str | None, float]:
        """Nearest cable within the buffer, or (None, inf)."""
        best_id, best_d = None, math.inf
        cell = self._cell(lat, lon)
        for cid in sorted(cell):
            line = self.cables[cid].line
            for i in cell[cid]:
                ax, ay = to_local_xy(lat, lon, *line[i])
                bx, by = to_local_xy(lat, lon, *line[i + 1])
                d = point_segment_distance(0.0, 0.0, ax, ay, bx, by)
                if d < best_d or (d == best_d and best_id is not None and cid < best_id):
                    best_id, best_d = cid, d
        if best_d <= self.buffer_m:
            return best_id, best_d
        return None, math.inf

    def crossed(self, a: tuple[float, float], b: tuple[float, float]) -> list[str]:
        """Cables whose registered segments the move a -> b crosses."""
        segs: dict[str, set[int]] = {}
        for cid, ix in self._cell(*a).items():
            segs.setdefault(cid, set()).update(ix)
        for cid, ix in self._cell(*b).items():
            segs.setdefault(cid, set()).update(ix)
        out = []
        pa = (0.0, 0.0)
        pb = to_local_xy(a[0], a[1], *b)
        for cid in sorted(segs):
            line = self.cables[cid].line
            for i in sorted(segs[cid]):
                q1 = to_local_xy(a[0], a[1], *line[i])
                q2 = to_local_xy(a[0], a[1], *line[i + 1])
                if segments_cross(pa, pb, q1, q2):
                    out.append(cid)
                    break
        return out

    def distance_to_landing_m(self, cable_id: str, lat: float, lon: float) -> float:
        return min(haversine_m(lat, lon, la, lo) for la, lo in self.cables[cable_id].endpoints)


def deg_to_dm(value: float, is_lat: bool) -> str:
    """Format decimal degrees as degrees and decimal minutes, chart style: 55°12.345'N."""
    hemi = ("N" if value >= 0 else "S") if is_lat else ("E" if value >= 0 else "W")
    v = abs(value)
    d = int(v)
    m = (v - d) * 60
    if round(m, 3) >= 60:
        d, m = d + 1, 0.0
    width = 2 if is_lat else 3
    return f"{d:0{width}d}°{m:06.3f}'{hemi}"
