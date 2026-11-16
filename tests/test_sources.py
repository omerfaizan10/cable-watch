"""OSM cable filtering, the EMODnet duplicate check, and the outage-lookup crossing ranking.
All geometry and rows are hand-built; nothing here reads AIS data."""
import json

import pandas as pd

from cablewatch.backtest import crossings
from cablewatch.cables import load_osm, osm_kind
from cablewatch.geo import Cable
from conftest import TEST_CABLE


def test_osm_kind_active_and_inactive():
    assert osm_kind({"power": "cable", "location": "underwater"}) == "power"
    assert osm_kind({"seamark:type": "cable_submarine", "seamark:cable_submarine:category": "power"}) == "power"
    assert osm_kind({"communication": "line", "location": "submarine"}) == "telecom"
    # Under construction, planned or disused cables carry nothing yet (or any more).
    assert osm_kind({"construction:power": "cable", "seamark:type": "cable_submarine"}) is None
    assert osm_kind({"power": "cable", "location": "underwater", "disused": "yes"}) is None
    assert osm_kind({"disused:power": "cable", "location": "underwater"}) is None


def _way(wid, pts, **tags):
    return {"type": "way", "id": wid, "tags": {"power": "cable", "location": "underwater", **tags},
            "geometry": [{"lat": la, "lon": lo} for la, lo in pts]}


def test_osm_duplicate_of_emodnet_route_is_dropped(tmp_path):
    p = tmp_path / "osm.json"
    p.write_text(json.dumps({"ways": [
        # 300 m east of the EMODnet test cable along its whole length: the same cable.
        _way(1, [(54.8, 15.0047), (55.1, 15.0047), (55.4, 15.0047)], name="Copy"),
        # 20 km east: a different cable.
        _way(2, [(54.8, 15.31), (55.4, 15.31)], name="Other"),
        # Telecom next to a power route is not a duplicate of it.
        _way(3, [(54.8, 15.0), (55.4, 15.0)], power=None, communication="line", name="Fibre"),
    ]}))
    got = {c.name: c for c in load_osm([TEST_CABLE], p, pinned=None)}
    assert "Copy" not in got
    assert got["Other"].kind == "power" and got["Other"].source == "OpenStreetMap"
    assert got["Fibre"].kind == "telecom"


def _rows(path, mmsi, name, fixes):
    return [{"# Timestamp": t.strftime("%d/%m/%Y %H:%M:%S"), "Type of mobile": "Class A", "MMSI": mmsi,
             "Latitude": f"{la}", "Longitude": f"{lo}", "SOG": "10.0", "Name": name, "Ship type": "Cargo"}
            for t, la, lo in fixes]


def test_crossings_rank_by_gap_to_damage_time(tmp_path):
    t = pd.Timestamp("2024-01-01 12:00:00")
    m = pd.Timedelta(minutes=1)
    rows = []
    # Crosses the cable at 15.0 E exactly at 12:03 (midway between fixes 12:02 and 12:04).
    rows += _rows(None, "1", "NEAR", [(t + 2 * m, 55.1, 14.99), (t + 4 * m, 55.1, 15.01)])
    # Crosses at 11:00.
    rows += _rows(None, "2", "EARLY", [(t - 61 * m, 55.0, 14.99), (t - 59 * m, 55.0, 15.01)])
    # Fixes 30 min apart: a straight line between them is a guess, so no crossing is counted.
    rows += _rows(None, "3", "GAPPY", [(t - 15 * m, 55.2, 14.9), (t + 15 * m, 55.2, 15.1)])
    # Never reaches the cable.
    rows += _rows(None, "4", "AWAY", [(t, 55.1, 14.5), (t + 2 * m, 55.1, 14.6)])
    f = tmp_path / "raw.parquet"
    pd.DataFrame(rows).to_parquet(f)
    dmg = int(t.tz_localize("UTC").timestamp() * 1000)
    cx = crossings([f], [TEST_CABLE], dmg, window_h=4)
    assert [c["name"] for c in cx] == ["NEAR", "EARLY"]
    assert cx[0]["rank"] == 1 and abs(cx[0]["offset_min"] - 3.0) < 0.05
    assert abs(cx[1]["offset_min"] + 60.0) < 0.05
    assert abs(cx[0]["lon"] - 15.0) < 1e-6
