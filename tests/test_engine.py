import random

from cablewatch.engine import Processor
from conftest import MIN, T0, pos
from scenarios import drag, eastbound_with_drop, loiter, straight_transit, zigzag


def all_fixes():
    return eastbound_with_drop() + straight_transit() + loiter(minutes=70) + drag() + zigzag()


def alert_keys(proc):
    return sorted((a.ts, a.mmsi, a.rule, a.cable_id, a.detail) for a in proc.alerts)


def feed(index, cfg, fixes):
    proc = Processor(index, cfg)
    for p in fixes:
        proc.push(p)
    proc.flush()
    return proc


def test_same_alerts_for_any_arrival_order_within_lateness(index, cfg):
    fixes = all_fixes()
    baseline = feed(index, cfg, sorted(fixes, key=lambda p: p.sort_key()))
    assert baseline.alerts, "scenario should produce alerts"
    for seed in range(25):
        rng = random.Random(seed)
        arrivals = sorted(((p.ts + rng.randint(0, cfg.allowed_lateness_ms), i, p) for i, p in enumerate(fixes)))
        proc = feed(index, cfg, [p for _, _, p in arrivals])
        assert proc.counts["late_dropped"] == 0
        assert alert_keys(proc) == alert_keys(baseline)


def test_fix_later_than_bound_is_dropped_and_counted(index, cfg):
    fixes = sorted(straight_transit(), key=lambda p: p.sort_key())
    late = fixes.pop(10)  # arrives after the vessel moved on by more than the bound
    proc = feed(index, cfg, fixes + [late])
    assert proc.counts["late_dropped"] == 1 and proc.late == [late]
    assert proc.audit()["balanced"]


def test_late_but_within_bound_is_reordered(index, cfg):
    fixes = sorted(straight_transit(), key=lambda p: p.sort_key())
    # Swap two neighbours one minute apart: within the 2 min bound.
    fixes[10], fixes[11] = fixes[11], fixes[10]
    proc = feed(index, cfg, fixes)
    assert proc.counts["late_dropped"] == 0 and proc.counts["accepted"] == len(fixes)


def test_teleport_is_filtered_and_track_continues(index, cfg):
    fixes = sorted(straight_transit(), key=lambda p: p.sort_key())
    bad = pos(fixes[20].ts + 30_000, 56.5, 15.0, mmsi=fixes[0].mmsi)  # 150 km jump in 30 s
    proc = feed(index, cfg, fixes[:21] + [bad] + fixes[21:])
    assert proc.counts["teleport"] == 1
    assert proc.counts["accepted"] == len(fixes)
    assert proc.audit()["balanced"]


def test_bad_first_fix_triggers_track_reset(index, cfg):
    fixes = sorted(straight_transit(), key=lambda p: p.sort_key())
    bad = pos(fixes[0].ts - MIN, 58.0, 12.0, mmsi=fixes[0].mmsi)
    proc = feed(index, cfg, [bad] + fixes)
    a = proc.audit()
    assert a["track_reset"] == 1 and a["balanced"]
    # A stream cannot retract what it already emitted: the bad first fix stays accepted,
    # the three good fixes held back while the run was checked are released, nothing is lost.
    assert a["teleport"] == 0 and a["accepted"] == len(fixes) + 1


def test_duplicates_counted(index, cfg):
    fixes = sorted(straight_transit(), key=lambda p: p.sort_key())
    proc = feed(index, cfg, fixes + fixes[:5])
    # Re-sent copies of early fixes are behind the bound by now: they are late, not silently merged.
    assert proc.counts["late_dropped"] == 5
    proc2 = feed(index, cfg, [p for f in fixes for p in (f, f)])
    assert proc2.counts["duplicate"] == len(fixes)
    assert proc2.audit()["balanced"]


def test_audit_counts_schema_rejects(index, cfg):
    proc = Processor(index, cfg)
    proc.reject_raw("invalid_mmsi")
    proc.push(pos(T0, 55.0, 15.5))
    proc.flush()
    a = proc.audit()
    assert a["raw_in"] == 2 and a["schema_rejects"] == 1 and a["accepted"] == 1 and a["balanced"]
