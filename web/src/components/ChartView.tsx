"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { dm, hm, utc } from "@/lib/format";
import type { Replay, ReplayAlert, ReplayMeta, Vessel } from "@/lib/types";

// MapLibre paint properties cannot read CSS variables, so the map mirrors the tokens in globals.css.
const C = {
  sea: "#e8eef0",
  land: "#ddd7c9",
  landEdge: "#a39a84",
  grat: "#d3dde1",
  gratLabel: "#5c636a",
  telecom: "#a8740e",
  power: "#155e72",
  pipeline: "#8a8477",
  vessel: "#6a7179",
  focus: "#17191c",
  alert: "#b42318",
};

const SPEEDS = [60, 300, 900, 1800];
const RULE_SHORT: Record<string, string> = {
  sog_drop: "speed drop",
  loiter: "slow dwell",
  drag_signature: "drag signature",
  repeat_crossing: "repeat crossing",
};

type FC = GeoJSON.FeatureCollection;

function chevron(color: string, size = 44): ImageData {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d")!;
  const s = size / 44;
  g.translate(size / 2, size / 2);
  g.beginPath();
  g.moveTo(0, -17 * s);
  g.lineTo(9 * s, 14 * s);
  g.lineTo(0, 8 * s);
  g.lineTo(-9 * s, 14 * s);
  g.closePath();
  g.fillStyle = color;
  g.fill();
  g.lineWidth = 2 * s;
  g.strokeStyle = "#ffffff";
  g.stroke();
  return g.getImageData(0, 0, size, size);
}

function graticule(): FC {
  const f: GeoJSON.Feature[] = [];
  for (let lat = 50; lat <= 66; lat += 0.5) {
    f.push({
      type: "Feature",
      properties: { major: lat % 1 === 0 },
      geometry: {
        type: "LineString",
        coordinates: [
          [0, lat],
          [34, lat],
        ],
      },
    });
  }
  for (let lon = 0; lon <= 34; lon += 0.5) {
    const c: [number, number][] = [];
    for (let lat = 50; lat <= 66; lat += 0.5) c.push([lon, lat]);
    f.push({
      type: "Feature",
      properties: { major: lon % 1 === 0 },
      geometry: { type: "LineString", coordinates: c },
    });
  }
  return { type: "FeatureCollection", features: f };
}

function coverageFC(
  cells: [number, number, number][],
  step: number,
  days: number,
): FC {
  return {
    type: "FeatureCollection",
    features: cells
      .filter((c) => c[2] / days >= 200)
      .map(([lon, lat, n]) => ({
        type: "Feature",
        properties: { d: Math.log10(n / days) },
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [lon, lat],
              [lon + step, lat],
              [lon + step, lat + step],
              [lon, lat + step],
              [lon, lat],
            ],
          ],
        },
      })),
  };
}

function posAt(
  v: Vessel,
  t: number,
): {
  lon: number;
  lat: number;
  sog: number | null;
  cog: number | null;
  i: number;
} | null {
  const p = v.pts;
  if (!p.length || t < p[0][0] - 60 || t > p[p.length - 1][0] + 600)
    return null;
  let lo = 0;
  let hi = p.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (p[mid][0] <= t) lo = mid;
    else hi = mid - 1;
  }
  const a = p[lo];
  const b = p[Math.min(lo + 1, p.length - 1)];
  // Interpolate only across short gaps; across a long gap the vessel stays at its last fix.
  const gap = b[0] - a[0];
  const k =
    gap > 0 && gap <= 900 && t > a[0] ? Math.min(1, (t - a[0]) / gap) : 0;
  return {
    lon: a[1] + (b[1] - a[1]) * k,
    lat: a[2] + (b[2] - a[2]) * k,
    sog: a[3],
    cog: a[4],
    i: lo,
  };
}

function niceNm(maxNm: number): number {
  const steps = [0.5, 1, 2, 5, 10, 20, 50, 100];
  let best = steps[0];
  for (const s of steps) if (s <= maxNm) best = s;
  return best;
}

