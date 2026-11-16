import { readFileSync, existsSync } from "node:fs";
import path from "node:path";

/** Read a precomputed JSON file from public/data at build time (null if it is missing). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function load(name: string): any | null {
  const p = path.join(process.cwd(), "public", "data", name);
  return existsSync(p) ? JSON.parse(readFileSync(p, "utf8")) : null;
}

/** Days with both a cable-gated and a whole-sea run, oldest first. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function runDays(score: any): string[] {
  const runs = score?.runs ?? {};
  return Object.keys(runs)
    .filter((k) => k.startsWith("gated_") && runs[`agnostic_${k.slice(6)}`])
    .map((k) => k.slice(6))
    .sort();
}

export const VERDICT: Record<string, string> = {
  testable: "Tracked before damage",
  in_coverage_only_after_damage: "Tracked only after damage",
  vessel_not_in_coverage: "Ship never in Danish range",
  outside_coverage_not_downloaded: "Outside Danish range",
  not_in_archive: "After the archive ends",
  damage_time_unknown: "Damage time not public",
};
