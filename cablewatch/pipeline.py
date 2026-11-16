"""Batch and streaming entry points around the Processor, plus the DuckDB/Parquet sinks.

  backfill: read extracted DMA Parquet in event-time order and run the processor
            (what the Makefile calls for each day; the same code path as streaming).
  stream:   consume the raw topic from the bus (embedded log or Redpanda), publish alerts
            and late rows to their topics, and write the same sinks.

Examples:
  python -m cablewatch.pipeline backfill data/processed/raw_2025-02-12.parquet --run normal_2025-02-12
  python -m cablewatch.pipeline stream --run replay_demo
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Iterable, Iterator

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .bus import ALERT_TOPIC, LATE_TOPIC, RAW_TOPIC, get_bus
from .cables import load_cables
from .config import DEFAULT, Config
from .engine import Processor
from .geo import CableIndex
from .schema import parse_dma_row

ROOT = Path(__file__).resolve().parent.parent
WAREHOUSE = ROOT / "data" / "warehouse"

# DMA timestamps are dd/mm/yyyy; this expression turns them into a sortable string in SQL.
TS_SORT_SQL = """substr("# Timestamp",7,4)||substr("# Timestamp",4,2)||substr("# Timestamp",1,2)||substr("# Timestamp",11,9)"""


def build_index(cfg: Config = DEFAULT) -> CableIndex:
    return CableIndex.build(load_cables(), cfg.cable_buffer_m, cfg.h3_res)


def iter_raw(paths: Iterable[Path], where: str | None = None, batch: int = 250_000) -> Iterator[dict]:
    """Raw rows (dict of str) from extracted Parquet, ordered by event time then file order."""
    files = [str(p) for p in paths]
    con = duckdb.connect()
    q = f"SELECT * FROM read_parquet({files!r}) {'WHERE ' + where if where else ''} ORDER BY {TS_SORT_SQL}, MMSI"
    reader = con.sql(q).to_arrow_reader(batch)
    for rb in reader:
        yield from rb.to_pylist()


def run_rows(rows: Iterable[dict], index: CableIndex | None, cfg: Config = DEFAULT,
             capture_tracks: set[int] | None = None) -> tuple[Processor, dict[int, list]]:
    proc = Processor(index, cfg)
    tracks: dict[int, list] = {}
    if capture_tracks is not None:
        proc.accepted_sink = _TrackSink(capture_tracks, tracks)
    for row in rows:
        p, reason = parse_dma_row(row)
        if p is None:
            proc.reject_raw(reason)
            continue
        proc.push(p)
    proc.flush()
    return proc, tracks


class _TrackSink(list):
    """Keeps clean fixes only for the vessels we want to draw."""

    def __init__(self, wanted: set[int], out: dict[int, list]):
        super().__init__()
        self.wanted, self.out = wanted, out

    def append(self, p) -> None:  # type: ignore[override]
        if not self.wanted or p.mmsi in self.wanted:
            self.out.setdefault(p.mmsi, []).append(p)


def write_sinks(run: str, proc: Processor, extra: dict | None = None) -> dict:
    WAREHOUSE.mkdir(parents=True, exist_ok=True)
    alerts = [a.to_dict() for a in sorted(proc.alerts, key=lambda a: (a.ts, a.mmsi, a.rule, a.cable_id))]
    audit = proc.audit()
    pq_path = WAREHOUSE / f"alerts_{run}.parquet"
    schema = pa.schema([
        ("alert_id", pa.string()), ("ts", pa.int64()), ("mmsi", pa.int64()), ("imo", pa.string()),
        ("name", pa.string()), ("ship_type", pa.string()), ("rule", pa.string()), ("label", pa.string()),
        ("cable_id", pa.string()), ("cable_name", pa.string()), ("lat", pa.float64()), ("lon", pa.float64()),
        ("sog", pa.float64()), ("distance_m", pa.float64()), ("detail", pa.string()),
    ])
    pq.write_table(pa.Table.from_pylist(alerts, schema=schema), pq_path)
    # One JSON per run, so parallel backfills never fight over the DuckDB file lock;
    # `load_warehouse` folds them into DuckDB afterwards.
    (WAREHOUSE / f"run_{run}.json").write_text(json.dumps({"run": run, "audit": audit, "extra": extra or {}}, indent=2))
    return {"run": run, "alerts": len(alerts), "audit": audit, "parquet": str(pq_path.relative_to(ROOT))}


def load_warehouse() -> dict:
    """Rebuild data/warehouse/cablewatch.duckdb from every run's Parquet and audit JSON."""
    db = WAREHOUSE / "cablewatch.duckdb"
    db.unlink(missing_ok=True)
    con = duckdb.connect(str(db))
    con.execute("INSTALL spatial; LOAD spatial;")
    runs = sorted(WAREHOUSE.glob("run_*.json"))
    con.execute("CREATE TABLE runs (run VARCHAR PRIMARY KEY, audit JSON, extra JSON)")
    for r in runs:
        d = json.loads(r.read_text())
        con.execute("INSERT INTO runs VALUES (?, ?, ?)", [d["run"], json.dumps(d["audit"]), json.dumps(d["extra"])])
    con.execute(f"""CREATE TABLE alerts AS SELECT *, regexp_extract(filename, 'alerts_(.*)\\.parquet', 1) AS run,
                    ST_Point(lon, lat) AS geom FROM read_parquet('{WAREHOUSE}/alerts_*.parquet', filename=true)""")
    n = con.execute("SELECT count(*) FROM alerts").fetchone()[0]
    con.close()
    return {"runs": len(runs), "alerts": n, "db": str(db.relative_to(ROOT))}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("inputs", nargs="+", type=Path)
    b.add_argument("--run", required=True)
    b.add_argument("--agnostic", action="store_true", help="evaluate behavior rules everywhere, no cable gating")
    sub.add_parser("warehouse")
    s = sub.add_parser("stream")
    s.add_argument("--run", required=True)
    s.add_argument("--group", default="cablewatch-processor")
    s.add_argument("--idle-timeout", type=float, default=10.0)
    a = ap.parse_args()

    t0 = time.monotonic()
    if a.cmd == "warehouse":
        print(json.dumps(load_warehouse(), indent=2))
        return
    if a.cmd == "backfill":
        index = None if a.agnostic else build_index()
        proc, _ = run_rows(iter_raw(a.inputs), index)
        res = write_sinks(a.run, proc, {"inputs": [str(p) for p in a.inputs], "agnostic": a.agnostic})
    else:
        bus = get_bus()
        proc = Processor(build_index(), DEFAULT)
        for row in bus.consume(RAW_TOPIC, a.group, a.idle_timeout):
            p, reason = parse_dma_row(row)
            if p is None:
                proc.reject_raw(reason)
                continue
            n_late = len(proc.late)
            for al in proc.push(p):
                bus.produce(ALERT_TOPIC, str(al.mmsi), al.to_dict())
            if len(proc.late) > n_late:
                bus.produce(LATE_TOPIC, str(p.mmsi), p.to_dict())
        for al in proc.flush():
            bus.produce(ALERT_TOPIC, str(al.mmsi), al.to_dict())
        bus.flush()
        res = write_sinks(a.run, proc, {"source": RAW_TOPIC})
    res["seconds"] = round(time.monotonic() - t0, 1)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
