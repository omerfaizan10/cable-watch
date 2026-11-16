"""Backtest against publicly reported incidents, and false alerts on normal days.

For each incident in data/reference/incidents.csv this decides, from the data itself,
whether it is testable:
  * is the damage date inside the DMA archive at all;
  * does the named vessel (matched by IMO, then by reported MMSI) appear in the extracted
    rows, and does it appear BEFORE the reported damage time;
  * is the damaged asset in the EMODnet route data we gate on.
Then it reads the processor's alert Parquet for that day (cable-gated and cable-agnostic
runs) and reports whether the vessel was flagged and how early.

False alerts per day come from the normal-day runs: every alert there is counted as a false
alert, because none of those days has a reported incident in the covered area. That is the
conservative reading; some of those alerts may well be real anchoring over a cable.

Outage lookup: when the damage time is public to the hour or better and the damaged route
is in the cable data, every vessel whose AIS track crosses that route within
CROSSING_WINDOW_H of the damage time is listed, ranked by how close its crossing is to the
reported time. This is the question an investigator asks first ("who was over the cable
when it failed?"), and it needs no behavior rule at all.

Writes data/warehouse/backtest.json.
"""
from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .cables import load_cables
from .pipeline import ROOT, WAREHOUSE

PROC = ROOT / "data" / "processed"
INCIDENTS = ROOT / "data" / "reference" / "incidents.csv"
ARCHIVE_LAST_DAY = "2025-02-26"  # last daily file in the DMA bucket listing on 2026-11-14

# 2024-04-10 was looked at while setting thresholds (see config.py), so it is reported but
# kept out of the false-alert rate.
TUNING_DAY = "2024-04-10"
# Ordinary days with no reported incident in the covered area, picked by
# scripts/pick_normal_days.py (seeded, 2 or 3 per month, never next to an incident).
NORMAL_DAYS = [d for d in (ROOT / "data" / "reference" / "normal_days.txt").read_text().split() if d != TUNING_DAY]

INCIDENT_FILES = {
    "bornholm-2022": ["2022-02-25_26"],
    "bcs-2024": ["2024-11-17"],
    "clion1-2024": ["2024-11-17", "2024-11-18"],
    "estlink2-2024": ["2024-12-25"],
    "gotland-latvia-2025": ["2025-01-26"],
}

# Words that identify the damaged asset in EMODnet names (checked against the loaded routes).
ASSET_KEYWORDS = {
    "bornholm-2022": ["bornholm"],
    "balticconnector-2023": ["balticconnector"],
    "bcs-2024": ["bcs", "east-west"],
    "clion1-2024": ["c-lion"],
    "estlink2-2024": ["estlink"],
    "gotland-latvia-2025": ["lvrtc", "ventspils"],
    "fitburg-2025": ["elisa", "arelion"],
    "sventoji-liepaja-2026": ["sventoji", "liepaja", "arelion"],
}


def iso_ms(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)


def ms_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def vessel_presence(files: list[Path], imo: str, mmsi: str, name: str) -> dict:
    preds = []
    if imo:
        preds.append(f"IMO = '{imo}'")
    if mmsi:
        preds.append(f"MMSI = '{mmsi}'")
    if name:
        preds.append(f"upper(Name) = '{name.upper()}'")
    if not preds:
        return {"mmsis": [], "fixes": 0}
    flist = [str(f) for f in files]
    # Static fields (IMO, name) are not in every row, so first find the MMSIs, then all their rows.
    mmsis = [r[0] for r in duckdb.sql(
        f"SELECT DISTINCT MMSI FROM read_parquet({flist!r}) WHERE {' OR '.join(preds)}").fetchall()]
    if not mmsis:
        return {"mmsis": [], "fixes": 0}
    q = f"""SELECT count(*), min(ts), max(ts), min(lon), max(lon) FROM (
              SELECT strptime("# Timestamp", '%d/%m/%Y %H:%M:%S') AS ts, Longitude::DOUBLE AS lon
              FROM read_parquet({flist!r}) WHERE MMSI IN {tuple(mmsis) + ('',)})"""
    n, t0, t1, lo0, lo1 = duckdb.sql(q).fetchall()[0]
    return {"mmsis": sorted(mmsis), "fixes": n,
            "first_fix_utc": t0.strftime("%Y-%m-%dT%H:%M:%SZ") if t0 else None,
            "last_fix_utc": t1.strftime("%Y-%m-%dT%H:%M:%SZ") if t1 else None,
            "lon_range": [lo0, lo1]}


def alerts_for(run: str, mmsis: list[str]) -> list[dict]:
    p = WAREHOUSE / f"alerts_{run}.parquet"
    if not p.exists() or not mmsis:
        return []
    ids = ",".join(str(int(m)) for m in mmsis)
    return duckdb.sql(f"SELECT * FROM read_parquet('{p}') WHERE mmsi IN ({ids}) ORDER BY ts").df().to_dict("records")


CROSSING_WINDOW_H = 4
MAX_FIX_GAP_S = 900  # a straight line between fixes further apart than this is a guess, not a track


