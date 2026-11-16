#!/usr/bin/env bash
# Streams the DMA days used by the backtest and the normal-traffic sample.
# Raw zips are never stored; only rows inside the Baltic box are kept (Parquet, strings).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
BBOX="9.5,53.5,24,60.5"
INCIDENT_DAYS="2024-11-17 2024-11-18 2024-12-25 2025-01-26"
# Ordinary days: picked by scripts/pick_normal_days.py (seeded, 2 or 3 per month).
NORMAL_DAYS=$(cat data/reference/normal_days.txt)
JOBS=${JOBS:-3}
for d in $INCIDENT_DAYS $NORMAL_DAYS; do
  out=data/processed/raw_$d.parquet
  [ -f "$out" ] && { echo "skip $d" >&2; continue; }
  echo "$d"
done | xargs -P "$JOBS" -n 1 scripts/fetch_day.sh

# Samus Swan, Bornholm cable, 2022-02-26 05:17 UTC. Only a monthly file exists (14.4 GB);
# it is streamed and only the 36 h window around the break is kept.
out=data/processed/raw_2022-02-25_26.parquet
[ -f "$out" ] || $PY -m cablewatch.dma_archive window 2022-02 --start "2022-02-25T00:00:00" --end "2022-02-26T12:00:00" --bbox "$BBOX" --out "$out"
