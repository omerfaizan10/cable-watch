/* eslint-disable @typescript-eslint/no-explicit-any */

const min = (ms: number) => `${Math.round(ms / 60000)} min`;

export default function Method({ score }: { score: any }) {
  const c = score?.config;
  if (!c) return null;
  const rules: [string, string][] = [
    [
      "Speed drop",
      `Median speed over the last ${min(c.drop_recent_window_ms)} falls below ${Math.round(
        c.drop_max_ratio * 100,
      )}% of the median from ${min(c.drop_baseline_window_ms[0])} to ${min(
        c.drop_baseline_window_ms[1],
      )} earlier, the earlier median was at least ${c.drop_min_baseline_kn} kn, and the drop is at least ${c.drop_min_delta_kn} kn.`,
    ],
    [
      "Slow dwell",
      `Below ${c.loiter_max_sog_kn} kn within ${(c.cable_buffer_m / 1000).toFixed(1)} km of the same cable for at least ${min(c.loiter_min_dwell_ms)}.`,
    ],
    [
      "Drag signature",
      `Over ${min(c.drag_window_ms)} and at least ${c.drag_min_fixes} fixes: median speed between ${c.drag_sog_range_kn[0]} and ${c.drag_sog_range_kn[1]} kn, course spread of ${c.drag_min_cog_std_deg}° or more, heading and course apart by ${c.drag_min_heading_cog_gap_deg}° or more, and still moving at least ${c.drag_min_displacement_m} m. A ship pulled sideways by its own anchor points one way and moves another.`,
    ],
    [
      "Repeated crossing",
      `${c.cross_min_count} or more crossings of the same cable within ${min(c.cross_window_ms)}, with crossings closer than ${min(c.cross_min_gap_ms)} counted once.`,
    ],
  ];
  return (
    <section className="section" id="method">
      <h2>Method</h2>
      <p className="lede">
        Every threshold below is read from the same config file the processor
        uses, so the page cannot drift from the code. The defaults come from
        published incident descriptions (speeds reported for Eagle S, Newnew
        Polar Bear and Samus Swan), not from fitting the backtest.
      </p>
      <div className="scroll-x">
        <table className="t">
          <thead>
            <tr>
              <th>Rule</th>
              <th>Fires when</th>
            </tr>
          </thead>
          <tbody>
            {rules.map(([name, text]) => (
              <tr key={name}>
                <td style={{ whiteSpace: "nowrap" }}>{name}</td>
                <td>{text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        <b>Which ships are checked.</b> {c.mobile_types.join(", ")} transponders
        on vessels {c.min_length_m} m or longer (unknown length is kept), not
        moored, and not in a working category such as fishing, dredging, tugs
        or pilots. Every other row still passes through the data quality
        accounting, so nothing disappears silently.
      </p>
      <p>
        <b>Cable-gated and cable-agnostic.</b> Gated runs only evaluate fixes
        within {(c.cable_buffer_m / 1000).toFixed(1)} km of a mapped route and
        ignore the last {(c.landing_exclusion_m / 1000).toFixed(0)} km before a
        landing point, where ships approach port. Agnostic runs apply the same
        rules everywhere. Comparing the two shows how much of the alert volume
        the cable map removes, and what it costs when a route is missing from
        the map.
      </p>
      <p>
        <b>Streaming guarantees.</b> Each vessel&apos;s fixes are reordered by
        event time within {Math.round(c.allowed_lateness_ms / 1000)} s. Exact
        duplicates (one message heard by several base stations) are dropped,
        and a fix implying more than {c.teleport_max_kn} kn is held back as a
        bad position unless {c.teleport_reset_after} in a row agree, which
        restarts the track. Alerts for the same vessel, rule and cable are
        suppressed for {min(c.alert_cooldown_ms)}.
      </p>
      <p>
        <b>Data.</b> AIS: Danish Maritime Authority historical archive, read
        straight from the published daily files. Cable routes: EMODnet Human
        Activities (CC BY 4.0, originator Cogea Srl), plus routes the
        incidents depend on that EMODnet lacks (the Bornholm cable), from
        OpenStreetMap contributors (ODbL). Incidents: public reporting, with every source
        listed per row in data/reference/incidents.csv.
      </p>
      <p>
        <b>What a flag means.</b> Behavior consistent with anchor drag near a
        cable. It is a lead for a human analyst, never a finding of fault.
      </p>
    </section>
  );
}
