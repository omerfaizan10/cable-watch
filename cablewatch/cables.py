"""Cable routes from EMODnet Human Activities (CC BY 4.0, data originator Cogea Srl).

EMODnet publishes the cable layers through a GeoServer WFS at
https://ows.emodnet-humanactivities.eu/wfs . Layer names (from the dataset metadata records):
  telecom, actual routes: emodnet:bshcontiscables, emodnet:cicacables, emodnet:shomcables,
                          emodnet:sigcables, emodnet:maltacables, emodnet:rijkscables,
                          emodnet:ukfibrecables
  power, actual routes:   emodnet:pcablesbshcontis, emodnet:pcablesshom, emodnet:pcablesnve,
                          emodnet:pcablesrijks
OpenStreetMap (ODbL) is the second source. EMODnet's Baltic coverage is mostly German (BSH)
and Norwegian (NVE) data, so Danish and Swedish routes such as the Bornholm cable are
missing there. `fetch-osm` pulls submarine power and telecom ways from the Overpass API
for the chart area. An OSM way that runs along an EMODnet route of the same kind is
dropped, so one cable is never counted twice.

`fetch` asks GetCapabilities for every layer whose name contains "cable", requests each as
GeoJSON clipped to the Baltic bounding box, and stores the result untouched together with a
manifest. Nothing here invents geometry: a cable missing from EMODnet stays missing and is
listed in docs/DATA.md.

Usage:
  python -m cablewatch.cables fetch      # writes data/reference/emodnet_cables_raw.geojson
  python -m cablewatch.cables fetch-osm  # writes data/reference/osm_cables_raw.json
  python -m cablewatch.cables summarize  # prints which layers have Baltic features
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from .geo import Cable

WFS = "https://ows.emodnet-humanactivities.eu/wfs"
UA = {"User-Agent": "cablewatch-research/0.1"}
REF = Path(__file__).resolve().parent.parent / "data" / "reference"
RAW_GEOJSON = REF / "emodnet_cables_raw.geojson"
OSM_JSON = REF / "osm_cables_raw.json"
# Ways fetched one by one from the main OSM API (api.openstreetmap.org), for routes the backtest
# depends on. Used on their own when the bulk Overpass download is unavailable, merged otherwise.
OSM_PINNED = {168326669: "Bornholm Cable, Sweden to Bornholm (missing from EMODnet)"}
OSM_PINNED_JSON = REF / "osm_pinned_ways.json"
OVERPASS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
OSM_BBOX = (9.5, 53.6, 19.5, 58.6)  # lon_min, lat_min, lon_max, lat_max: DMA receivers hear ships to about 18.6 E
DUP_TOLERANCE_M = 1_000.0
MAX_ATTEMPTS = 200  # public Overpass servers can be overloaded for hours; finished tiles are cached
BALTIC_BBOX = (9.0, 53.0, 31.0, 66.5)  # lon_min, lat_min, lon_max, lat_max
POWER_PREFIX = "pcables"
# Routes that are not on the seabed (yet) or no longer carry anything are left out.
EXCLUDED_STATUS = {"planned", "approved", "outofuse", "out of use", "decommissioned", "application submitted"}
NAME_KEYS = ("name_", "navn", "name", "NAME", "Name", "cable_name", "CABLE_NAME", "cablename", "title", "nom", "label")


def cable_layers_from_capabilities(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    names = []
    for el in root.iter():
        if el.tag.endswith("FeatureType"):
            for ch in el:
                if ch.tag.endswith("Name") and ch.text and ("cable" in ch.text.lower() or ch.text.lower().endswith(":pipelines")):
                    names.append(ch.text)
    return sorted(set(names))


def fetch() -> None:
    import httpx

    REF.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=UA, timeout=120) as c:
        caps = c.get(WFS, params={"service": "WFS", "request": "GetCapabilities", "version": "2.0.0"})
        caps.raise_for_status()
        layers = cable_layers_from_capabilities(caps.content)
        feats, manifest = [], []
        lon0, lat0, lon1, lat1 = BALTIC_BBOX
        for layer in layers:
            r = c.get(WFS, params={
                "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": layer,
                "outputFormat": "application/json", "srsName": "EPSG:4326",
                "bbox": f"{lon0},{lat0},{lon1},{lat1},EPSG:4326",
            })
            ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json")
            n = 0
            if ok:
                for f in r.json().get("features", []):
                    f.setdefault("properties", {})["_layer"] = layer
                    feats.append(f)
                    n += 1
            manifest.append({"layer": layer, "http_status": r.status_code, "features_in_bbox": n})
    RAW_GEOJSON.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    (REF / "emodnet_cables_manifest.json").write_text(json.dumps({
        "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wfs": WFS, "bbox": BALTIC_BBOX, "license": "CC BY 4.0, EMODnet Human Activities, originator Cogea Srl",
        "layers": manifest,
    }, indent=2))
    for m in manifest:
        print(m)


def _overpass_query(bbox: tuple[float, float, float, float]) -> str:
    lon0, lat0, lon1, lat1 = bbox
    b = f"({lat0},{lon0},{lat1},{lon1})"
    return f"""[out:json][timeout:80];
