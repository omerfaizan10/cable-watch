export type Pt = [number, number, number, number | null, number | null]; // t_s, lon, lat, sog, cog

export interface Vessel {
  mmsi: number;
  name: string;
  imo: string;
  type: string;
  length: number | null;
  focus: boolean;
  pts: Pt[];
}

export interface ReplayAlert {
  t: number;
  mmsi: number;
  name: string;
  rule: string;
  label: string;
  cable: string;
  lon: number;
  lat: number;
  sog: number | null;
  dist_m: number;
  detail: string;
  mode: "gated" | "agnostic";
}

export interface Replay {
  id: string;
  title: string;
  start_utc: string;
  end_utc: string;
  bbox: [number, number, number, number];
  focus_mmsi: number | null;
  incident_id: string | null;
  vessels: Vessel[];
  alerts: ReplayAlert[];
}

export interface ReplayMeta {
  id: string;
  title: string;
  vessels: number;
  alerts: number;
}
