"""Replay producer: plays archived DMA rows onto the raw topic in event-time order.

Arrival model. Every row gets an arrival time = event time + delay:
  * delay ~ Uniform(0, jitter_ms) for normal rows, which reorders rows but never by more
    than jitter_ms, so with jitter_ms <= allowed lateness nothing should be dropped;
  * with probability late_fraction, delay = allowed_lateness + Uniform(1 s, late_extra_ms),
    which guarantees the row is behind the bound and must be counted as late.
Rows are emitted in arrival order. speed=0 emits as fast as possible; speed=60 plays one
hour of traffic per minute of wall clock. A fixed seed makes the disorder reproducible.

Usage:
  python -m cablewatch.replay data/processed/raw_2024-11-17.parquet --speed 0 \
      --jitter-ms 90000 --late-fraction 0.001
"""
from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

import pyarrow.parquet as pq

from .bus import RAW_TOPIC, get_bus
from .config import DEFAULT
from .schema import parse_dma_timestamp


def arrival_schedule(rows: list[dict], jitter_ms: int, late_fraction: float, lateness_ms: int,
                     late_extra_ms: int = 600_000, seed: int = 7) -> list[tuple[int, int, dict, bool]]:
    """Return [(arrival_ms, seq, row, injected_late)] sorted by arrival. Rows whose timestamp
    cannot be parsed keep arrival = previous arrival so they still flow through and get
    rejected (and counted) by the processor."""
    rng = random.Random(seed)
    out = []
    last_ok = 0
    for seq, row in enumerate(rows):
        ts_raw = row.get("# Timestamp") or row.get("Timestamp") or ""
        try:
            ts = parse_dma_timestamp(ts_raw)
            last_ok = ts
        except ValueError:
            ts = last_ok
        late = rng.random() < late_fraction
        if late:
            delay = lateness_ms + rng.randint(1_000, late_extra_ms)
        else:
            delay = rng.randint(0, jitter_ms) if jitter_ms > 0 else 0
        out.append((ts + delay, seq, row, late))
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def read_raw(path: Path) -> list[dict]:
    return pq.read_table(path).to_pylist()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--speed", type=float, default=0.0)
    ap.add_argument("--jitter-ms", type=int, default=0)
    ap.add_argument("--late-fraction", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--topic", default=RAW_TOPIC)
    args = ap.parse_args()

    bus = get_bus()
    if hasattr(bus, "reset"):
        bus.reset(args.topic)
    rows: list[dict] = []
    for p in args.inputs:
        rows.extend(read_raw(p))
    sched = arrival_schedule(rows, args.jitter_ms, args.late_fraction, DEFAULT.allowed_lateness_ms, seed=args.seed)
    t0_wall = time.monotonic()
    t0_evt = sched[0][0] if sched else 0
    n_late = 0
    for arr, _, row, late in sched:
        if args.speed > 0:
            due = (arr - t0_evt) / 1000 / args.speed
            wait = due - (time.monotonic() - t0_wall)
            if wait > 0:
                time.sleep(wait)
        n_late += late
        bus.produce(args.topic, str(row.get("MMSI", "")), row)
    bus.flush()
    print(f"produced {len(sched)} rows to {args.topic} ({n_late} injected late)")


if __name__ == "__main__":
    main()
