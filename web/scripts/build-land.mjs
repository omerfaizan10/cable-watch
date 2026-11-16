// Clips Natural Earth 1:10m land (public domain, via the world-atlas package) to the chart
// area and writes public/data/land.json. Run: node scripts/build-land.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { feature } from "topojson-client";

const BBOX = [7.5, 52.8, 24.5, 61.0];
const topo = JSON.parse(readFileSync(new URL("../node_modules/world-atlas/land-10m.json", import.meta.url)));
const land = feature(topo, topo.objects.land);
const inBox = ([x, y]) => x >= BBOX[0] && x <= BBOX[2] && y >= BBOX[1] && y <= BBOX[3];
// Sutherland-Hodgman clip of a ring against the box, so the Eurasia polygon does not ship whole.
function clipRing(ring) {
  const edges = [
    (p) => p[0] >= BBOX[0], (p) => p[0] <= BBOX[2], (p) => p[1] >= BBOX[1], (p) => p[1] <= BBOX[3],
  ];
  const cut = [
    (a, b) => [BBOX[0], a[1] + ((b[1] - a[1]) * (BBOX[0] - a[0])) / (b[0] - a[0])],
    (a, b) => [BBOX[2], a[1] + ((b[1] - a[1]) * (BBOX[2] - a[0])) / (b[0] - a[0])],
    (a, b) => [a[0] + ((b[0] - a[0]) * (BBOX[1] - a[1])) / (b[1] - a[1]), BBOX[1]],
    (a, b) => [a[0] + ((b[0] - a[0]) * (BBOX[3] - a[1])) / (b[1] - a[1]), BBOX[3]],
  ];
  let pts = ring;
  for (let e = 0; e < 4; e++) {
    const out = [];
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i], b = pts[(i + 1) % pts.length];
      const ia = edges[e](a), ib = edges[e](b);
      if (ia) out.push(a);
      if (ia !== ib) out.push(cut[e](a, b));
    }
    pts = out;
    if (!pts.length) break;
  }
  if (pts.length > 2) pts.push(pts[0]);
  return pts;
}
const polys = [];
for (const f of land.features) {
  const g = f.geometry;
  const list = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
  for (const poly of list) {
    if (poly[0].some(inBox)) {
      const rings = poly.map((ring) => clipRing(ring).map(([x, y]) => [Math.round(x * 1e4) / 1e4, Math.round(y * 1e4) / 1e4])).filter((r) => r.length > 3);
      if (rings.length) polys.push(rings);
    }
  }
}
const out = { type: "FeatureCollection", features: [{ type: "Feature", properties: { source: "Natural Earth 1:10m land" }, geometry: { type: "MultiPolygon", coordinates: polys } }] };
writeFileSync(new URL("../public/data/land.json", import.meta.url), JSON.stringify(out));
console.log("polygons", polys.length);
