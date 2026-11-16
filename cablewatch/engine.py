"""The stream processor core: per-vessel event-time reordering, data-quality filters and
rule evaluation. It holds no I/O, so the same object runs behind the embedded bus, behind
Redpanda/Kafka, and inside the unit tests.

Ordering guarantee
------------------
Each vessel has its own reorder buffer. A fix is released once the vessel's highest event
time seen so far is at least `allowed_lateness_ms` past it. Released fixes come out in
`Position.sort_key()` order. If every fix arrives no more than the lateness bound behind
the newest fix already seen for that vessel, the released sequence is exactly the sorted
sequence, so the alerts are identical for any arrival order. A fix that arrives after a
later fix of the same vessel has already been released is counted as `late_dropped` and
goes to the late-data side output instead of silently corrupting state.
"""
from __future__ import annotations

import heapq
from collections import Counter
from dataclasses import dataclass, field

from .config import Config
from .geo import M_PER_NM, CableIndex, haversine_m
from .rules import Alert, RuleEngine, VesselState, vessel_in_scope
from .schema import Position


@dataclass
class _Reorder:
    heap: list = field(default_factory=list)
    max_ts: int = -1
    released_key: tuple | None = None
    seq: int = 0


@dataclass
class _Quality:
    last: Position | None = None
    rejected_run: list = field(default_factory=list)


class Processor:
    def __init__(self, index: CableIndex, cfg: Config):
        self.cfg = cfg
        self.rules = RuleEngine(index, cfg)
        self.reorder: dict[int, _Reorder] = {}
        self.quality: dict[int, _Quality] = {}
        self.vessels: dict[int, VesselState] = {}
        self.counts: Counter = Counter()
        self.late: list[Position] = []
        self.alerts: list[Alert] = []
        self.accepted_sink: list[Position] | None = None  # set to a list to capture clean fixes

    # ---- ingestion -------------------------------------------------------------------
    def reject_raw(self, reason: str) -> None:
        """Count a row that failed schema validation before it became a Position."""
        self.counts["raw_in"] += 1
        self.counts[f"reject:{reason}"] += 1

    def push(self, p: Position) -> list[Alert]:
        self.counts["raw_in"] += 1
        self.counts["valid_schema"] += 1
        rb = self.reorder.setdefault(p.mmsi, _Reorder())
        key = p.sort_key()
        if rb.released_key is not None and key < rb.released_key:
            self.counts["late_dropped"] += 1
            self.late.append(p)
            return []
        heapq.heappush(rb.heap, (key, rb.seq, p))
        rb.seq += 1
        if p.ts > rb.max_ts:
            rb.max_ts = p.ts
        return self._release(p.mmsi, rb, rb.max_ts - self.cfg.allowed_lateness_ms)

    def flush(self) -> list[Alert]:
        """End of stream: release everything still buffered, vessel by vessel."""
        out: list[Alert] = []
        for mmsi in sorted(self.reorder):
            out.extend(self._release(mmsi, self.reorder[mmsi], None))
        return out

    def _release(self, mmsi: int, rb: _Reorder, upto: int | None) -> list[Alert]:
        out: list[Alert] = []
        while rb.heap and (upto is None or rb.heap[0][0][0] <= upto):
            key, _, p = heapq.heappop(rb.heap)
            rb.released_key = key
            out.extend(self._process_in_order(p))
        return out

    # ---- in-order path ---------------------------------------------------------------
    def _process_in_order(self, p: Position) -> list[Alert]:
        q = self.quality.setdefault(p.mmsi, _Quality())
        last = q.last
        if last is not None:
            if p.ts == last.ts and p.lat == last.lat and p.lon == last.lon:
                self.counts["duplicate"] += 1
                return []
            d = haversine_m(last.lat, last.lon, p.lat, p.lon)
            dt_h = (p.ts - last.ts) / 3_600_000
            implied_kn = (d / M_PER_NM) / dt_h if dt_h > 0 else (float("inf") if d > 0 else 0.0)
            if d > self.cfg.teleport_min_dist_m and implied_kn > self.cfg.teleport_max_kn:
                q.rejected_run.append(p)
                if not self._run_is_consistent(q.rejected_run):
                    q.rejected_run = [p]
                if len(q.rejected_run) >= self.cfg.teleport_reset_after:
                    # The earlier track was the outlier: restart from the agreeing run.
                    self.counts["teleport"] += 1  # count only the current fix here
                    self.counts["track_reset"] += 1
                    # Fixes already in the run (except the current one) were counted as
                    # teleports when they arrived; reclassify them as accepted.
                    run = q.rejected_run
                    q.rejected_run = []
                    q.last = None
                    self.counts["teleport"] -= len(run)
                    out: list[Alert] = []
                    for r in run:
                        out.extend(self._accept(q, r))
                    return out
                self.counts["teleport"] += 1
                return []
        q.rejected_run = []
        return self._accept(q, p)

    def _run_is_consistent(self, run: list[Position]) -> bool:
        for a, b in zip(run, run[1:]):
            d = haversine_m(a.lat, a.lon, b.lat, b.lon)
            dt_h = (b.ts - a.ts) / 3_600_000
            if d > self.cfg.teleport_min_dist_m and (dt_h <= 0 or (d / M_PER_NM) / dt_h > self.cfg.teleport_max_kn):
                return False
        return True

    def _accept(self, q: _Quality, p: Position) -> list[Alert]:
        q.last = p
        self.counts["accepted"] += 1
        if self.accepted_sink is not None:
            self.accepted_sink.append(p)
        if not vessel_in_scope(p, self.cfg):
            self.counts["accepted_out_of_scope"] += 1
            return []
        self.counts["evaluated"] += 1
        st = self.vessels.setdefault(p.mmsi, VesselState())
        new = self.rules.step(st, p)
        self.alerts.extend(new)
        self.counts["alerts"] += len(new)
        return new

    # ---- audit -----------------------------------------------------------------------
    def audit(self) -> dict:
        """Row-count reconciliation: every raw row lands in exactly one bucket."""
        c = self.counts
        rejects = sum(v for k, v in c.items() if k.startswith("reject:"))
        buffered = sum(len(rb.heap) for rb in self.reorder.values())
        pending = sum(len(q.rejected_run) for q in self.quality.values())
        # Fixes in a pending teleport run were counted as teleports already.
        accounted = rejects + c["late_dropped"] + c["duplicate"] + c["teleport"] + c["accepted"] + buffered
        return {
            "raw_in": c["raw_in"],
            "schema_rejects": rejects,
            "reject_breakdown": {k.split(":", 1)[1]: v for k, v in sorted(c.items()) if k.startswith("reject:")},
            "late_dropped": c["late_dropped"],
            "duplicate": c["duplicate"],
            "teleport": c["teleport"],
            "track_reset": c["track_reset"],
            "accepted": c["accepted"],
            "accepted_out_of_scope": c["accepted_out_of_scope"],
            "evaluated": c["evaluated"],
            "still_buffered": buffered,
            "pending_teleport_run": pending,
            "alerts": c["alerts"],
            "balanced": accounted == c["raw_in"],
        }
