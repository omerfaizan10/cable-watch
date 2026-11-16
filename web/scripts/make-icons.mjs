// Renders the favicon set and the social share image from SVG with sharp.
// Run from web/: node scripts/make-icons.mjs (reads public/data/scorecard.json).
import fs from "node:fs";
import sharp from "sharp";

const icon = fs.readFileSync("src/app/icon.svg");
const png = (size, svg = icon) => sharp(svg, { density: 384 }).resize(size, size).png().toBuffer();

// iOS rounds the corners itself, so the touch icon is a full square.
const square = Buffer.from(icon.toString().replace('rx="12"', 'rx="0"'));
await fs.promises.writeFile("src/app/apple-icon.png", await png(180, square));

// favicon.ico: an ICO container holding PNG-encoded 16, 32 and 48 px images.
const sizes = [16, 32, 48];
const imgs = await Promise.all(sizes.map((s) => png(s)));
const header = Buffer.alloc(6);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(sizes.length, 4);
let offset = 6 + 16 * sizes.length;
const dir = sizes.map((s, i) => {
  const e = Buffer.alloc(16);
  e.writeUInt8(s, 0);
  e.writeUInt8(s, 1);
  e.writeUInt16LE(1, 4);
  e.writeUInt16LE(32, 6);
  e.writeUInt32LE(imgs[i].length, 8);
  e.writeUInt32LE(offset, 12);
  offset += imgs[i].length;
  return e;
});
await fs.promises.writeFile("src/app/favicon.ico", Buffer.concat([header, ...dir, ...imgs]));

// 1200x630 share card. Numbers come from the evaluation output.
const s = JSON.parse(fs.readFileSync("public/data/scorecard.json", "utf8"));
const bt = s.backtest;
const bh = bt.incidents.find((r) => r.incident_id === "bornholm-2022");
const ol = bh?.outage_lookup;
const fa = bt.false_alerts_per_day;
const rows = (s.correctness?.rows ?? 0).toLocaleString("en-US");
const serif = "Source Serif 4, Georgia, Times New Roman, serif";
const sans = "Public Sans, Helvetica Neue, Arial, sans-serif";
const days = Object.keys(s.runs).filter((k) => k.startsWith("gated_")).length;
const stat = (x, big, small, color = "#17191c") => `
    <line x1="${x}" x2="${x + 320}" y1="430" y2="430" stroke="#17191c" stroke-width="3"/>
    <text x="${x}" y="492" font-family="${serif}" font-size="52" font-weight="600" fill="${color}">${big}</text>
    <text x="${x}" y="530" font-family="${sans}" font-size="19" fill="#3f454b">${small}</text>`;
const og = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630">
  <rect width="1200" height="630" fill="#fbfaf7"/>
  <text x="80" y="92" font-family="${sans}" font-size="20" font-weight="700" fill="#5c636a" letter-spacing="2">CABLE WATCH  ·  DATA ENGINEERING CASE STUDY</text>
  <line x1="80" x2="1120" y1="116" y2="116" stroke="#17191c" stroke-width="3"/>
  <text x="80" y="200" font-family="${serif}" font-size="62" font-weight="600" fill="#17191c">Ships over the cables</text>
  <text x="80" y="272" font-family="${serif}" font-size="62" font-weight="600" fill="#17191c">under the Baltic</text>
  <text x="80" y="332" font-family="${sans}" font-size="25" fill="#3f454b">${days} days of Danish ship positions, graded against real cable breaks.</text>
  <path d="M860 196 C 920 170, 1000 222, 1110 192" fill="none" stroke="#155e72" stroke-width="6" stroke-linecap="round"/>
  <path d="M985 120 L 1012 182 L 985 165 L 958 182 Z" fill="#b42318" stroke="#fbfaf7" stroke-width="3" stroke-linejoin="round"/>
  ${ol?.named_vessel_rank ? stat(80, `1st of ${ol.candidates}`, "Samus Swan among cable crossings", "#b42318") : ""}
  ${fa?.gated ? stat(440, `${Math.round(fa.gated.median ?? fa.gated.mean_alerts_per_day)} a day`, "alerts on a typical ordinary day") : ""}
  ${stat(800, "3 of 3", "shuffled replays, identical alerts")}
</svg>`;
const ogPng = await sharp(Buffer.from(og)).png().toBuffer();
await fs.promises.writeFile("src/app/opengraph-image.png", ogPng);
await fs.promises.writeFile("src/app/twitter-image.png", ogPng);
const alt = "Cable Watch: ships over Baltic subsea cables, graded against real cable breaks";
await fs.promises.writeFile("src/app/opengraph-image.alt.txt", alt);
await fs.promises.writeFile("src/app/twitter-image.alt.txt", alt);
console.log("icons and share image written");
