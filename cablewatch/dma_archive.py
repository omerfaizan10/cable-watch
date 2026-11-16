"""Danish Maritime Authority historical AIS archive (http://aisdata.ais.dk/).

Verified facts about the archive (index at https://web.ais.dk/aisdata/, checked 2026-11-14):
  * 2006-03 to 2024-02 are MONTHLY zips of 11 to 32 GB each (aisdk-YYYY-MM.zip);
  * from 2024-03-01 on there is one zip per DAY, about 400 to 720 MB (aisdk-YYYY-MM-DD.zip);
  * each zip holds one CSV; columns are listed in !_README_information_CSV_files.txt;
  * coverage is what Danish shore stations receive: Danish straits, Kattegat, Skagerrak,
    western Baltic and the waters around Bornholm. It does not reach the Gulf of Finland.

To stay inside a ~15 GB disk budget the downloader never stores a full CSV. It streams the
zip over HTTP, inflates it on the fly, and keeps only rows inside a bounding box (and,
optionally, a time window). The kept rows are written as strings, exactly as received, to
Parquet, so the replay producer and the row-count audit see the real raw records.

Usage:
  python -m cablewatch.dma_archive day 2024-11-17 --bbox 9,53.5,17.5,58.5
  python -m cablewatch.dma_archive window 2022-02 --start "2022-02-25 00:00" --end "2022-02-26 12:00" \
      --bbox 13.5,54.6,15.6,55.9 --out data/processed/raw_samus_swan.parquet
"""
from __future__ import annotations

import argparse
import csv
import math
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


BASE = "http://aisdata.ais.dk"
UA = {"User-Agent": "cablewatch-research/0.1"}
ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
CACHE = ROOT / "data" / "raw"


def url_for(period: str) -> str:
    """period is YYYY-MM-DD (daily files, 2024-03-01 on) or YYYY-MM (monthly files)."""
    year = period[:4]
    return f"{BASE}/{year}/aisdk-{period}.zip"


def ts_sort_key(s: str) -> str:
    """'31/12/2015 23:59:59' -> '20151231 23:59:59', so string comparison is time order."""
    return s[6:10] + s[3:5] + s[0:2] + s[10:19]


def filter_lines(lines, bbox, t0_key=None, t1_key=None, stats=None, coverage=None, stop_after_key=None):
    """Yield raw CSV rows (dict of str) inside bbox and [t0_key, t1_key).

    Works on raw text lines first (cheap string slicing) and only runs the csv parser on
    rows that survive, which is what makes a 400-million-row monthly file tractable.
    Every line is counted in exactly one bucket of `stats`. `coverage` (a Counter) gets
    the number of fixes per 0.1 degree cell for every row with a parseable position, which
    is how the archive's real receiving range is measured rather than assumed.
    If `stop_after_key` is set, reading stops after 200,000 consecutive rows past it
    (monthly files are written in time order, give or take a few minutes).
    """
    lon0, lat0, lon1, lat1 = bbox
    it = iter(lines)
    header_line = next(it)
    header = next(csv.reader([header_line]))
    past = 0
    for line in it:
        stats["seen"] += 1
        tk = ts_sort_key(line[:19])
        if stop_after_key is not None:
            if tk > stop_after_key:
                past += 1
                if past >= 200_000:
                    stats["stopped_early"] = 1
                    return
            else:
                past = 0
        if (t0_key is not None and tk < t0_key) or (t1_key is not None and tk >= t1_key):
            stats["outside_window"] += 1
            continue
        parts = line.split(",", 5)
        try:
            lat = float(parts[3])
            lon = float(parts[4])
        except (IndexError, ValueError):
            stats["unparseable_latlon"] += 1
            continue
        if coverage is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            coverage[(math.floor(lat * 10), math.floor(lon * 10))] += 1
        if not (lat0 <= lat <= lat1 and lon0 <= lon <= lon1):
            stats["outside_bbox"] += 1
            continue
        vals = next(csv.reader([line]))
        stats["kept"] += 1
        yield dict(zip(header, vals))


def _zip_from_local(path: Path):
    zf = zipfile.ZipFile(path)
    name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
    return io.TextIOWrapper(zf.open(name), encoding="utf-8", errors="replace", newline="")


def _zip_streamed(url: str):
    """Inflate a remote zip while it downloads (needs the stream-unzip package)."""
    import httpx
    from stream_unzip import stream_unzip

    def chunks():
        with httpx.stream("GET", url, headers=UA, timeout=None, follow_redirects=True) as r:
            r.raise_for_status()
            yield from r.iter_bytes(1 << 20)

    for fname, _size, content in stream_unzip(chunks()):
        if fname.decode(errors="replace").lower().endswith(".csv"):
            buf = b""
            for piece in content:
                buf += piece
                *lines, buf = buf.split(b"\n")
                for ln in lines:
                    yield ln.decode("utf-8", errors="replace") + "\n"
            if buf:
                yield buf.decode("utf-8", errors="replace")
        else:
            for _ in content:
                pass


def extract(period: str, bbox, out: Path, start: str | None = None, end: str | None = None,
            local_zip: Path | None = None) -> dict:
    from collections import Counter

    def key(iso):
        d = datetime.fromisoformat(iso)
        return d.strftime("%Y%m%d %H:%M:%S")

    t0, t1 = (key(start) if start else None), (key(end) if end else None)
    stop = None
    if end:
        stop = (datetime.fromisoformat(end) + timedelta(hours=6)).strftime("%Y%m%d %H:%M:%S")
    stats: Counter = Counter()
    coverage: Counter = Counter()
    lines = _zip_from_local(local_zip) if local_zip else _zip_streamed(url_for(period))
    out.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temporary name and rename at the end, so an interrupted run never leaves a
    # truncated file that a later run would mistake for a finished day.
    tmp = out.with_name(out.name + ".partial")
    writer = None
    batch: list[dict] = []
    cols: list[str] | None = None

    def write(b):
        nonlocal writer
        tbl = pa.Table.from_pylist(b, schema=pa.schema([(c, pa.string()) for c in cols]))
        if writer is None:
            writer = pq.ParquetWriter(tmp, tbl.schema, compression="zstd")
        writer.write_table(tbl)

    for row in filter_lines(lines, bbox, t0, t1, stats, coverage, stop):
        if cols is None:
            cols = list(row.keys())
        batch.append({c: row.get(c) for c in cols})
        if len(batch) >= 200_000:
            write(batch)
            batch = []
    if batch:
        write(batch)
    if writer:
        writer.close()
        tmp.replace(out)
    manifest = {
        "period": period, "source": local_zip.name if local_zip else url_for(period), "bbox": list(bbox),
        "start": start, "end": end, "out": str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out),
        "extracted_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **dict(stats),
    }
    out.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2))
    out.with_suffix(".coverage.json").write_text(json.dumps(
        [[la / 10, lo / 10, n] for (la, lo), n in sorted(coverage.items())]))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["day", "window"])
    ap.add_argument("period")
    ap.add_argument("--bbox", default="9,53.5,17.5,58.5", help="lon0,lat0,lon1,lat1")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--local-zip", type=Path, help="use an already downloaded zip instead of streaming")
    a = ap.parse_args()
    bbox = tuple(float(x) for x in a.bbox.split(","))
    out = a.out or PROC / f"raw_{a.period}.parquet"
    print(json.dumps(extract(a.period, bbox, out, a.start, a.end, a.local_zip), indent=2))


if __name__ == "__main__":
    main()
