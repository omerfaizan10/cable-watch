// Chart-style formatting: degrees and decimal minutes, UTC everywhere.

export function dm(value: number, isLat: boolean, digits = 2): string {
  const hemi = isLat ? (value >= 0 ? "N" : "S") : value >= 0 ? "E" : "W";
  const v = Math.abs(value);
  let d = Math.floor(v);
  let m = (v - d) * 60;
  if (Number(m.toFixed(digits)) >= 60) {
    d += 1;
    m = 0;
  }
  const deg = String(d).padStart(isLat ? 2 : 3, "0");
  const min = m.toFixed(digits).padStart(digits + 3, "0");
  return `${deg}°${min}'${hemi}`;
}

export function utc(ms: number, withDate = true): string {
  const iso = new Date(ms).toISOString();
  return withDate
    ? `${iso.slice(0, 10)} ${iso.slice(11, 19)}Z`
    : `${iso.slice(11, 19)}Z`;
}

export function hm(ms: number): string {
  return new Date(ms).toISOString().slice(11, 16) + "Z";
}

export const int = (n: number | null | undefined) =>
  n == null ? "not measured" : n.toLocaleString("en-US");

export function pct(a: number, b: number, digits = 1): string {
  if (!b) return "0%";
  return `${((100 * a) / b).toFixed(digits)}%`;
}