def crossings(files: list[Path], routes: list, dmg_ms: int, window_h: float = CROSSING_WINDOW_H) -> list[dict]:
    """Every crossing of `routes` by any vessel within +-window_h of dmg_ms, closest first."""
    from shapely.geometry import LineString

    lines = [LineString([(lo, la) for la, lo in c.line]) for c in routes]
    lon0 = min(l.bounds[0] for l in lines) - 0.05
    lat0 = min(l.bounds[1] for l in lines) - 0.05
    lon1 = max(l.bounds[2] for l in lines) + 0.05
    lat1 = max(l.bounds[3] for l in lines) + 0.05
    t0, t1 = ms_iso(dmg_ms - int(window_h * 3_600_000)), ms_iso(dmg_ms + int(window_h * 3_600_000))
    flist = [str(f) for f in files]
    df = duckdb.sql(f"""
        WITH r AS (
          SELECT MMSI, Name, "Type of mobile" AS mt, "Ship type" AS st,
                 strptime("# Timestamp", '%d/%m/%Y %H:%M:%S') AS ts,
                 TRY_CAST(Longitude AS DOUBLE) AS lon, TRY_CAST(Latitude AS DOUBLE) AS lat, TRY_CAST(SOG AS DOUBLE) AS sog
          FROM read_parquet({flist!r})
          WHERE TRY_CAST(Longitude AS DOUBLE) BETWEEN {lon0} AND {lon1} AND TRY_CAST(Latitude AS DOUBLE) BETWEEN {lat0} AND {lat1})
        SELECT DISTINCT ON (MMSI, ts) MMSI, ts, lon, lat, sog,
               max(Name) OVER (PARTITION BY MMSI) AS name, max(mt) OVER (PARTITION BY MMSI) AS mt,
               max(st) OVER (PARTITION BY MMSI) AS st
        FROM r WHERE ts BETWEEN TIMESTAMP '{t0[:-1]}' AND TIMESTAMP '{t1[:-1]}'
        ORDER BY MMSI, ts""").df()
    out = []
    for mmsi, g in df.groupby("MMSI", sort=False):
        rows = list(g.itertuples(index=False))
        best = None
        for a, b in zip(rows, rows[1:]):
            gap = (b.ts - a.ts).total_seconds()
            if gap <= 0 or gap > MAX_FIX_GAP_S or (a.lon == b.lon and a.lat == b.lat):
                continue
            seg = LineString([(a.lon, a.lat), (b.lon, b.lat)])
            for line, route in zip(lines, routes):
                x = seg.intersection(line)
                if x.is_empty:
                    continue
                pt = x if x.geom_type == "Point" else x.representative_point()
                frac = seg.project(pt) / seg.length
                t_ms = int(a.ts.timestamp() * 1000 + frac * gap * 1000)
                d = abs(t_ms - dmg_ms)
                if best is None or d < best["abs_offset_min"] * 60_000:
                    best = {"mmsi": str(mmsi), "name": g["name"].iloc[0], "mobile_type": g["mt"].iloc[0],
                            "ship_type": g["st"].iloc[0], "crossing_utc": ms_iso(t_ms),
                            "offset_min": round((t_ms - dmg_ms) / 60_000, 1),
                            "abs_offset_min": round(d / 60_000, 1),
                            "sog_kn": None if a.sog is None or a.sog != a.sog else a.sog,
                            "route": route.name, "lon": round(pt.x, 5), "lat": round(pt.y, 5)}
        if best:
            out.append(best)
    out.sort(key=lambda c: c["abs_offset_min"])
    for i, c in enumerate(out, 1):
        c["rank"] = i
    return out


def run_audit(run: str) -> dict | None:
    p = WAREHOUSE / f"run_{run}.json"
    return json.loads(p.read_text()) if p.exists() else None


