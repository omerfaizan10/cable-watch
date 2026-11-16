"""Per-vessel state and the four behavior rules.

A flag means "behavior consistent with anchor drag" near a cable. It is a lead for a
human analyst, never a finding of fault.
"""
from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass, field

from .config import Config
from .geo import (
    CableIndex,
    angle_diff_deg,
    circular_std_deg,
    haversine_m,
)
from .schema import Position

RULE_LABELS = {
    "sog_drop": "Sharp speed drop over cable",
    "loiter": "Slow dwell over cable",
    "drag_signature": "Slow, erratic course over cable",
    "repeat_crossing": "Repeated crossing of same cable",
}


@dataclass
class Alert:
    ts: int
    mmsi: int
    imo: str
    name: str
    ship_type: str
    rule: str
    cable_id: str
    cable_name: str
    lat: float
    lon: float
    sog: float | None
    distance_m: float
    detail: str

    @property
    def alert_id(self) -> str:
        return f"{self.mmsi}-{self.rule}-{self.cable_id}-{self.ts}"

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["alert_id"] = self.alert_id
        d["label"] = RULE_LABELS[self.rule]
        return d


@dataclass
class VesselState:
    fixes: deque = field(default_factory=deque)  # (Position, cable_id|None, dist_m) over the drag/drop horizon
    last: Position | None = None
    dwell_start: dict[str, int] = field(default_factory=dict)  # cable_id -> ts when slow dwell began
    crossings: dict[str, deque] = field(default_factory=dict)  # cable_id -> deque of crossing ts
    last_alert: dict[tuple[str, str], int] = field(default_factory=dict)


def vessel_in_scope(p: Position, cfg: Config) -> bool:
    if p.mobile_type not in cfg.mobile_types:
        return False
    if p.ship_type in cfg.excluded_ship_types:
        return False
    if p.length is not None and p.length > 0 and p.length < cfg.min_length_m:
        return False
    return True


