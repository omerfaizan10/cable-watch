/* eslint-disable @typescript-eslint/no-explicit-any */
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import OutageLookup from "@/components/OutageLookup";
import { load, VERDICT } from "@/lib/data";
import { utc } from "@/lib/format";

function incidents(): any[] {
  return load("scorecard.json")?.backtest?.incidents ?? [];
}

// Every incident page is prerendered from generateStaticParams, so a navigation to one
// can wait for it rather than stream a placeholder.
export const instant = false;

export function generateStaticParams() {
  return incidents().map((r) => ({ id: r.incident_id }));
}

export async function generateMetadata(props: PageProps<"/incidents/[id]">): Promise<Metadata> {
  const { id } = await props.params;
  const r = incidents().find((x) => x.incident_id === id);
  if (!r) return {};
  const asset = r.asset.split(" (")[0];
  return {
    title: `${asset}, ${r.damage_utc.slice(0, 10)}`,
    description: `${asset} damage reported ${r.damage_utc.slice(0, 10)}${r.vessel ? `, ship named: ${r.vessel}` : ""}. What was reported, what the Danish AIS archive shows, and what the detector did.`,
    alternates: { canonical: `/incidents/${id}/` },
  };
}

const RULE: Record<string, string> = {
  sog_drop: "Sharp slowdown",
  loiter: "Slow dwell",
  drag_signature: "Sideways drift",
  repeat_crossing: "Repeated crossing",
};

function host(u: string) {
  try {
    return new URL(u).hostname.replace(/^www\./, "");
  } catch {
    return u;
  }
}

