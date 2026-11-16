from cablewatch.engine import Processor
from conftest import MIN, T0, pos
from scenarios import drag, eastbound_with_drop, loiter, straight_transit, zigzag


def run(index, cfg, fixes):
    proc = Processor(index, cfg)
    for p in sorted(fixes, key=lambda p: p.sort_key()):
        proc.push(p)
    proc.flush()
    return proc


def rules(proc):
    return sorted({a.rule for a in proc.alerts})


def test_straight_transit_is_quiet(index, cfg):
    assert run(index, cfg, straight_transit()).alerts == []


def test_speed_drop_over_cable(index, cfg):
    proc = run(index, cfg, eastbound_with_drop())
    assert "sog_drop" in rules(proc)
    a = next(a for a in proc.alerts if a.rule == "sog_drop")
    assert a.distance_m <= cfg.cable_buffer_m and a.cable_id == "test#0"


def test_speed_drop_far_from_cable_is_ignored(index, cfg):
    far = [pos(p.ts, 55.1, p.lon - 0.5, sog=p.sog, mmsi=p.mmsi) for p in eastbound_with_drop()]
    assert run(index, cfg, far).alerts == []


def test_loiter_fires_after_dwell_and_respects_cooldown(index, cfg):
    proc = run(index, cfg, loiter(minutes=100))
    times = [(a.ts - T0) // MIN for a in proc.alerts if a.rule == "loiter"]
    assert times == [30, 90]


def test_loiter_shorter_than_threshold_is_quiet(index, cfg):
    assert run(index, cfg, loiter(minutes=25)).alerts == []


def test_landing_exclusion(index, cfg):
    # Same loiter 2 km from the cable's southern landing point.
    assert run(index, cfg, loiter(lat=54.818, minutes=60)).alerts == []


def test_out_of_scope_ship_types_are_not_evaluated(index, cfg):
    proc = run(index, cfg, loiter(minutes=60, ship_type="Fishing"))
    assert proc.alerts == [] and proc.counts["accepted_out_of_scope"] == 60


def test_drag_signature(index, cfg):
    assert "drag_signature" in rules(run(index, cfg, drag()))


def test_repeat_crossing(index, cfg):
    proc = run(index, cfg, zigzag())
    assert "repeat_crossing" in rules(proc)


def test_agnostic_mode_runs_without_cables(cfg):
    proc = run(None, cfg, eastbound_with_drop())
    assert rules(proc) == ["sog_drop"]
    assert all(a.cable_name == "(any position)" for a in proc.alerts)
