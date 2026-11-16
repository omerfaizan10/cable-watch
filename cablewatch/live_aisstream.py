"""Live consumer for aisstream.io (wss://stream.aisstream.io/v0/stream).

It converts each PositionReport into the same row shape as a DMA CSV row and publishes it
to the raw topic, so the live path and the archive replay share every line of processing
code after this file. ShipStaticData messages fill a per-MMSI cache (name, IMO, type,
length) that is merged into later position rows, the way DMA rows carry static fields.

Needs AISSTREAM_API_KEY in .env (free account at aisstream.io). Without a key it exits
with a message; the site never depends on this process.

Protocol facts used here (aisstream.io/documentation, read 2026-11-14): connect with
permessage-deflate, send one JSON subscription within 3 s with APIKey and BoundingBoxes
as [[lat, lon], [lat, lon]] pairs, frames are binary UTF-8 JSON, MessageType selects the
object under Message, MetaData carries the MMSI. Reconnect with backoff; the service does
not replay missed messages.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from datetime import datetime, timezone
from typing import Awaitable, Callable

URL = "wss://stream.aisstream.io/v0/stream"
# Western Baltic, Danish straits and the Gulf of Finland, as [[lat, lon], [lat, lon]].
DEFAULT_BOXES = [[[53.5, 9.5], [60.8, 30.5]]]

NAV_STATUS = {
    0: "Under way using engine", 1: "At anchor", 2: "Not under command", 3: "Restricted manoeuverability",
    4: "Constrained by her draught", 5: "Moored", 6: "Aground", 7: "Engaged in fishing",
    8: "Under way sailing", 15: "Unknown value",
}


def ship_type_name(code: int | None) -> str:
    """AIS ship type code (ITU-R M.1371 table 53) to the labels DMA uses."""
    if code is None:
        return "Undefined"
    fixed = {30: "Fishing", 31: "Towing", 32: "Towing long/wide", 33: "Dredging", 34: "Diving", 35: "Military",
             36: "Sailing", 37: "Pleasure", 50: "Pilot", 51: "SAR", 52: "Tug", 53: "Port tender",
             54: "Anti-pollution", 55: "Law enforcement", 58: "Medical"}
    if code in fixed:
        return fixed[code]
    for lo, label in ((40, "HSC"), (60, "Passenger"), (70, "Cargo"), (80, "Tanker"), (90, "Other")):
        if lo <= code <= lo + 9:
            return label
    return "Undefined"


def _fmt_ts(meta: dict, now: datetime) -> str:
    raw = meta.get("time_utc")
    dt = None
    if isinstance(raw, str):
        # aisstream sends e.g. "2024-05-01 12:00:00.123456789 +0000 UTC"
        try:
            dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            dt = None
    dt = dt or now
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def to_row(msg: dict, static: dict[int, dict], now: datetime | None = None) -> dict | None:
    """aisstream message -> DMA-shaped row (strings), or None for non-position messages."""
    now = now or datetime.now(timezone.utc)
    mtype = msg.get("MessageType")
    body = (msg.get("Message") or {}).get(mtype) or {}
    meta = msg.get("MetaData") or {}
    if mtype == "ShipStaticData":
        mmsi = int(body.get("UserID") or meta.get("MMSI") or 0)
        dim = body.get("Dimension") or {}
        length = (dim.get("A") or 0) + (dim.get("B") or 0)
        static[mmsi] = {"Name": str(body.get("Name") or meta.get("ShipName") or "").strip(),
                        "IMO": str(body.get("ImoNumber") or ""), "Ship type": ship_type_name(body.get("Type")),
                        "Length": str(length) if length else ""}
        return None
    if mtype not in ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport"):
        return None
    mmsi = int(body.get("UserID") or meta.get("MMSI") or 0)
    st = static.get(mmsi, {})
    hdg = body.get("TrueHeading")
    return {
        "# Timestamp": _fmt_ts(meta, now),
        "Type of mobile": "Class A" if mtype == "PositionReport" else "Class B",
        "MMSI": str(mmsi),
        "Latitude": str(body.get("Latitude", meta.get("Latitude", ""))),
        "Longitude": str(body.get("Longitude", meta.get("Longitude", ""))),
        "Navigational status": NAV_STATUS.get(body.get("NavigationalStatus"), "Unknown value"),
        "SOG": str(body.get("Sog", "")),
        "COG": str(body.get("Cog", "")),
        "Heading": str(hdg) if hdg is not None else "",
        "IMO": st.get("IMO", ""),
        "Name": st.get("Name", str(meta.get("ShipName") or "").strip()),
        "Ship type": st.get("Ship type", "Undefined"),
        "Length": st.get("Length", ""),
        "Data source type": "aisstream",
    }


async def consume(url: str, api_key: str, on_row: Callable[[dict], Awaitable[None] | None],
                  boxes=DEFAULT_BOXES, max_rows: int | None = None, reconnect: bool = True) -> int:
    from websockets.asyncio.client import connect

    static: dict[int, dict] = {}
    n = 0
    backoff = 1.0
    while True:
        try:
            async with connect(url, compression="deflate", open_timeout=10) as ws:
                await ws.send(json.dumps({"APIKey": api_key, "BoundingBoxes": boxes,
                                          "FilterMessageTypes": ["PositionReport", "ShipStaticData",
                                                                 "StandardClassBPositionReport"]}))
                backoff = 1.0
                async for frame in ws:
                    msg = json.loads(frame.decode() if isinstance(frame, bytes) else frame)
                    row = to_row(msg, static)
                    if row is None:
                        continue
                    res = on_row(row)
                    if asyncio.iscoroutine(res):
                        await res
                    n += 1
                    if max_rows is not None and n >= max_rows:
                        return n
            if not reconnect:
                return n
        except (OSError, asyncio.TimeoutError) as e:  # network trouble: back off and retry
            if not reconnect:
                raise
            print(f"connection lost ({e}); retrying in {backoff:.0f} s", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 (websockets raises ConnectionClosed subclasses)
            if not reconnect:
                return n
            print(f"stream closed ({type(e).__name__}); retrying in {backoff:.0f} s", file=sys.stderr)
        await asyncio.sleep(backoff + random.random())
        backoff = min(backoff * 2, 60)


async def collect(api_key: str, seconds: float, boxes=DEFAULT_BOXES) -> list[dict]:
    """Every position row received in `seconds` of wall-clock time."""
    rows: list[dict] = []

    def keep(row: dict) -> None:
        row["_received_utc"] = datetime.now(timezone.utc)
        rows.append(row)

    try:
        await asyncio.wait_for(consume(URL, api_key, keep, boxes=boxes), timeout=seconds)
    except asyncio.TimeoutError:
        pass
    return rows


def check(api_key: str, seconds: float) -> dict:
    """Listen for `seconds`, then push the rows through the same processor as the archive replay
    in the order they arrived, as the bus would deliver them, and summarise."""
    from collections import Counter
    from pathlib import Path

    from .config import DEFAULT
    from .pipeline import WAREHOUSE, build_index, run_rows

    t0 = datetime.now(timezone.utc)
    rows = asyncio.run(collect(api_key, seconds))
    received = [r.pop("_received_utc") for r in rows]
    proc, _ = run_rows(rows, build_index(), DEFAULT)
    audit = proc.audit()
    mmsis = {r["MMSI"] for r in rows}
    named = {r["MMSI"] for r in rows if r.get("Name")}
    lags = []  # receive time minus the message's own timestamp
    for r, got in zip(rows, received):
        try:
            ts = datetime.strptime(r["# Timestamp"], "%d/%m/%Y %H:%M:%S").replace(tzinfo=timezone.utc)
            lags.append((got - ts).total_seconds())
        except ValueError:
            pass
    out = {
        "started_utc": t0.isoformat(timespec="seconds"),
        "seconds": seconds,
        "boxes": DEFAULT_BOXES,
        "rows": len(rows),
        "rows_per_second": round(len(rows) / seconds, 1) if seconds else None,
        "vessels": len(mmsis),
        "vessels_with_static_data": len(named),
        "rows_per_vessel_median": sorted(Counter(r["MMSI"] for r in rows).values())[len(mmsis) // 2] if rows else None,
        "rows_per_vessel_max": max(Counter(r["MMSI"] for r in rows).values(), default=None),
        "lag_seconds_median": round(sorted(lags)[len(lags) // 2], 1) if lags else None,
        "lag_seconds_p95": round(sorted(lags)[int(len(lags) * 0.95)], 1) if lags else None,
        "message_types": dict(Counter(r["Type of mobile"] for r in rows)),
        "nav_status": dict(Counter(r["Navigational status"] for r in rows).most_common(6)),
        "lat_range": [min((float(r["Latitude"]) for r in rows), default=None), max((float(r["Latitude"]) for r in rows), default=None)],
        "lon_range": [min((float(r["Longitude"]) for r in rows), default=None), max((float(r["Longitude"]) for r in rows), default=None)],
        "audit": audit,
        "alerts": [a.to_dict() for a in proc.alerts],
    }
    Path(WAREHOUSE).mkdir(parents=True, exist_ok=True)
    (WAREHOUSE / "live_check.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def main() -> None:
    import argparse

    from dotenv import load_dotenv

    from .bus import RAW_TOPIC, get_bus

    ap = argparse.ArgumentParser()
    ap.add_argument("--check", type=float, metavar="SECONDS",
                    help="listen for SECONDS, run the rows through the processor and write data/warehouse/live_check.json")
    args = ap.parse_args()
    load_dotenv()
    key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if not key:
        sys.exit("AISSTREAM_API_KEY is not set. Create a free key at https://aisstream.io and put it in .env.")
    if args.check:
        out = check(key, args.check)
        print(json.dumps({k: v for k, v in out.items() if k != "alerts"}, indent=2))
        print(f"{len(out['alerts'])} alerts")
        return
    bus = get_bus()

    def publish(row: dict) -> None:
        bus.produce(RAW_TOPIC, row["MMSI"], row)

    try:
        asyncio.run(consume(URL, key, publish))
    finally:
        bus.flush()


if __name__ == "__main__":
    main()
