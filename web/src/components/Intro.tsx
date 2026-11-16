/* eslint-disable @typescript-eslint/no-explicit-any */

const n = (v: number) => v.toLocaleString("en-US");

type Finding = { big: string; text: string; key?: boolean };

export default function Intro({ score }: { score: any }) {
  const bt = score?.backtest;
  const bh = bt?.incidents?.find((r: any) => r.incident_id === "bornholm-2022");
  const ol = bh?.outage_lookup;
  const fa = bt?.false_alerts_per_day;
  const det = score?.correctness?.determinism ?? [];
  const rows = score?.correctness?.rows;
  const runs = Object.entries(score?.runs ?? {}).filter(([k]) => k.startsWith("gated_"));
  const nDays = runs.length;
  const nRows = runs.reduce((a, [, v]: [string, any]) => a + (v.raw_in ?? 0), 0);
  const normal: string[] = (bt?.normal_days ?? []).filter((d: any) => !d.tuning_day).map((d: any) => d.day).sort();
  const span = normal.length ? `${normal[0].slice(0, 7)} to ${normal[normal.length - 1].slice(0, 7)}` : "";
  const findings: Finding[] = [];
  if (ol?.named_vessel_rank)
    findings.push({
      key: true,
      big: ol.named_vessel_rank === 1 ? `1st of ${ol.candidates}` : `#${ol.named_vessel_rank} of ${ol.candidates}`,
      text: `Samus Swan's place among the ships that crossed the Bornholm power cable within ${ol.window_h} hours of the 2022 blackout, ranked by how close each crossing came to the failure. It crossed ${Math.abs(ol.named_vessel_offset_min)} minutes from the reported time; a Danish court later found it had been dragging its anchor.`,
    });
  if (fa?.gated && fa?.agnostic)
    findings.push({
      big: `${n(Math.round(fa.gated.median ?? fa.gated.mean_alerts_per_day))} a day`,
      text: `Alerts on a typical ordinary day (the median of ${fa.gated.days}) when the rules only watch mapped cables, against ${n(Math.round(fa.agnostic.median ?? fa.agnostic.mean_alerts_per_day))} when they watch the whole sea.`,
    });
  if (det.length && det.every((d: any) => d.identical_to_in_order))
    findings.push({
      big: `${det.length} of ${det.length}`,
      text: `Shuffled replays of ${rows ? n(rows) : "the same"} position reports that gave exactly the same alerts as the in-order run. Arrival order does not change the answer.`,
    });
  return (
    <section className="section" id="summary">
      <h2>Summary</h2>
      <div className="summary-text">
        <p>
          Ships broadcast their position every few seconds. I replay {nDays} days
          of those broadcasts from the western Baltic (
          {nRows >= 1e9 ? `${(nRows / 1e9).toFixed(2)} billion` : `${Math.round(nRows / 1e6)} million`}{" "}
          position reports): the days around reported cable breaks, plus{" "}
          {normal.length} ordinary days from {span}. A streaming pipeline
          watches for ships behaving as if they are dragging an anchor across a
          subsea cable, and I check it against every publicly reported break the
          data can test.
        </p>
        <p className="honest">
          The behavior rules did not catch the one break they could be tested
          on: that ship kept a normal cruising speed with its anchor down.
          Knowing which ships crossed the cable, and when, did.
        </p>
      </div>
      {findings.length > 0 && (
        <ol className="findings" aria-label="Key findings">
          {findings.map((f) => (
            <li key={f.big} className={f.key ? "key" : undefined}>
              <span className="big">{f.big}</span>
              <p>{f.text}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