(way["seamark:type"="cable_submarine"]{b};
 way["power"="cable"]["location"~"^(underwater|submarine)$"]{b};
 way["communication"="line"]["location"~"^(underwater|submarine)$"]{b};);
out geom;"""


def fetch_osm() -> None:
    """Overpass in 1 x 1 degree tiles (a single chart-sized query times out on the public
    servers). Each tile is cached under data/reference/osm_tiles/, so a rerun only asks for
    the tiles that failed."""
    import time

    import httpx

    lon0, lat0, lon1, lat1 = OSM_BBOX
    tiles = []
    x = lon0
    while x < lon1:
        y = lat0
        while y < lat1:
            tiles.append((round(x, 2), round(y, 2), round(min(x + 1, lon1), 2), round(min(y + 1, lat1), 2)))
            y += 1
        x += 1
    cache = REF / "osm_tiles"
    cache.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=UA, timeout=httpx.Timeout(100, connect=20)) as c:
        for i, t in enumerate(tiles, 1):
            f = cache / ("tile_%s_%s.json" % (t[0], t[1]))
            if f.exists():
                continue
            for attempt in range(MAX_ATTEMPTS):
                url = OVERPASS[attempt % len(OVERPASS)]
                try:
                    r = c.post(url, data={"data": _overpass_query(t)})
                    if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
                        f.write_text(r.text)
                        print(f"tile {i}/{len(tiles)} {t}: {len(r.json().get('elements', []))} ways", flush=True)
                        break
                    print(f"tile {i} {url.split('/')[2]} HTTP {r.status_code}", flush=True)
                except httpx.HTTPError as e:
                    print(f"tile {i} {url.split('/')[2]} {type(e).__name__}", flush=True)
                time.sleep(min(300, 10 * (attempt + 1)))
            else:
                raise RuntimeError(f"Overpass failed for tile {t}; rerun to resume")
    ways: dict[int, dict] = {}
    for f in sorted(cache.glob("tile_*.json")):
        for e in json.loads(f.read_text()).get("elements", []):
            if e.get("type") == "way" and e.get("geometry"):
                ways[e["id"]] = e
    OSM_JSON.write_text(json.dumps({
        "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "OpenStreetMap contributors, ODbL 1.0, via the Overpass API",
        "bbox": OSM_BBOX, "tiles": len(tiles), "ways": sorted(ways.values(), key=lambda w: w["id"]),
    }))
    print(f"{len(ways)} OSM ways from {len(tiles)} tiles", flush=True)


def fetch_osm_pinned() -> None:
    import httpx

    ways = []
    with httpx.Client(headers=UA, timeout=60) as c:
        for wid, why in OSM_PINNED.items():
            r = c.get(f"https://api.openstreetmap.org/api/0.6/way/{wid}/full.json")
            r.raise_for_status()
            els = r.json()["elements"]
            nodes = {e["id"]: e for e in els if e["type"] == "node"}
            way = next(e for e in els if e["type"] == "way")
            ways.append({"type": "way", "id": wid, "tags": way.get("tags", {}), "version": way.get("version"),
                         "geometry": [{"lat": nodes[n]["lat"], "lon": nodes[n]["lon"]} for n in way["nodes"]],
                         "why": why})
            print(f"way {wid} v{way.get('version')}: {way.get('tags', {}).get('name')}, {len(way['nodes'])} nodes")
    OSM_PINNED_JSON.write_text(json.dumps({
        "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "OpenStreetMap contributors, ODbL 1.0, via api.openstreetmap.org", "ways": ways}, indent=1))


# Tags that mean the cable is not (or no longer) on the seabed carrying anything.
OSM_INACTIVE = ("construction", "proposed", "planned", "disused", "abandoned", "removed", "razed")


def osm_kind(tags: dict) -> str | None:
    if any(k.split(":")[0] in OSM_INACTIVE or tags.get(k) in OSM_INACTIVE for k in tags):
        return None
    if tags.get("power") == "cable" or tags.get("seamark:cable_submarine:category") == "power":
        return "power"
    if tags.get("communication") == "line" or tags.get("seamark:cable_submarine:category") in ("telephone", "telecom"):
        return "telecom"
    return None


def osm_ways(path: Path = OSM_JSON, pinned: Path = OSM_PINNED_JSON) -> list[dict]:
    """Bulk Overpass ways plus pinned ways, one copy per way id."""
    ways: dict[int, dict] = {}
    for p in (path, pinned):
        if p and Path(p).exists():
            for w in json.loads(Path(p).read_text())["ways"]:
                ways[w["id"]] = w
    return [ways[k] for k in sorted(ways)]


def load_osm(existing: list[Cable], path: Path = OSM_JSON, pinned: Path | None = OSM_PINNED_JSON) -> list[Cable]:
    ways = osm_ways(path, pinned)
    if not ways:
        return []
    from shapely.geometry import LineString, Point

    from .geo import haversine_m

    def _nearest(other, la, lo):
        q = other.interpolate(other.project(Point(lo, la)))
        return q.y, q.x

    lines_by_kind: dict[str, list] = {}
    for c in existing:
        lines_by_kind.setdefault(c.kind, []).append(LineString([(lo, la) for la, lo in c.line]))
    out = []
    for w in ways:
        tags = w.get("tags") or {}
        kind = osm_kind(tags)
        if not kind:
            continue
        line = [(p["lat"], p["lon"]) for p in w["geometry"]]
        if len(line) < 2:
            continue
        # Duplicate of an EMODnet route: every vertex within DUP_TOLERANCE_M of one same-kind line.
        mine = LineString([(lo, la) for la, lo in line])
        pad = DUP_TOLERANCE_M / 60_000  # degrees, generous at Baltic latitudes
        dup = False
        for other in lines_by_kind.get(kind, []):
            if not mine.buffer(pad).intersects(other):
                continue
            if all(haversine_m(la, lo, *_nearest(other, la, lo)) <= DUP_TOLERANCE_M for la, lo in line):
                dup = True
                break
        if dup:
            continue
        name = tags.get("name") or tags.get("name:en") or tags.get("ref") or f"OSM way {w['id']}"
        out.append(Cable(cable_id=f"osm.{w['id']}", name=name, kind=kind, source="OpenStreetMap", line=simplify(line)))
    return out


def _lines(geom: dict) -> list[list[tuple[float, float]]]:
    t = geom.get("type")
    if t == "LineString":
        parts = [geom["coordinates"]]
    elif t == "MultiLineString":
        parts = geom["coordinates"]
    else:
        return []
    # GeoJSON is lon, lat. Some WFS servers return EPSG:4326 as lat, lon; detect that by range.
    out = []
    for part in parts:
        pts = [(float(c[1]), float(c[0])) for c in part if len(c) >= 2]
        if pts and all(-180 <= la <= 180 and -90 <= lo <= 90 for la, lo in pts) and not all(-90 <= la <= 90 for la, lo in pts):
            pts = [(lo, la) for la, lo in pts]
        if len(pts) >= 2:
            out.append(pts)
    return out


SIMPLIFY_DEG = 0.0002  # Douglas-Peucker tolerance, about 22 m north-south and 13 m east-west at 55 N


def simplify(line: list[tuple[float, float]], tol: float = SIMPLIFY_DEG) -> list[tuple[float, float]]:
    """Drop vertices that move the route by less than ~20 m (AIS noise is ~10 m, the buffer 1.5 km)."""
    from shapely.geometry import LineString

    ls = LineString([(lo, la) for la, lo in line]).simplify(tol, preserve_topology=False)
    return [(la, lo) for lo, la in ls.coords]


def load_cables(path: Path = RAW_GEOJSON) -> list[Cable]:
    gj = json.loads(Path(path).read_text())
    cables: list[Cable] = []
    for i, f in enumerate(gj.get("features", [])):
        props = f.get("properties") or {}
        layer = props.get("_layer", "unknown")
        if str(props.get("status") or "").strip().lower() in EXCLUDED_STATUS:
            continue
        name = next((str(props[k]) for k in NAME_KEYS if props.get(k)), "") or f"{layer.split(':')[-1]} #{i}"
        kind = "power" if POWER_PREFIX in layer else ("pipeline" if layer.endswith("pipelines") else "telecom")
        for j, line in enumerate(_lines(f.get("geometry") or {})):
            fid = str(f.get("id") or f"{layer}.{i}")
            cables.append(Cable(cable_id=f"{fid}#{j}", name=name, kind=kind, source=f"EMODnet {layer}", line=simplify(line)))
    if path == RAW_GEOJSON:
        cables += load_osm(cables)
    return cables


def summarize(path: Path = RAW_GEOJSON) -> dict:
    cables = load_cables(path)
    by_layer: dict[str, int] = {}
    for c in cables:
        by_layer[c.source] = by_layer.get(c.source, 0) + 1
    return {"polylines": len(cables), "by_layer": by_layer, "names": sorted({c.name for c in cables})}


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch()
    elif sys.argv[1] == "fetch-osm":
        fetch_osm()
    elif sys.argv[1] == "fetch-osm-pinned":
        fetch_osm_pinned()
    elif sys.argv[1] == "summarize":
        print(json.dumps(summarize(), indent=2))
