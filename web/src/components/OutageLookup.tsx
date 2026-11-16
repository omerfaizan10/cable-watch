/* eslint-disable @typescript-eslint/no-explicit-any */

const W = 720;
const LEFT = 186;
const RIGHT = 24;
const ROW = 22;

export default function OutageLookup({
  score,
  only,
  title = "Who was over the cable when it failed?",
}: {
  score: any;
  only?: string;
  title?: string;
}) {
  const inc: any[] = score?.backtest?.incidents ?? [];
  const cases = inc.filter((r) => r.outage_lookup?.candidates && (!only || r.incident_id === only));
  if (!cases.length) return null;
  return (
    <section className="section" id="outage-lookup">
      <h2>{title}</h2>
      {cases.map((r) => {
        const ol = r.outage_lookup;
        const top: any[] = ol.top;
        const span = ol.window_h * 60;
        const x = (m: number) => LEFT + ((m + span) / (2 * span)) * (W - LEFT - RIGHT);
        const H = top.length * ROW + 46;
        const named = top.find((c) => c.rank === ol.named_vessel_rank);
        return (
          <div key={r.incident_id} className="ol-case">
            {!only && (
              <h3>
                {r.asset.split(" (")[0]}, {r.damage_utc.slice(0, 10)}
              </h3>
            )}
            <p className="lede">
              {named ? (
                <>
                  {ol.candidates} ships crossed the {top[0].route} within{" "}
                  {ol.window_h} hours of the reported failure at{" "}
                  {r.damage_utc.slice(11, 16)} UTC on{" "}
                  {r.damage_utc.slice(0, 10)}. Sorting them by how close their
                  crossing came to that moment puts <b>{r.vessel}</b> first,{" "}
                  {Math.abs(ol.named_vessel_offset_min)} minutes off. The next
                  ship was {ol.runner_up_abs_offset_min} minutes off, so this
                  only works because the failure time was published to the
                  minute.
                </>
              ) : (
                <>
                  {ol.candidates} ships crossed the route near the reported
                  time of the {r.asset.split(" (")[0]} failure on{" "}
                  {r.damage_utc.slice(0, 10)}, and {r.vessel || "the named vessel"}{" "}
                  is not among them: it only came into Danish receiver range after
                  the break, so this case cannot test the method.
                </>
              )}
            </p>
            {named ? (
              <>
            <p className="howto">
              How to read it: each row is a ship, placed at the time it crossed
              the cable. The vertical line is the reported failure. The closer
              a dot is to the line, the better that ship fits the timing.
            </p>
            <div className="scroll-x">
              <svg
                viewBox={`0 0 ${W} ${H}`}
                width="100%"
                style={{ maxWidth: W, minWidth: 520 }}
                role="img"
                aria-label={`Crossings of the ${top[0]?.route} around the reported failure, closest ${top.length} ships`}
              >
                {[-span, -span / 2, 0, span / 2, span].map((m) => (
                  <g key={m}>
                    <line x1={x(m)} x2={x(m)} y1={14} y2={H - 26} stroke="var(--rule)" />
                    <text x={x(m)} y={H - 10} textAnchor="middle" className="axis-t">
                      {m === 0 ? "failure" : `${m > 0 ? "+" : "−"}${Math.abs(m / 60)} h`}
                    </text>
                  </g>
                ))}
                <line x1={x(0)} x2={x(0)} y1={6} y2={H - 26} stroke="var(--alert)" strokeWidth={1.5} />
                {top.map((c, i) => {
                  const y = 22 + i * ROW;
                  const hit = c.rank === ol.named_vessel_rank;
                  return (
                    <g key={c.mmsi}>
                      <text x={LEFT - 10} y={y + 4} textAnchor="end" className={hit ? "row-t hit" : "row-t"}>
                        {c.name || `MMSI ${c.mmsi}`}
                      </text>
                      <line x1={x(0)} x2={x(c.offset_min)} y1={y} y2={y} stroke={hit ? "var(--alert)" : "var(--rule-2)"} />
                      <circle cx={x(c.offset_min)} cy={y} r={hit ? 5 : 3.5} fill={hit ? "var(--alert)" : "var(--vessel)"} />
                      <text x={x(c.offset_min) + (c.offset_min >= 0 ? 9 : -9)} y={y + 4} textAnchor={c.offset_min >= 0 ? "start" : "end"} className="val-t">
                        {c.offset_min > 0 ? "+" : c.offset_min < 0 ? "−" : ""}
                        {Math.abs(c.offset_min)} min
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>
                <p className="figcap">
                  Ships crossing the {top[0]?.route} around the reported
                  failure, closest {top.length} of {ol.candidates}, by minutes
                  from the failure time.
                </p>
              </>
            ) : (
              <details className="tech">
                <summary>Show the {top.length} closest crossings</summary>
            <p className="howto">
              How to read it: each row is a ship, placed at the time it crossed
              the cable. The vertical line is the reported failure. The closer
              a dot is to the line, the better that ship fits the timing.
            </p>
            <div className="scroll-x">
              <svg
                viewBox={`0 0 ${W} ${H}`}
                width="100%"
                style={{ maxWidth: W, minWidth: 520 }}
                role="img"
                aria-label={`Crossings of the ${top[0]?.route} around the reported failure, closest ${top.length} ships`}
              >
                {[-span, -span / 2, 0, span / 2, span].map((m) => (
                  <g key={m}>
                    <line x1={x(m)} x2={x(m)} y1={14} y2={H - 26} stroke="var(--rule)" />
                    <text x={x(m)} y={H - 10} textAnchor="middle" className="axis-t">
                      {m === 0 ? "failure" : `${m > 0 ? "+" : "−"}${Math.abs(m / 60)} h`}
                    </text>
                  </g>
                ))}
                <line x1={x(0)} x2={x(0)} y1={6} y2={H - 26} stroke="var(--alert)" strokeWidth={1.5} />
                {top.map((c, i) => {
                  const y = 22 + i * ROW;
                  const hit = c.rank === ol.named_vessel_rank;
                  return (
                    <g key={c.mmsi}>
                      <text x={LEFT - 10} y={y + 4} textAnchor="end" className={hit ? "row-t hit" : "row-t"}>
                        {c.name || `MMSI ${c.mmsi}`}
                      </text>
                      <line x1={x(0)} x2={x(c.offset_min)} y1={y} y2={y} stroke={hit ? "var(--alert)" : "var(--rule-2)"} />
                      <circle cx={x(c.offset_min)} cy={y} r={hit ? 5 : 3.5} fill={hit ? "var(--alert)" : "var(--vessel)"} />
                      <text x={x(c.offset_min) + (c.offset_min >= 0 ? 9 : -9)} y={y + 4} textAnchor={c.offset_min >= 0 ? "start" : "end"} className="val-t">
                        {c.offset_min > 0 ? "+" : c.offset_min < 0 ? "−" : ""}
                        {Math.abs(c.offset_min)} min
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>
              </details>
            )}
            <details className="tech">
              <summary>Technical note</summary>
              <p>
                For each ship with position reports inside the route&apos;s
                bounding box during the window, consecutive fixes less than 15
                minutes apart are joined by a straight line and intersected with
                the cable route; the crossing time is interpolated along that
                segment. Ships are ranked by the absolute gap between crossing
                time and reported failure time.
                {r.incident_id === "bornholm-2022" &&
                  " The route comes from OpenStreetMap (EMODnet does not include it)."}
                {r.time_precision !== "minute" &&
                  ` The failure time is only public to ${r.time_precision.replace("approx ", "about ")}, so the ranking is weak evidence either way.`}{" "}
                The crossing point sits{" "}
                {named ? `at ${named.lat.toFixed(3)}°N ${named.lon.toFixed(3)}°E` : "on the route"}
                {r.incident_id === "bornholm-2022" &&
                  ", 16.7 km from the Swedish landing and 24.6 km from Bornholm in a straight line; the operator reported the break 17 km from Sweden and 26 km from Bornholm"}
                . Showing the {top.length} closest of{" "}
                {ol.candidates}.
              </p>
            </details>
          </div>
        );
      })}
    </section>
  );
}
