import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";
import { load } from "@/lib/data";

export default function sitemap(): MetadataRoute.Sitemap {
  const incidents: { incident_id: string }[] = load("scorecard.json")?.backtest?.incidents ?? [];
  const pages = ["/", "/replay/", "/incidents/", "/false-alerts/", "/pipeline/", "/method/", "/how-it-works/",
    ...incidents.map((r) => `/incidents/${r.incident_id}/`)];
  return pages.map((p) => ({
    url: `${SITE_URL}${p}`,
    changeFrequency: "monthly",
    priority: p === "/" ? 1 : 0.8,
  }));
}