export default function ChartView({ replays }: { replays: ReplayMeta[] }) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const [rid, setRid] = useState(replays[0]?.id ?? "");
  const [replay, setReplay] = useState<Replay | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(300);
  const [cursor, setCursor] = useState<{ lon: number; lat: number } | null>(
    null,
  );
  const [scale, setScale] = useState<{ nm: number; px: number }>({
    nm: 10,
    px: 80,
  });
  const [hover, setHover] = useState<{
    x: number;
    y: number;
    html: string;
  } | null>(null);
  const nowRef = useRef(0);
  const lastPush = useRef(0);

  const t0 = replay ? Date.parse(replay.start_utc) : 0;
  const dur = replay ? (Date.parse(replay.end_utc) - t0) / 1000 : 0;

  // ---- map setup -----------------------------------------------------------------
  useEffect(() => {
    if (!el.current) return;
    const map = new maplibregl.Map({
      container: el.current,
      style: {
        version: 8,
        sources: {},
        layers: [
          {
            id: "sea",
            type: "background",
            paint: { "background-color": C.sea },
          },
        ],
      },
      center: [14.5, 55.2],
      zoom: 7,
      minZoom: 4.5,
      maxZoom: 13,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right",
    );
    map.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        customAttribution:
          "AIS: Danish Maritime Authority | Routes: EMODnet Human Activities, CC BY 4.0 (Cogea); OpenStreetMap contributors, ODbL | Land: Natural Earth",
      }),
    );
    mapRef.current = map;
    const updateScale = () => {
      const c = map.getCenter();
      const mPerPx =
        (40075016.686 * Math.cos((c.lat * Math.PI) / 180)) /
        (512 * 2 ** map.getZoom());
      const maxNm = (120 * mPerPx) / 1852;
      const nm = niceNm(maxNm);
      setScale({ nm, px: (nm * 1852) / mPerPx });
    };
    map.on("move", updateScale);
    map.on("mousemove", (e) =>
      setCursor({ lon: e.lngLat.lng, lat: e.lngLat.lat }),
    );
    map.on("mouseout", () => setCursor(null));
    map.on("load", async () => {
      updateScale();
      map.addImage("ship", chevron(C.vessel), { pixelRatio: 2 });
      map.addImage("ship-focus", chevron(C.focus), { pixelRatio: 2 });
      map.addImage("ship-alert", chevron(C.alert), { pixelRatio: 2 });
      try {
        const [land, cables, cov] = await Promise.all(
          ["land", "cables", "coverage"].map((n) =>
            fetch(`/data/${n}.json`).then((r) => (r.ok ? r.json() : null)),
          ),
        );
        if (cov) {
          map.addSource("cov", {
            type: "geojson",
            data: coverageFC(cov.cells, cov.cell_deg, cov.days.length),
          });
          map.addLayer({
            id: "cov",
            type: "fill",
            source: "cov",
            paint: {
              "fill-color": "#c9dae1",
              "fill-opacity": [
                "interpolate",
                ["linear"],
                ["get", "d"],
                2.3,
                0.25,
                4.5,
                0.75,
              ],
            },
          });
        }
        map.addSource("grat", { type: "geojson", data: graticule() });
        map.addLayer({
          id: "grat",
          type: "line",
          source: "grat",
          paint: {
            "line-color": C.grat,
            "line-width": ["case", ["get", "major"], 1, 0.5],
          },
        });
        if (land) {
          map.addSource("land", { type: "geojson", data: land });
          map.addLayer({
            id: "land",
            type: "fill",
            source: "land",
            paint: { "fill-color": C.land },
          });
          map.addLayer({
            id: "coast",
            type: "line",
            source: "land",
            paint: { "line-color": C.landEdge, "line-width": 0.8 },
          });
        }
        if (cables) {
          map.addSource("cables", { type: "geojson", data: cables });
          map.addLayer({
            id: "pipes",
            type: "line",
            source: "cables",
            filter: ["==", ["get", "kind"], "pipeline"],
            paint: {
              "line-color": C.pipeline,
              "line-width": 1,
              "line-dasharray": [4, 3],
            },
          });
          map.addLayer({
            id: "cables",
            type: "line",
            source: "cables",
            filter: ["!=", ["get", "kind"], "pipeline"],
            paint: {
              "line-color": [
                "match",
                ["get", "kind"],
                "power",
                C.power,
                C.telecom,
              ],
              "line-width": ["interpolate", ["linear"], ["zoom"], 6, 1, 11, 2],
            },
          });
        }
      } catch {
        setErr(
          "The chart layers did not load. The replay still runs without them.",
        );
      }
      const empty: FC = { type: "FeatureCollection", features: [] };
      map.addSource("trails", { type: "geojson", data: empty });
      map.addLayer({
        id: "trails",
        type: "line",
        source: "trails",
        paint: {
          "line-color": [
            "case",
            ["get", "alert"],
            C.alert,
            ["get", "focus"],
            C.focus,
            C.vessel,
          ],
          "line-opacity": [
            "case",
            ["get", "focus"],
            0.85,
            ["get", "alert"],
            0.7,
            0.18,
          ],
          "line-width": ["case", ["get", "focus"], 1.6, 0.8],
        },
      });
      map.addSource("alerts", { type: "geojson", data: empty });
      map.addLayer({
        id: "alerts",
        type: "circle",
        source: "alerts",
        paint: {
          "circle-radius": 7,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": C.alert,
          "circle-stroke-width": 1.2,
          "circle-stroke-opacity": ["case", ["get", "gated"], 0.95, 0.5],
        },
      });
      map.addSource("ships", { type: "geojson", data: empty });
      map.addLayer({
        id: "ships",
        type: "symbol",
        source: "ships",
        layout: {
          "icon-image": [
            "case",
            ["get", "alert"],
            "ship-alert",
            ["get", "focus"],
            "ship-focus",
            "ship",
          ],
          "icon-rotate": ["coalesce", ["get", "cog"], 0],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          "icon-size": [
            "interpolate",
            ["linear"],
            ["zoom"],
            6,
            0.55,
            10,
            ["case", ["get", "focus"], 1.1, 0.85],
          ],
          "symbol-sort-key": [
            "case",
            ["get", "alert"],
            2,
            ["get", "focus"],
            1,
            0,
          ],
        },
      });
      map.on("mousemove", "ships", (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const p = f.properties as Record<
          string,
          string | number | boolean | null
        >;
        const sog =
          p.sog == null || p.sog === "null"
            ? "no SOG"
            : `${Number(p.sog).toFixed(1)} kn`;
        const cog =
          p.cog == null || p.cog === "null"
            ? "no COG"
            : `${String(Math.round(Number(p.cog))).padStart(3, "0")}°`;
        const [lon, lat] = (f.geometry as GeoJSON.Point).coordinates;
        setHover({
          x: e.point.x,
          y: e.point.y,
          html: `${p.name || "(no name)"}  MMSI ${p.mmsi}\n${p.type || "type unknown"}  ${sog}  ${cog}\n${dm(lat, true)} ${dm(lon, false)}${p.alert ? "\nflagged: behavior consistent with anchor drag" : ""}`,
        });
        map.getCanvas().style.cursor = "crosshair";
      });
      map.on("mouseleave", "ships", () => {
        setHover(null);
        map.getCanvas().style.cursor = "";
      });
      setReady(true);
    });
    return () => map.remove();
  }, []);

  // ---- load replay -----------------------------------------------------------------
  useEffect(() => {
    if (!rid) return;
    let cancelled = false;
    fetch(`/data/replay_${rid}.json`)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((d: Replay) => {
        if (cancelled) return;
        setReplay(d);
        nowRef.current = 0;
        setNow(0);
      })
      .catch(
        () =>
          !cancelled &&
          setErr(
            "This replay file is missing. Run make eval to rebuild web/public/data.",
          ),
      );
    return () => {
      cancelled = true;
    };
  }, [rid]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !replay) return;
    const [x0, y0, x1, y1] = replay.bbox;
    map.fitBounds(
      [
        [x0, y0],
        [x1, y1],
      ],
      { padding: 20, duration: 0 },
    );
  }, [ready, replay]);

  // ---- which vessels are flagged by time t ------------------------------------------
  const firstAlert = useMemo(() => {
    const m = new Map<number, number>();
    if (!replay) return m;
    for (const a of replay.alerts) {
      const counts = a.mode === "gated" || a.mmsi === replay.focus_mmsi;
      if (counts && !m.has(a.mmsi)) m.set(a.mmsi, a.t);
    }
    return m;
  }, [replay]);

  const draw = useCallback(
    (t: number) => {
      const map = mapRef.current;
      if (!map || !replay || !map.getSource("ships")) return;
      const ships: GeoJSON.Feature[] = [];
      const trails: GeoJSON.Feature[] = [];
      for (const v of replay.vessels) {
        const p = posAt(v, t);
        if (!p) continue;
        const fa = firstAlert.get(v.mmsi);
        const alert = fa != null && fa <= t;
        ships.push({
          type: "Feature",
          properties: {
            mmsi: v.mmsi,
            name: v.name,
            type: v.type,
            sog: p.sog,
            cog: p.cog,
            focus: v.focus,
            alert,
          },
          geometry: { type: "Point", coordinates: [p.lon, p.lat] },
        });
        const tail = v.focus ? 0 : Math.max(0, p.i - 25);
        const coords = v.pts.slice(tail, p.i + 1).map((q) => [q[1], q[2]]);
        coords.push([p.lon, p.lat]);
        if (coords.length > 1)
          trails.push({
            type: "Feature",
            properties: { focus: v.focus, alert },
            geometry: { type: "LineString", coordinates: coords },
          });
      }
      const al = replay.alerts
        .filter(
          (a) =>
            a.t <= t && (a.mode === "gated" || a.mmsi === replay.focus_mmsi),
        )
        .map((a) => ({
          type: "Feature" as const,
          properties: { gated: a.mode === "gated" },
          geometry: { type: "Point" as const, coordinates: [a.lon, a.lat] },
        }));
      (map.getSource("ships") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: ships,
      });
      (map.getSource("trails") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: trails,
      });
      (map.getSource("alerts") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: al,
      });
    },
    [replay, firstAlert],
  );

  useEffect(() => {
    if (ready) draw(now);
  }, [ready, now, draw]);

  // ---- clock -----------------------------------------------------------------------
  useEffect(() => {
    if (!playing || !replay) return;
    let raf = 0;
    let prev = performance.now();
    const tick = (ts: number) => {
      const dt = (ts - prev) / 1000;
      prev = ts;
      nowRef.current = Math.min(dur, nowRef.current + dt * speed);
      if (ts - lastPush.current > 66 || nowRef.current >= dur) {
        lastPush.current = ts;
        setNow(nowRef.current);
      }
      if (nowRef.current >= dur) {
        setPlaying(false);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, replay, dur]);

  const feed: ReplayAlert[] = useMemo(() => {
    if (!replay) return [];
    return replay.alerts
      .filter(
        (a) =>
          a.t <= now && (a.mode === "gated" || a.mmsi === replay.focus_mmsi),
      )
      .slice()
      .reverse();
  }, [replay, now]);

  const focus = replay?.vessels.find((v) => v.focus);
  const focusPos = focus ? posAt(focus, now) : null;
  const visible = replay
    ? replay.vessels.filter((v) => posAt(v, now)).length
    : 0;
  const flagged = replay
    ? [...firstAlert.values()].filter((t) => t <= now).length
    : 0;

  const jump = (a: ReplayAlert) => {
    nowRef.current = a.t;
    setNow(a.t);
    setPlaying(false);
    mapRef.current?.flyTo({
      center: [a.lon, a.lat],
      zoom: Math.max(mapRef.current.getZoom(), 9.5),
      duration: 600,
    });
  };

  return (
    <div className="console">
      <div className="chart-wrap">
        <div
          ref={el}
          className="chart"
          role="region"
          aria-label="Chart of the western Baltic with cable routes and vessel tracks"
        />
        <div className="ovl ovl-tl">
          <div className="big">
            {replay ? utc(t0 + now * 1000) : "loading replay"}
          </div>
          <div>
            {visible} vessels in view window, {flagged} flagged
          </div>
        </div>
        <div className="ovl ovl-tr">
          <div>
            {cursor
              ? `${dm(cursor.lat, true)}  ${dm(cursor.lon, false)}`
              : "cursor off chart"}
          </div>
          {focus && focusPos && (
            <div style={{ color: "var(--ink)" }}>
              {focus.name}{" "}
              {focusPos.sog != null ? `${focusPos.sog.toFixed(1)} kn` : ""}{" "}
              {focusPos.cog != null
                ? `${String(Math.round(focusPos.cog)).padStart(3, "0")}°`
                : ""}
            </div>
          )}
        </div>
        <div className="ovl ovl-bl">
          <div className="scalebar">
            <div className="bar" style={{ width: scale.px }} />
            <span>{scale.nm} NM</span>
          </div>
        </div>
        <div className="ovl ovl-br">
          <div className="legend">
            <span className="sw" style={{ borderColor: C.telecom }} />
            <span>Telecom cable (EMODnet)</span>
            <span className="sw" style={{ borderColor: C.power }} />
            <span>Power cable (EMODnet, OSM)</span>
            <span className="sw dash" style={{ borderColor: C.pipeline }} />
            <span>Pipeline (EMODnet)</span>
            <span className="cov" />
            <span>DMA receiving range, measured</span>
            <span className="chev" />
            <span>Vessel, oriented by COG</span>
            <span className="chev alert" />
            <span>Flagged vessel</span>
          </div>
        </div>
        {hover && (
          <div
            className="chart-tip"
            style={{ left: hover.x + 14, top: hover.y + 10, whiteSpace: "pre" }}
          >
            {hover.html}
          </div>
        )}
      </div>

      <aside className="side">
        <section className="panel">
          <header>
            <span>Replay</span>
            <span className="meta">DMA archive, event time</span>
          </header>
          <div className="replays">
            {replays.map((r) => (
              <button
                key={r.id}
                aria-pressed={r.id === rid}
                onClick={() => {
                  if (r.id === rid) return;
                  // Reset here rather than in the loading effect, so switching is one render.
                  setReplay(null);
                  setErr(null);
                  setPlaying(false);
                  setRid(r.id);
                }}
              >
                {r.title}
                <span className="rmeta">
                  {r.vessels} vessels, {r.alerts} alerts
                </span>
              </button>
            ))}
          </div>
          <div className="transport">
            <button
              className="btn"
              onClick={() => setPlaying((p) => !p)}
              disabled={!replay}
              aria-pressed={playing}
            >
              {playing ? "PAUSE" : now >= dur && dur > 0 ? "REPLAY" : "PLAY"}
            </button>
            <div className="speeds" role="group" aria-label="Replay speed">
              {SPEEDS.map((s) => (
                <button
                  key={s}
                  className="btn"
                  aria-pressed={s === speed}
                  onClick={() => setSpeed(s)}
                >
                  {s}x
                </button>
              ))}
            </div>
            <span className="clock">
              {replay ? hm(t0 + now * 1000) : "--:--Z"}
            </span>
            <input
              type="range"
              min={0}
              max={Math.max(1, dur)}
              step={30}
              value={now}
              aria-label="Replay time"
              onChange={(e) => {
                const v = Number(e.target.value);
                nowRef.current = v;
                setNow(v);
                if (now >= dur) setPlaying(false);
              }}
            />
          </div>
          {err && <div className="caveat">{err}</div>}
        </section>
        <section className="panel feed" aria-live="polite">
          <header>
            <span>Alert feed</span>
            <span className="meta">{feed.length} so far</span>
          </header>
          {feed.length === 0 ? (
            <div className="empty">
              {replay
                ? "No alerts yet at this point in the replay. Press play or drag the time slider."
                : "Loading replay data."}
            </div>
          ) : (
            <ol>
              {feed.map((a, i) => (
                <li
                  key={`${a.t}-${a.mmsi}-${a.rule}-${i}`}
                  className={a.mode === "agnostic" ? "agn" : ""}
                  tabIndex={0}
                  onClick={() => jump(a)}
                  onKeyDown={(e) => e.key === "Enter" && jump(a)}
                >
                  <div className="row1">
                    <span className="who">{a.name || `MMSI ${a.mmsi}`}</span>
                    <span className="t">{hm(t0 + a.t * 1000)}</span>
                  </div>
                  <div className="what">
                    {a.label}
                    {a.mode === "agnostic" ? " (cable-agnostic rule)" : ""}
                  </div>
                  <div className="why">
                    {a.mode === "gated"
                      ? `${a.cable}, ${Math.round(a.dist_m)} m. `
                      : ""}
                    {a.detail}
                  </div>
                  <div className="why">
                    {dm(a.lat, true)} {dm(a.lon, false)}{" "}
                    {RULE_SHORT[a.rule] ? "" : a.rule}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>
        <div className="caveat">
          A flag means <b>behavior consistent with anchor drag</b> near a mapped
          route. It is a lead for a person to check, not an accusation and not
          evidence of intent.
        </div>
      </aside>
    </div>
  );
}
