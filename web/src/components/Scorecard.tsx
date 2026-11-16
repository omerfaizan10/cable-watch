/* eslint-disable @typescript-eslint/no-explicit-any */
import { utc } from "@/lib/format";

const STATUS: Record<string, string> = {
  testable: "Tracked before damage",
  in_coverage_only_after_damage: "Tracked only after damage",
  vessel_not_in_coverage: "No DMA fixes for vessel",
  outside_coverage_not_downloaded: "Outside DMA range",
  not_in_archive: "After archive end",
  damage_time_unknown: "Damage time not public",
};

function flagCell(m: any, testable: boolean) {
  if (!m) return <span className="tiny">not run</span>;
  if (!m.alerts_for_vessel) return <span className="tag">not flagged</span>;
  if (m.flagged_before_damage)
    return (
      <span className="tag hit">
        flagged {m.lead_time_h?.toFixed(1)} h before
      </span>
    );
  return (
    <span className="tag">
      flagged after{testable ? "" : " (no earlier fixes)"}:{" "}
      {m.first_alert_utc?.slice(11, 16)}Z
    </span>
  );
}

export default function Scorecard({
  score,
  coverage,
}: {
  score: any;
  coverage: any;
}) {
  const bt = score?.backtest;
  if (!bt)
    return (
      <section className="section">
        <h2>Backtest scorecard</h2>
        <p className="lede">
          The backtest has not been run yet. Run make eval to produce
          data/warehouse/backtest.json.
        </p>
      </section>
    );
  const inc: any[] = bt.incidents;
  const testable = inc.filter((r) => r.status === "testable");
  const east = coverage?.east_limit_lon_1000_fixes_per_day;
  return (
    <section className="section" id="scorecard">
      <h2>Backtest scorecard</h2>
      <p className="lede">
        {inc.length} publicly reported Baltic cable and pipeline incidents, each
        checked against the Danish Maritime Authority archive. {testable.length}{" "}
        of them can be tested honestly: the named vessel is in the DMA data
        before the reported damage time. The rest fail on geography (the DMA
        receivers stop near {east ? `${east.toFixed(1)}°E` : "18.6°E"}, short of
        Gotland and the Gulf of Finland), on archive dates (the daily files end
        26 Feb 2025), or on a damage time that was never published.
      </p>
      <div className="scroll-x">
        <table className="t">
          <thead>
            <tr>
              <th>Reported damage</th>
              <th>Asset</th>
              <th>Vessel</th>
              <th>Route in EMODnet</th>
              <th>DMA verdict</th>
              <th>Cable-gated rules</th>
              <th>Cable-agnostic rules</th>
            </tr>
          </thead>
          <tbody>
            {inc.map((r) => (
              <tr key={r.incident_id}>
                <td className="mono" style={{ whiteSpace: "nowrap" }}>
                  {r.time_precision === "day"
                    ? r.damage_utc.slice(0, 10)
                    : utc(Date.parse(r.damage_utc)).slice(0, 16) + "Z"}
                  <div className="tiny">
                    {r.time_precision === "minute"
                      ? "to the minute"
                      : r.time_precision}
                  </div>
                </td>
                <td>{r.asset}</td>
                <td>
                  {r.vessel || <span className="tiny">none named</span>}
                  {r.ais?.mmsis?.length ? (
                    <div className="tiny mono">
                      MMSI {r.ais.mmsis.join(", ")} in DMA
                    </div>
                  ) : null}
                </td>
                <td>
                  {r.asset_routes_in_emodnet?.length ? (
                    r.asset_routes_in_emodnet.join(", ")
                  ) : (
                    <span className="tiny">missing</span>
                  )}
                </td>
                <td>
                  <span
                    className={`tag ${r.status === "testable" ? "ok" : ""}`}
                  >
                    {STATUS[r.status] ?? r.status}
                  </span>
                  <div className="tiny">{r.reason}</div>
                </td>
                <td>
                  {r.gated || r.agnostic ? (
                    flagCell(r.gated, r.status === "testable")
                  ) : (
                    <span className="tiny">untestable</span>
                  )}
                </td>
                <td>
                  {r.gated || r.agnostic ? (
                    flagCell(r.agnostic, r.status === "testable")
                  ) : (
                    <span className="tiny">untestable</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tiny">
        Sources for every incident row (dates, vessel names, IMO numbers) are
        listed in data/reference/incidents.csv. Lead time is reported damage
        time minus the first alert for that vessel; it is only computed when the
        vessel was tracked before the damage.
      </p>
    </section>
  );
}