def main() -> None:
    cables = load_cables()
    names = sorted({c.name for c in cables})
    incidents = list(csv.DictReader(open(INCIDENTS, encoding="utf-8")))
    results = []
    for inc in incidents:
        iid = inc["incident_id"]
        dmg = iso_ms(inc["damage_utc"])
        day = inc["damage_utc"][:10]
        kw = ASSET_KEYWORDS.get(iid, [])
        asset_routes = [n for n in names if any(k in n.lower() for k in kw)]
        r = {"incident_id": iid, "damage_utc": inc["damage_utc"], "time_precision": inc["time_precision"],
             "asset": inc["asset"], "asset_type": inc["asset_type"], "between": inc["between"].replace(";", ", "),
             "vessel": inc["vessel_name"], "imo": inc["imo"], "reported_mmsi": inc["mmsi"],
             "identifier_notes": inc["identifier_notes"], "location_notes": inc["location_notes"],
             "status_notes": inc["status_notes"],
             "sources": [u.strip() for u in inc["sources"].split("|") if u.strip()],
             "asset_routes_in_emodnet": asset_routes}
        if day > ARCHIVE_LAST_DAY:
            r.update(status="not_in_archive", reason=f"DMA archive ends {ARCHIVE_LAST_DAY}")
        elif iid not in INCIDENT_FILES:
            r.update(status="outside_coverage_not_downloaded",
                     reason="Gulf of Finland, east of the measured DMA receiving range (see coverage), "
                            "so the 16 GB monthly file was not streamed")
        else:
            files = [PROC / f"raw_{d}.parquet" for d in INCIDENT_FILES[iid]]
            files = [f for f in files if f.exists()]
            pres = vessel_presence(files, inc["imo"], inc["mmsi"], inc["vessel_name"]) if inc["vessel_name"] else {"mmsis": [], "fixes": 0}
            r["ais"] = pres
            if pres["fixes"] == 0:
                r.update(status="vessel_not_in_coverage", reason="no AIS rows for the vessel in the DMA extract")
            elif iso_ms(pres["first_fix_utc"]) > dmg and inc["time_precision"] != "day":
                r.update(status="in_coverage_only_after_damage",
                         reason=f"first DMA fix {pres['first_fix_utc']} is after the reported damage time")
            elif inc["time_precision"] == "day" and iso_ms(pres["first_fix_utc"]) >= dmg:
                r.update(status="damage_time_unknown",
                         reason="only the damage date is public, so lead time cannot be measured")
            else:
                r.update(status="testable", reason="vessel tracked by DMA before the reported damage time")
            routes = [c for c in cables if any(k in c.name.lower() for k in kw)]
            if routes and files and inc["time_precision"] != "day":
                cx = crossings(files, routes, dmg)
                named = next((c for c in cx if c["mmsi"] in pres["mmsis"]), None)
                r["outage_lookup"] = {
                    "window_h": CROSSING_WINDOW_H, "candidates": len(cx),
                    "named_vessel_rank": named["rank"] if named else None,
                    "named_vessel_offset_min": named["offset_min"] if named else None,
                    "runner_up_abs_offset_min": next((c["abs_offset_min"] for c in cx if c is not named), None),
                    "top": cx[:12],
                }
            for mode in ("gated", "agnostic"):
                al = []
                for d in INCIDENT_FILES[iid]:
                    al += alerts_for(f"{mode}_{d}", pres["mmsis"])
                al.sort(key=lambda a: a["ts"])
                before = [a for a in al if a["ts"] <= dmg]
                r[mode] = {
                    "alerts_for_vessel": len(al),
                    "first_alert_utc": ms_iso(al[0]["ts"]) if al else None,
                    "first_alert_rule": al[0]["rule"] if al else None,
                    "flagged_before_damage": bool(before),
                    "lead_time_h": round((dmg - before[0]["ts"]) / 3_600_000, 2) if before else None,
                    "alerts": [{k: a[k] for k in ("ts", "rule", "label", "cable_name", "lat", "lon", "sog", "detail")} for a in al[:40]],
                }
        results.append(r)

    normal = []
    for d in [TUNING_DAY] + NORMAL_DAYS:
        row = {"day": d, "tuning_day": d == TUNING_DAY}
        for mode in ("gated", "agnostic"):
            p = WAREHOUSE / f"alerts_{mode}_{d}.parquet"
            if not p.exists():
                row[mode] = None
                continue
            con = duckdb.sql(f"SELECT rule, count(*) n, count(DISTINCT mmsi) v FROM read_parquet('{p}') GROUP BY rule ORDER BY rule").fetchall()
            tot = duckdb.sql(f"SELECT count(*), count(DISTINCT mmsi) FROM read_parquet('{p}')").fetchall()[0]
            aud = run_audit(f"{mode}_{d}")
            row[mode] = {"alerts": tot[0], "vessels": tot[1], "by_rule": {k: {"alerts": n, "vessels": v} for k, n, v in con},
                         "evaluated_fixes": aud["audit"]["evaluated"] if aud else None,
                         "distinct_mmsi_accepted": None}
        normal.append(row)

    # Both modes are summarised over the same days (those with both runs), so the
    # mapped-cables and whole-sea figures are a like-for-like comparison.
    def summary(mode):
        vals = [r[mode]["alerts"] for r in normal if r.get("gated") and r.get("agnostic") and not r["tuning_day"]]
        if not vals:
            return None
        v = sorted(vals)
        q = lambda f: v[min(len(v) - 1, int(f * len(v)))]
        return {"days": len(vals), "mean_alerts_per_day": round(statistics.mean(vals), 1),
                "median": statistics.median(vals), "p10": q(0.1), "p90": q(0.9),
                "min": min(vals), "max": max(vals)}

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "incidents": results,
        "normal_days": normal,
        "false_alerts_per_day": {"gated": summary("gated"), "agnostic": summary("agnostic")},
        "counts": {s: sum(1 for r in results if r["status"] == s) for s in sorted({r["status"] for r in results})},
    }
    (WAREHOUSE / "backtest.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps({k: out[k] for k in ("false_alerts_per_day", "counts")}, indent=2))
    for r in results:
        print(r["incident_id"], r["status"], {m: (r.get(m) or {}).get("first_alert_utc") for m in ("gated", "agnostic")})


if __name__ == "__main__":
    main()