function Detector({ m, label }: { m: any; label: string }) {
  if (!m) return null;
  return (
    <div>
      <h3>{label}</h3>
      {m.alerts_for_vessel ? (
        <>
          <p>
            {m.alerts_for_vessel} alert{m.alerts_for_vessel === 1 ? "" : "s"} for the
            ship, the first at {m.first_alert_utc?.replace("T", " ").replace("Z", " UTC")} (
            {RULE[m.first_alert_rule] ?? m.first_alert_rule}).{" "}
            {m.flagged_before_damage
              ? `That is ${m.lead_time_h} hours before the reported damage.`
              : "That is after the reported damage, so it does not count as a catch."}
          </p>
          <div className="scroll-x">
            <table className="t">
              <thead>
                <tr>
                  <th>Time (UTC)</th>
                  <th>Rule</th>
                  <th>Near</th>
                  <th className="n">Speed (kn)</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {m.alerts.slice(0, 12).map((a: any, i: number) => (
                  <tr key={i}>
                    <td className="mono" style={{ whiteSpace: "nowrap" }}>
                      {utc(a.ts).slice(0, 16)}
                    </td>
                    <td>{RULE[a.rule] ?? a.rule}</td>
                    <td>{a.cable_name === "(any position)" ? "anywhere (whole-sea run)" : a.cable_name}</td>
                    <td className="n">{a.sog ?? ""}</td>
                    <td className="small">{a.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p>No alerts for this ship.</p>
      )}
    </div>
  );
}

export default async function IncidentPage(props: PageProps<"/incidents/[id]">) {
  const { id } = await props.params;
  const score = load("scorecard.json");
  const all = incidents();
  const i = all.findIndex((x) => x.incident_id === id);
  if (i < 0) notFound();
  const r = all[i];
  const asset = r.asset.split(" (")[0];
  // The bracket in an asset name holds either other cables hit in the same incident
  // ("also EE-S1 ...") or the operator ("Energinet").
  const paren = r.asset.includes("(") ? r.asset.slice(r.asset.indexOf("(") + 1, -1) : "";
  const also = /^also /i.test(paren) ? paren.replace(/^also /i, "") : "";
  const operator = paren && !also ? paren : "";
  const prev = all[i - 1];
  const next = all[i + 1];
  const testedByData = r.gated || r.agnostic;
  return (
    <main className="wrap report">
      <header className="title-block page-head">
        <p className="kicker">
          <Link href="/incidents/">Incidents tested</Link> · {r.damage_utc.slice(0, 10)}
        </p>
        <h1>{asset}</h1>
        <p className="standfirst">
          {r.asset_type ? `${r.asset_type[0].toUpperCase()}${r.asset_type.slice(1)}` : "Damage"}
          {r.between ? ` between ${r.between}` : ""}
          {operator ? `, operated by ${operator}` : ""}
          {also ? `. Also damaged in the same incident: ${also}` : ""}.
        </p>
        <dl className="meta-row">
          <div>
            <dt>Reported damage</dt>
            <dd>
              {r.time_precision === "day"
                ? r.damage_utc.slice(0, 10)
                : `${r.damage_utc.slice(0, 10)} ${r.damage_utc.slice(11, 16)} UTC`}{" "}
              <span className="tiny">({r.time_precision === "minute" ? "to the minute" : r.time_precision})</span>
            </dd>
          </div>
          <div>
            <dt>Ship named</dt>
            <dd>{r.vessel || "none"}</dd>
          </div>
          <div>
            <dt>Verdict</dt>
            <dd className={r.status === "testable" ? "verdict ok" : "verdict"}>{VERDICT[r.status] ?? r.status}</dd>
          </div>
        </dl>
      </header>

      <section className="section">
        <h2>What was reported</h2>
        {r.location_notes && <p><b>Where.</b> {r.location_notes}</p>}
        {r.status_notes && <p><b>Investigation.</b> {r.status_notes}</p>}
        {r.identifier_notes && <p><b>Identifying the ship.</b> {r.identifier_notes}</p>}
        {r.sources?.length > 0 && (
          <>
            <h3>Sources</h3>
            <ol className="sources-list">
              {r.sources.map((u: string) => (
                <li key={u}>
                  <a href={u} rel="noopener noreferrer" target="_blank">
                    {host(u)}
                  </a>
                </li>
              ))}
            </ol>
          </>
        )}
      </section>

      <section className="section">
        <h2>What the data shows</h2>
        <p>{r.reason[0].toUpperCase() + r.reason.slice(1)}.</p>
        {r.ais?.fixes > 0 && (
          <p>
            The Danish archive holds {r.ais.fixes.toLocaleString("en-US")} position reports for the
            ship (MMSI {r.ais.mmsis.join(", ")}) in the extracted window, from{" "}
            {r.ais.first_fix_utc?.replace("T", " ").replace("Z", " UTC")} to{" "}
            {r.ais.last_fix_utc?.replace("T", " ").replace("Z", " UTC")}.
          </p>
        )}
        <p>
          Route on the map:{" "}
          {r.asset_routes_in_emodnet?.length ? r.asset_routes_in_emodnet.join(", ") : "not in EMODnet or the OpenStreetMap routes used"}.
        </p>
      </section>

      {testedByData && (
        <section className="section">
          <h2>What the detector did</h2>
          <div className="grid2">
            <Detector m={r.gated} label="Watching mapped cables" />
            <Detector m={r.agnostic} label="Watching the whole sea" />
          </div>
        </section>
      )}

      {r.outage_lookup && <OutageLookup score={score} only={r.incident_id} />}

      <nav className="page-nav" aria-label="Previous and next incident">
        {prev ? (
          <Link href={`/incidents/${prev.incident_id}/`} className="prev">
            <span>Previous incident</span>
            {prev.asset.split(" (")[0]}
          </Link>
        ) : (
          <Link href="/incidents/" className="prev">
            <span>Back to</span>
            All incidents
          </Link>
        )}
        {next ? (
          <Link href={`/incidents/${next.incident_id}/`} className="next">
            <span>Next incident</span>
            {next.asset.split(" (")[0]}
          </Link>
        ) : (
          <Link href="/incidents/" className="next">
            <span>Back to</span>
            All incidents
          </Link>
        )}
      </nav>
    </main>
  );
}