class RuleEngine:
    AGNOSTIC = "(any position)"

    def __init__(self, index: CableIndex | None, cfg: Config):
        """index=None runs the cable-agnostic mode: speed-drop and drag-signature rules are
        evaluated everywhere (loiter and crossing need a cable and are skipped). It exists to
        test the behavior rules on incidents whose cable is missing from the open route data."""
        self.index = index
        self.cfg = cfg
        self.horizon_ms = max(cfg.drop_baseline_window_ms[0], cfg.drag_window_ms)

    def _emit(self, st: VesselState, p: Position, rule: str, cable_id: str, dist: float, detail: str) -> Alert | None:
        key = (rule, cable_id)
        prev = st.last_alert.get(key)
        if prev is not None and p.ts - prev < self.cfg.alert_cooldown_ms:
            return None
        st.last_alert[key] = p.ts
        return Alert(
            ts=p.ts, mmsi=p.mmsi, imo=p.imo, name=p.name, ship_type=p.ship_type, rule=rule,
            cable_id=cable_id, cable_name=self.index.cables[cable_id].name if self.index else self.AGNOSTIC,
            lat=p.lat, lon=p.lon, sog=p.sog, distance_m=round(dist, 1), detail=detail,
        )

    def step(self, st: VesselState, p: Position) -> list[Alert]:
        """Advance one vessel by one in-order, quality-checked fix."""
        cfg = self.cfg
        alerts: list[Alert] = []
        if self.index is None:
            cable_id, dist = "ANY", 0.0
        else:
            cable_id, dist = self.index.nearest(p.lat, p.lon)
            if cable_id is not None and self.index.distance_to_landing_m(cable_id, p.lat, p.lon) < cfg.landing_exclusion_m:
                cable_id, dist = None, float("inf")

        # Repeated crossing: test the move from the previous fix against candidate cables.
        prev = st.last
        if prev is not None and self.index is not None:
            for cid in self.index.crossed((prev.lat, prev.lon), (p.lat, p.lon)):
                if self.index.distance_to_landing_m(cid, p.lat, p.lon) < cfg.landing_exclusion_m:
                    continue
                dq = st.crossings.setdefault(cid, deque())
                if dq and p.ts - dq[-1] < cfg.cross_min_gap_ms:
                    continue
                dq.append(p.ts)
                while dq and p.ts - dq[0] > cfg.cross_window_ms:
                    dq.popleft()
                if len(dq) >= cfg.cross_min_count:
                    a = self._emit(st, p, "repeat_crossing", cid, 0.0,
                                   f"{len(dq)} crossings in {round((dq[-1] - dq[0]) / 3_600_000, 1)} h")
                    if a:
                        alerts.append(a)

        st.fixes.append((p, cable_id, dist))
        while st.fixes and p.ts - st.fixes[0][0].ts > self.horizon_ms:
            st.fixes.popleft()
        st.last = p

        if cable_id is None or p.nav_status in cfg.excluded_nav_status:
            st.dwell_start.clear()
            return alerts

        # Loiter: continuous slow dwell over the same cable (needs a real cable).
        if self.index is None:
            st.dwell_start.clear()
        for cid in list(st.dwell_start):
            if cid != cable_id:
                del st.dwell_start[cid]
        if self.index is None:
            pass
        elif p.sog is not None and p.sog < cfg.loiter_max_sog_kn:
            start = st.dwell_start.setdefault(cable_id, p.ts)
            dwell = p.ts - start
            if dwell >= cfg.loiter_min_dwell_ms:
                a = self._emit(st, p, "loiter", cable_id, dist, f"{round(dwell / 60_000)} min under {cfg.loiter_max_sog_kn:g} kn within {cfg.cable_buffer_m:g} m")
                if a:
                    alerts.append(a)
        else:
            st.dwell_start.pop(cable_id, None)

        # Speed drop: baseline speed earlier vs speed in the last few minutes.
        b0, b1 = p.ts - cfg.drop_baseline_window_ms[0], p.ts - cfg.drop_baseline_window_ms[1]
        r0 = p.ts - cfg.drop_recent_window_ms
        base = [f.sog for f, _, _ in st.fixes if b0 <= f.ts <= b1 and f.sog is not None]
        recent = [f.sog for f, _, _ in st.fixes if f.ts >= r0 and f.sog is not None]
        if len(base) >= 3 and len(recent) >= 2:
            mb, mr = statistics.median(base), statistics.median(recent)
            if mb >= cfg.drop_min_baseline_kn and mr <= cfg.drop_max_ratio * mb and mb - mr >= cfg.drop_min_delta_kn:
                a = self._emit(st, p, "sog_drop", cable_id, dist, f"median SOG {mb:.1f} kn to {mr:.1f} kn")
                if a:
                    alerts.append(a)

        # Drag signature: slow, still moving, course or heading erratic, all near this cable.
        w0 = p.ts - cfg.drag_window_ms
        win = [(f, c) for f, c, _ in st.fixes if f.ts >= w0]
        near = [f for f, c in win if c == cable_id]
        if len(near) >= cfg.drag_min_fixes:
            sogs = [f.sog for f in near if f.sog is not None]
            cogs = [f.cog for f in near if f.cog is not None]
            gaps = [abs(angle_diff_deg(f.heading, f.cog)) for f in near if f.heading is not None and f.cog is not None]
            if sogs and len(cogs) >= cfg.drag_min_fixes:
                msog = statistics.median(sogs)
                lo, hi = cfg.drag_sog_range_kn
                disp = haversine_m(near[0].lat, near[0].lon, near[-1].lat, near[-1].lon)
                cstd = circular_std_deg(cogs)
                gap = statistics.mean(gaps) if gaps else 0.0
                if lo <= msog <= hi and disp >= cfg.drag_min_displacement_m and (
                    cstd >= cfg.drag_min_cog_std_deg or gap >= cfg.drag_min_heading_cog_gap_deg
                ):
                    a = self._emit(st, p, "drag_signature", cable_id, dist,
                                   f"median SOG {msog:.1f} kn, COG spread {cstd:.0f} deg, heading/COG gap {gap:.0f} deg, moved {disp:.0f} m")
                    if a:
                        alerts.append(a)
        return alerts
