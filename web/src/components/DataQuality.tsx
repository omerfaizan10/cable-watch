/* eslint-disable @typescript-eslint/no-explicit-any */
import { pct } from "@/lib/format";

const n = (v: number) => v.toLocaleString("en-US");

function Funnel({ a }: { a: any }) {
  const rows: [string, number, string][] = [
    [
      "Raw rows in the Baltic box",
      a.raw_in,
      "read from the extracted DMA Parquet",
    ],
    [
      "Schema rejects",
      a.schema_rejects,
      Object.entries(a.reject_breakdown ?? {})
        .map(([k, v]) => `${k.replaceAll("_", " ")} ${n(v as number)}`)
        .join(", "),
    ],
    [
      "Late beyond bound",
      a.late_dropped,
      "arrived after a newer fix of the same vessel was released",
    ],
    [
      "Exact duplicates",
      a.duplicate,
      "same vessel, time and position (several base stations hear one message)",
    ],
    [
      "Teleports",
      a.teleport,
      `implied speed over 60 kn; ${n(a.track_reset)} track restarts`,
    ],
    ["Accepted", a.accepted, "clean, in event-time order"],
    [
      "Evaluated by the rules",
      a.evaluated,
      "Class A, 50 m or longer, not fishing, tug, pilot, SAR, military and similar",
    ],
  ];
  return (
    <table className="t">
      <thead>
        <tr>
          <th>Bucket</th>
          <th className="n">Rows</th>
          <th className="n">Share</th>
          <th>Meaning</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([k, v, why]) => (
          <tr key={k}>
            <td>{k}</td>
            <td className="n">{n(v)}</td>
            <td className="n">{pct(v, a.raw_in)}</td>
            <td className="small">{why}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function DataQuality({ score }: { score: any }) {
  const runs = score?.runs ?? {};
  const c = score?.correctness;
  const keys = Object.keys(runs)
    .filter((k) => k.startsWith("gated_"))
    .sort();
  const total = keys.reduce(
    (acc, k) => {
      const a = runs[k];
      acc.raw += a.raw_in;
      acc.ok += a.balanced ? 1 : 0;
      return acc;
    },
    { raw: 0, ok: 0 },
  );
  const show =
    runs["gated_2025-02-12"] ??
    (keys.length ? runs[keys[keys.length - 1]] : null);
  return (
    <section className="section" id="quality">
      <h2>Data quality and pipeline correctness</h2>
      <div className="grid2">
        <div>
          <p className="lede">
            Every raw row lands in exactly one bucket, and the buckets must add
            back to the input. That reconciliation held for{" "}
            <span className="num">
              {total.ok} of {keys.length}
            </span>{" "}
            cable-gated runs, covering{" "}
            <span className="num">{n(total.raw)}</span> rows. Breakdown for 12
            Feb 2025:
          </p>
          {show ? (
            <Funnel a={show} />
          ) : (
            <p className="small">No run audits found.</p>
          )}
        </div>
        <div>
          <p className="lede">
            Correctness checks on real rows from the Samus Swan window:
          </p>
          {c ? (
            <table className="t">
              <tbody>
                <tr>
                  <td>Row-count audit</td>
                  <td className="small">
                    <span className="num">
                      {n(c.row_count_audit.parquet_rows)}
                    </span>{" "}
                    rows in Parquet,{" "}
                    <span className="num">
                      {n(c.row_count_audit.processor_raw_in)}
                    </span>{" "}
                    counted in by the processor:{" "}
                    {c.row_count_audit.match && c.row_count_audit.balanced
                      ? "match, balanced"
                      : "MISMATCH"}
                  </td>
                </tr>
                {c.determinism.map((d: any) => (
                  <tr key={d.seed}>
                    <td>Replay order, seed {d.seed}</td>
                    <td className="small">
                      <span className="num">{n(d.rows_out_of_order)}</span> rows
                      delivered out of order (up to 90 s),{" "}
                      <span className="num">{d.late_dropped}</span> dropped,{" "}
                      {d.identical_to_in_order
                        ? `same ${d.alerts} alerts as in-order`
                        : "alerts DIFFER from in-order"}
                    </td>
                  </tr>
                ))}
                <tr>
                  <td>Late injection</td>
                  <td className="small">
                    <span className="num">
                      {n(c.late_injection.injected_late_rows)}
                    </span>{" "}
                    rows pushed past the 120 s bound,{" "}
                    <span className="num">
                      {n(c.late_injection.late_dropped)}
                    </span>{" "}
                    counted late. Alerts vs in-order:{" "}
                    {c.late_injection.alerts_missing_vs_in_order} missing,{" "}
                    {c.late_injection.alerts_new_vs_in_order} new.
                  </td>
                </tr>
                <tr>
                  <td>Bus round trip</td>
                  <td className="small">
                    <span className="num">
                      {n(c.bus_round_trip.rows_produced)}
                    </span>{" "}
                    rows through the embedded log:{" "}
                    {c.bus_round_trip.identical_alerts &&
                    c.bus_round_trip.identical_audit
                      ? "identical alerts and audit"
                      : "DIFFERENT"}
                  </td>
                </tr>
                {score?.live && (
                  <tr>
                    <td>Live feed</td>
                    <td className="small">
                      <span className="num">{n(score.live.rows)}</span> position
                      reports from {n(score.live.vessels)} ships in{" "}
                      {Math.round(score.live.seconds / 60)} minutes of the
                      aisstream.io feed on {score.live.started_utc.slice(0, 10)}
                      , converted to the archive&apos;s row shape and run through
                      the same processor: ledger{" "}
                      {score.live.balanced ? "balanced" : "NOT balanced"},{" "}
                      {score.live.alerts} alert{score.live.alerts === 1 ? "" : "s"}
                      {score.live.lag_seconds_median != null &&
                        `, median delay ${score.live.lag_seconds_median} s from transmission to arrival`}
                      . The free feed is sparse: a median of{" "}
                      {score.live.rows_per_vessel_median} reports per ship in 10
                      minutes, against 7 in the Danish archive for the same
                      length of window (48,121 reports from 1,563 ships on 12 Feb
                      2025, 10:00 to 10:10 UTC). At that rate the rules rarely
                      have enough fixes to fire, so live mode proves the plumbing,
                      not the detection.
                    </td>
                  </tr>
                )}
                {score?.kafka && (
                  <tr>
                    <td>Kafka (Redpanda)</td>
                    <td className="small">
                      <span className="num">{n(score.kafka.rows_consumed)}</span>{" "}
                      rows of the full 36 h window through a{" "}
                      {score.kafka.partitions}-partition topic, consumed in{" "}
                      {Math.round(score.kafka.consume_seconds)} s (
                      {n(score.kafka.consume_rows_per_second)} rows/s on a
                      laptop).{" "}
                      {score.kafka.passed
                        ? `Every row consumed, ledger balanced, ${score.kafka.alerts_parquet} alerts identical on the topic, in Parquet and in an in-process run.`
                        : "FAILED: see data/warehouse/kafka_check.json"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          ) : (
            <p className="small">Not measured yet: run make eval.</p>
          )}
          <p className="tiny">
            Why late rows are not simply processed: a vessel&apos;s state (speed
            baseline, dwell timer, crossings) only moves forward. Applying an
            old fix after a newer one would rewrite history and make alerts
            depend on network timing.
          </p>
        </div>
      </div>
    </section>
  );
}
