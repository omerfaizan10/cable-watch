#!/usr/bin/env bash
# Download one DMA daily file (resumable), extract the Baltic box to
# data/processed/raw_<day>.parquet, then delete the zip. Used by fetch_all.sh.
set -uo pipefail
cd "$(dirname "$0")/.."
d=$1
BBOX="9.5,53.5,24,60.5"
zip="data/raw/aisdk-$d.zip"
log="data/processed/_fetch_$d.log"
if .venv/bin/python -m cablewatch.download "$d" "$zip" > "$log" 2>&1 \
   && .venv/bin/python -m cablewatch.dma_archive day "$d" --bbox "$BBOX" --local-zip "$zip" \
        --out "data/processed/raw_$d.parquet" >> "$log" 2>&1; then
  rm -f "$zip"
  echo "done $d"
else
  echo "FAILED $d (see $log)"
fi
