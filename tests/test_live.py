"""The live consumer against a local WebSocket server replaying recorded-format messages.

The messages are built from the hand-made scenario tracks in aisstream's documented JSON
shape (they are NOT a capture from aisstream.io, which needs an account). The test checks
that rows coming through the socket produce exactly the alerts the same tracks produce
when fed to the processor directly.
"""
import asyncio
import json

from cablewatch.engine import Processor
from cablewatch.live_aisstream import consume, ship_type_name, to_row
from cablewatch.schema import parse_dma_row
from scenarios import eastbound_with_drop, loiter


def as_aisstream(p):
    from datetime import datetime, timezone

    t = datetime.fromtimestamp(p.ts / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000000000 +0000 UTC")
    nav = {"Under way using engine": 0, "At anchor": 1}[p.nav_status]
    return {"MessageType": "PositionReport",
            "MetaData": {"MMSI": p.mmsi, "ShipName": p.name, "Latitude": p.lat, "Longitude": p.lon, "time_utc": t},
            "Message": {"PositionReport": {"UserID": p.mmsi, "Latitude": p.lat, "Longitude": p.lon, "Sog": p.sog,
                                           "Cog": p.cog, "TrueHeading": int(p.heading), "NavigationalStatus": nav}}}


def static_msg(mmsi):
    return {"MessageType": "ShipStaticData", "MetaData": {"MMSI": mmsi},
            "Message": {"ShipStaticData": {"UserID": mmsi, "Name": "TEST VESSEL", "ImoNumber": 9000001, "Type": 70,
                                           "Dimension": {"A": 120, "B": 30, "C": 10, "D": 10}}}}


def test_ship_type_codes():
    assert ship_type_name(30) == "Fishing" and ship_type_name(74) == "Cargo" and ship_type_name(84) == "Tanker"


def test_to_row_merges_static():
    static = {}
    assert to_row(static_msg(219000001), static) is None
    p = eastbound_with_drop()[0]
    row = to_row(as_aisstream(p), static)
    parsed, reason = parse_dma_row(row)
    assert reason is None and parsed.imo == "9000001" and parsed.ship_type == "Cargo" and parsed.length == 150
    assert parsed.ts == p.ts


def test_consumer_over_local_websocket(index, cfg):
    from websockets.asyncio.server import serve

    tracks = eastbound_with_drop() + loiter(minutes=40)
    msgs = [static_msg(219000001), static_msg(219000003)] + [as_aisstream(p) for p in sorted(tracks, key=lambda p: p.ts)]

    async def handler(ws):
        sub = json.loads(await ws.recv())
        assert sub["APIKey"] == "test-key" and sub["BoundingBoxes"]
        for m in msgs:
            await ws.send(json.dumps(m).encode())

    rows = []

    async def go():
        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            await consume(f"ws://127.0.0.1:{port}", "test-key", rows.append, max_rows=len(tracks), reconnect=False)

    asyncio.run(go())
    assert len(rows) == len(tracks)

    def run(positions):
        proc = Processor(index, cfg)
        for p in positions:
            proc.push(p)
        proc.flush()
        return sorted((a.ts, a.mmsi, a.rule) for a in proc.alerts)

    via_socket = run([parse_dma_row(r)[0] for r in rows])
    direct = run(sorted(tracks, key=lambda p: p.sort_key()))
    assert via_socket == direct and direct
