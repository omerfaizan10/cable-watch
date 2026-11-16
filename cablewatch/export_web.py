"""Precompute the compact JSON the site reads (web/public/data). Nothing in the site is
computed in the browser except drawing; every number comes from these files.

  cables.json      EMODnet routes inside the chart area (simplified, CC BY 4.0)
  coverage.json    measured DMA receiving range: fixes per 0.2 degree cell, all extracted days
  replay_*.json    vessel tracks + alerts for one incident window or normal-traffic window
  scorecard.json   backtest, false alerts per day, pipeline correctness, data quality audits
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .cables import load_cables
from .config import DEFAULT
from .pipeline import ROOT, WAREHOUSE, build_index, iter_raw, run_rows

OUT = ROOT / "web" / "public" / "data"
PROC = ROOT / "data" / "processed"
CHART_BBOX = (9.5, 53.6, 20.5, 58.6)  # lon0, lat0, lon1, lat1

REPLAYS = [
    {
        "id": "samus-swan-2022",
        "title": "Samus Swan, Bornholm power cable, 26 Feb 2022",
        "file": "raw_2022-02-25_26.parquet",
        "bbox": (12.6, 54.5, 16.8, 56.1),
        "start": "2022-02-25T20:00:00Z", "end": "2022-02-26T08:30:00Z",
        "focus_mmsi": 248363000, "incident_id": "bornholm-2022",
        "step_s": 60,
    },
    {
        "id": "yi-peng-3-2024",
        "title": "Yi Peng 3 westbound past Bornholm, 18 Nov 2024",
        "file": "raw_2024-11-18.parquet",
        "bbox": (11.8, 54.4, 16.6, 56.0),
        "start": "2024-11-18T05:30:00Z", "end": "2024-11-18T16:00:00Z",
        "focus_mmsi": 414270000, "incident_id": "clion1-2024",
        "step_s": 120,
    },
    {
        "id": "normal-2025-02-12",
        "title": "Normal traffic, Arkona Basin and Kriegers Flak, 12 Feb 2025",
        "file": "raw_2025-02-12.parquet",
        "bbox": (11.6, 54.3, 15.2, 55.6),
        "start": "2025-02-12T00:00:00Z", "end": "2025-02-13T00:00:00Z",
        "focus_mmsi": None, "incident_id": None,
        "step_s": 180,
    },
]


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def in_bbox(lon, lat, b):
    return b[0] <= lon <= b[2] and b[1] <= lat <= b[3]


def export_cables() -> dict:
    feats = []
    for c in load_cables():
        if not any(in_bbox(lo, la, CHART_BBOX) for la, lo in c.line):
            continue
        feats.append({"type": "Feature", "properties": {"id": c.cable_id, "name": c.name, "kind": c.kind, "source": c.source},
                      "geometry": {"type": "LineString", "coordinates": [[round(lo, 4), round(la, 4)] for la, lo in c.line]}})
    return {"type": "FeatureCollection", "features": feats}


def export_coverage() -> dict:
    grid: dict[tuple[float, float], int] = defaultdict(int)
    days = []
    for f in sorted(PROC.glob("raw_*.coverage.json")):
        days.append(f.name.replace("raw_", "").replace(".coverage.json", ""))
        for la, lo, n in json.loads(f.read_text()):
            grid[(round(la // 0.2 * 0.2, 1), round(lo // 0.2 * 0.2, 1))] += n
    cells = [[lo, la, n] for (la, lo), n in sorted(grid.items()) if 4 <= lo <= 32 and 52 <= la <= 66]
    east = max((lo for lo, la, n in cells if n >= 1000 * len(days)), default=None)
    return {"cell_deg": 0.2, "days": days, "cells": cells, "east_limit_lon_1000_fixes_per_day": east}


def export_replay(spec: dict, index) -> dict:
    t0, t1 = ms(spec["start"]), ms(spec["end"])
    b = spec["bbox"]
    where = (f"Longitude::DOUBLE BETWEEN {b[0]} AND {b[2]} AND Latitude::DOUBLE BETWEEN {b[1]} AND {b[3]}")
    proc, tracks = run_rows(iter_raw([PROC / spec["file"]], where=where), index, DEFAULT, capture_tracks=set())
    agn, _ = run_rows(iter_raw([PROC / spec["file"]], where=where), None, DEFAULT)
    step = spec["step_s"] * 1000
    vessels = []
    for mmsi, fixes in tracks.items():
        sel = [p for p in fixes if t0 <= p.ts <= t1]
        if not sel:
            continue
        focus = mmsi == spec["focus_mmsi"]
        last = sel[-1]
        if not focus and (last.mobile_type != "Class A" or last.ship_type in DEFAULT.excluded_ship_types):
            continue
        pts, nxt = [], -1
        for p in sel:
            if p.ts >= nxt or p is sel[-1]:
                pts.append([round((p.ts - t0) / 1000), round(p.lon, 4), round(p.lat, 4),
                            None if p.sog is None else round(p.sog, 1), None if p.cog is None else round(p.cog)])
                nxt = p.ts + (60_000 if focus else step)
        named = next((p for p in reversed(sel) if p.name), last)
        vessels.append({"mmsi": mmsi, "name": named.name, "imo": named.imo, "type": named.ship_type,
                        "length": named.length, "focus": focus, "pts": pts})

    def alert_rows(alerts, mode):
        out = []
        for a in sorted(alerts, key=lambda a: a.ts):
            if t0 <= a.ts <= t1 and (mode == "gated" or a.mmsi == spec["focus_mmsi"]):
                out.append({"t": round((a.ts - t0) / 1000), "mmsi": a.mmsi, "name": a.name, "rule": a.rule,
                            "label": a.to_dict()["label"], "cable": a.cable_name, "lon": a.lon, "lat": a.lat,
                            "sog": a.sog, "dist_m": a.distance_m, "detail": a.detail, "mode": mode})
        return out

    alerts = alert_rows(proc.alerts, "gated") + alert_rows(agn.alerts, "agnostic")
    alerts.sort(key=lambda a: (a["t"], a["mmsi"]))
    return {"id": spec["id"], "title": spec["title"], "start_utc": spec["start"], "end_utc": spec["end"],
            "bbox": b, "focus_mmsi": spec["focus_mmsi"], "incident_id": spec["incident_id"],
            "vessels": sorted(vessels, key=lambda v: (not v["focus"], v["mmsi"])), "alerts": alerts,
            "audit": proc.audit()}


def _runs_in_backtest(runs: dict) -> dict:
    """Only the days the backtest evaluated, so every count on the site describes the
    same set of days even if more runs finished after the backtest."""
    p = WAREHOUSE / "backtest.json"
    if not p.exists():
        return {k: v for k, v in runs.items() if not k.startswith("kafka_")}
    bt = json.loads(p.read_text())
    days = {r["day"] for r in bt["normal_days"] if r.get("gated") and r.get("agnostic")}
    from .backtest import INCIDENT_FILES
    days |= {d for files in INCIDENT_FILES.values() for d in files}
    return {k: v for k, v in runs.items() if k.split("_", 1)[1] in days and not k.startswith("kafka_")}


def _live() -> dict | None:
    p = WAREHOUSE / "live_check.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    keep = ("started_utc", "seconds", "rows", "rows_per_second", "vessels", "vessels_with_static_data",
            "rows_per_vessel_median", "lag_seconds_median", "lag_seconds_p95", "lon_range", "lat_range")
    out = {k: d.get(k) for k in keep}
    out["balanced"] = d["audit"]["balanced"]
    out["evaluated"] = d["audit"]["evaluated"]
    out["alerts"] = len(d.get("alerts", []))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cables.json").write_text(json.dumps(export_cables(), separators=(",", ":")))
    (OUT / "coverage.json").write_text(json.dumps(export_coverage(), separators=(",", ":")))
    index = build_index()
    replays = []
    for spec in REPLAYS:
        if not (PROC / spec["file"]).exists():
            continue
        r = export_replay(spec, index)
        (OUT / f"replay_{spec['id']}.json").write_text(json.dumps(r, separators=(",", ":")))
        replays.append({"id": r["id"], "title": r["title"], "vessels": len(r["vessels"]), "alerts": len(r["alerts"])})
        print(spec["id"], len(r["vessels"]), "vessels", len(r["alerts"]), "alerts")

    runs = {}
    for f in sorted(WAREHOUSE.glob("run_*.json")):
        d = json.loads(f.read_text())
        runs[d["run"]] = d["audit"]
    score = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": DEFAULT.to_dict(),
        "backtest": json.loads((WAREHOUSE / "backtest.json").read_text()) if (WAREHOUSE / "backtest.json").exists() else None,
        "correctness": json.loads((WAREHOUSE / "correctness.json").read_text()) if (WAREHOUSE / "correctness.json").exists() else None,
        "live": _live(),
        "kafka": json.loads((WAREHOUSE / "kafka_check.json").read_text()) if (WAREHOUSE / "kafka_check.json").exists() else None,
        "runs": _runs_in_backtest(runs),
        "replays": replays,
    }
    (OUT / "scorecard.json").write_text(json.dumps(score, separators=(",", ":"), default=str))
    print("wrote", sorted(p.name for p in OUT.glob("*.json")))


if __name__ == "__main__":
    main()
