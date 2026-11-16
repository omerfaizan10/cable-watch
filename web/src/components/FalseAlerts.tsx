"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from "react";

const RULES: [string, string][] = [
  ["repeat_crossing", "Repeated crossing"],
  ["sog_drop", "Speed drop"],
  ["loiter", "Slow dwell"],
  ["drag_signature", "Drag signature"],
];
// Four rule colours from the report palette (globals.css); red stays reserved for findings.
const HUE: Record<string, string> = {
  repeat_crossing: "var(--rule-a)",
  sog_drop: "var(--rule-b)",
  loiter: "var(--rule-c)",
  drag_signature: "var(--rule-d)",
};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function FalseAlerts({ score }: { score: any }) {
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const bt = score?.backtest;
  if (!bt?.normal_days?.length)
    return (
      <section className="section">
        <h2>False alerts on normal days</h2>
        <p className="lede">Not measured yet: the normal-day runs are missing.</p>
      </section>
    );
  const days: any[] = bt.normal_days.filter((d: any) => d.gated && d.agnostic).sort((a: any, b: any) => a.day.localeCompare(b.day));
  const fa = bt.false_alerts_per_day;
  const held = days.filter((d) => !d.tuning_day);
  const g = fa?.gated;
  const max = Math.max(1, ...days.map((d) => d.gated.alerts));
  const top = Math.ceil(max / 20) * 20;
  const W = 720;
  const H = 260;
  const L = 34;
  const R = 8;
  const T = 12;
  const B = 40;
  const slot = (W - L - R) / days.length;
  const bw = Math.max(4, slot - 3);
  const y = (v: number) => T + (H - T - B) * (1 - v / top);
  const ticks = [0, top / 2, top];
  return (
    <section className="section" id="false-alerts">
      <h2>False alerts on normal days</h2>
      <p className="lede">
        On {g?.days ?? 0} ordinary days with no reported incident, from{" "}
        {held[0]?.day.slice(0, 7)} to {held[held.length - 1]?.day.slice(0, 7)},
        the detector raised a median of{" "}
        <span className="num">{g?.median ?? g?.mean_alerts_per_day}</span> alerts
        a day when it only watches mapped cables (mean{" "}
        <span className="num">{g?.mean_alerts_per_day}</span>;{" "}
        {g?.p10 != null ? "eight days in ten fell between" : "range"}{" "}
        <span className="num">{g?.p10 ?? g?.min}</span> and{" "}
        <span className="num">{g?.p90 ?? g?.max}</span>). Watching the whole
        sea instead gives a median of{" "}
        <span className="num">
          {(fa?.agnostic?.median ?? fa?.agnostic?.mean_alerts_per_day)?.toLocaleString("en-US")}
        </span>
        .
        Every alert on these days is counted as false, which overstates the
        problem: survey and cable-work vessels really do loiter over cables.
      </p>
      <p className="howto">
        How to read it: one column per day, in date order. The colours show which
        rule raised the alerts; the dashed line is the median day.
      </p>
      <figure className="fig">
      <div className="scroll-x" style={{ position: "relative" }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          style={{ maxWidth: W, minWidth: 560 }}
          role="img"
          aria-label={`Alerts per ordinary day by rule, ${days.length} days, median ${g?.median}`}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--rule)" />
              <text x={L - 6} y={y(t) + 4} textAnchor="end" className="axis-t">
                {t}
              </text>
            </g>
          ))}
          {days.map((d, i) => {
            const x = L + i * slot + (slot - bw) / 2;
            let acc = 0;
            const showMonth = i === 0 || days[i - 1].day.slice(0, 7) !== d.day.slice(0, 7);
            return (
              <g key={d.day}>
                {RULES.map(([k, label]) => {
                  const n = d.gated.by_rule?.[k]?.alerts ?? 0;
                  if (!n) return null;
                  const y0 = y(acc + n);
                  const h = y(acc) - y0;
                  acc += n;
                  return (
                    <rect
                      key={k}
                      x={x}
                      y={y0}
                      width={bw}
                      height={Math.max(1, h - 1)}
                      fill={HUE[k]}
                      opacity={d.tuning_day ? 0.4 : 0.9}
                      onMouseMove={(e) => {
                        const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                        setTip({
                          x: e.clientX - r.left,
                          y: e.clientY - r.top,
                          text: `${d.day}${d.tuning_day ? " (tuning day)" : ""}: ${label} ${n}, all rules ${d.gated.alerts}`,
                        });
                      }}
                      onMouseLeave={() => setTip(null)}
                    />
                  );
                })}
                {showMonth && (
                  <text x={x} y={H - B + 16} className="axis-t">
                    {MONTHS[Number(d.day.slice(5, 7)) - 1]}
                    {d.day.slice(5, 7) === "01" || i === 0 ? ` ${d.day.slice(2, 4)}` : ""}
                  </text>
                )}
              </g>
            );
          })}
          {g?.median != null && (
            <g>
              <line x1={L} x2={W - R} y1={y(g.median)} y2={y(g.median)} stroke="var(--ink-2)" strokeDasharray="4 3" />
              <text x={W - R} y={y(g.median) - 5} textAnchor="end" className="val-t">
                median {g.median}
              </text>
            </g>
          )}
        </svg>
        {tip && (
          <div className="chart-tip" style={{ left: tip.x + 12, top: tip.y - 28 }}>
            {tip.text}
          </div>
        )}
      </div>
      <div className="legend" style={{ gridTemplateColumns: "repeat(4, 14px auto)", marginTop: 8, justifyContent: "start" }}>
        {RULES.map(([k, label]) => (
          <span key={k} style={{ display: "contents" }}>
            <span style={{ width: 12, height: 10, background: HUE[k] }} />
            <span>{label}</span>
          </span>
        ))}
      </div>
      <figcaption>
        Alerts per ordinary day from the cable-gated detector, stacked by the
        rule that raised them, in date order. Faded column: the tuning day,
        excluded from every figure in the text.
      </figcaption>
      </figure>
      <details className="tech">
        <summary>Full table, {days.length} days</summary>
        <p>
          The faded column is the tuning day (2024-04-10), looked at while
          setting thresholds and left out of every figure above. Four ordinary
          days (2024-06-12, 2024-08-14, 2024-10-09, 2025-02-12) were chosen
          before any results existed
          {held.length > 4
            ? `; the other ${held.length - 4} were drawn at random, 2 or 3 per month, never within a day of a reported incident (scripts/pick_normal_days.py).`
            : "."}
        </p>
        <div className="scroll-x">
          <table className="t">
            <thead>
              <tr>
                <th>Day</th>
                <th className="n">Mapped cables: alerts</th>
                <th className="n">Ships</th>
                <th className="n">Whole sea: alerts</th>
                <th className="n">Ships</th>
              </tr>
            </thead>
            <tbody>
              {days.map((d) => (
                <tr key={d.day}>
                  <td className="mono">
                    {d.day}
                    {d.tuning_day ? " (tuning)" : ""}
                  </td>
                  <td className="n">{d.gated.alerts}</td>
                  <td className="n">{d.gated.vessels}</td>
                  <td className="n">{d.agnostic?.alerts?.toLocaleString("en-US") ?? "not run"}</td>
                  <td className="n">{d.agnostic?.vessels?.toLocaleString("en-US") ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
