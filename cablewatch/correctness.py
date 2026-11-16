"""Pipeline correctness checks on real DMA rows (the Samus Swan window around Bornholm).

1. Replay determinism: the same rows, delivered in three different arrival orders with up
   to 90 s of disorder (inside the 120 s lateness bound), must give exactly the alerts of
   the in-order run, with zero rows dropped as late.
2. Late data: rows delayed past the bound are counted as late (never processed twice,
   never silently merged), and the audit still balances.
3. Row-count audit: rows read from Parquet == rows the processor counted in, and every
   row lands in exactly one bucket.
4. Bus round trip: one hour pushed through the embedded log and consumed back gives the
   same alerts as processing the rows directly.

Writes data/warehouse/correctness.json.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import duckdb

from .bus import RAW_TOPIC, LocalBus
from .config import DEFAULT
from .pipeline import ROOT, WAREHOUSE, build_index, iter_raw, run_rows
from .replay import arrival_schedule

SRC = ROOT / "data" / "processed" / "raw_2022-02-25_26.parquet"
BBOX_SQL = "Longitude::DOUBLE BETWEEN 13.0 AND 17.0 AND Latitude::DOUBLE BETWEEN 54.5 AND 56.2"


def keys(proc):
    return sorted((a.ts, a.mmsi, a.rule, a.cable_id, a.detail) for a in proc.alerts)


def main() -> None:
    t0 = time.monotonic()
    index = build_index()
    rows = list(iter_raw([SRC], where=BBOX_SQL))
    n_parquet = duckdb.sql(f"SELECT count(*) FROM read_parquet('{SRC}') WHERE {BBOX_SQL}").fetchall()[0][0]
    base, _ = run_rows(rows, index)
    base_keys = keys(base)
    out = {
        "source": str(SRC.relative_to(ROOT)), "bbox": BBOX_SQL, "rows": len(rows),
        "allowed_lateness_s": DEFAULT.allowed_lateness_ms / 1000,
        "baseline": {"alerts": len(base_keys), "audit": base.audit()},
        "row_count_audit": {"parquet_rows": n_parquet, "processor_raw_in": base.audit()["raw_in"],
                            "match": n_parquet == base.audit()["raw_in"], "balanced": base.audit()["balanced"]},
    }

    det = []
    for seed in (1, 2, 3):
        sched = arrival_schedule(rows, jitter_ms=90_000, late_fraction=0.0, lateness_ms=DEFAULT.allowed_lateness_ms, seed=seed)
        moved = sum(1 for i, (_, seq, _, _) in enumerate(sched) if seq != i)
        proc, _ = run_rows((r for _, _, r, _ in sched), index)
        det.append({"seed": seed, "rows_out_of_order": moved, "late_dropped": proc.counts["late_dropped"],
                    "alerts": len(proc.alerts), "identical_to_in_order": keys(proc) == base_keys,
                    "balanced": proc.audit()["balanced"]})
    out["determinism"] = det

    sched = arrival_schedule(rows, jitter_ms=90_000, late_fraction=0.002, lateness_ms=DEFAULT.allowed_lateness_ms, seed=11)
    injected = sum(1 for s in sched if s[3])
    proc, _ = run_rows((r for _, _, r, _ in sched), index)
    lk = keys(proc)
    out["late_injection"] = {
        "injected_late_rows": injected, "late_dropped": proc.counts["late_dropped"],
        "note": "an injected row is only droppable if its vessel sent a newer fix that was released first; "
                "a vessel's very last rows, and rows that are exact duplicates, can legitimately survive",
        "alerts": len(lk), "alerts_missing_vs_in_order": len(set(base_keys) - set(lk)),
        "alerts_new_vs_in_order": len(set(lk) - set(base_keys)), "balanced": proc.audit()["balanced"],
    }

    # Bus round trip on the first hour of the window.
    hour = [r for r in rows if r["# Timestamp"].startswith("25/02/2022 22:")]
    with tempfile.TemporaryDirectory() as d:
        bus = LocalBus(Path(d))
        for r in hour:
            bus.produce(RAW_TOPIC, r["MMSI"], r)
        bus.flush()
        consumed = list(bus.consume(RAW_TOPIC))
        bus.close()
    direct, _ = run_rows(hour, index)
    via_bus, _ = run_rows(consumed, index)
    out["bus_round_trip"] = {"rows_produced": len(hour), "rows_consumed": len(consumed),
                             "identical_alerts": keys(direct) == keys(via_bus),
                             "identical_audit": direct.audit() == via_bus.audit()}
    out["seconds"] = round(time.monotonic() - t0, 1)
    WAREHOUSE.mkdir(parents=True, exist_ok=True)
    (WAREHOUSE / "correctness.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
