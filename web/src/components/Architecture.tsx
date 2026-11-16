// Pipeline diagram drawn as plain SVG so it uses the chart's own ink and line weights.

const BOX = { w: 150, h: 54 };

function Node({
  x,
  y,
  title,
  sub,
  accent,
}: {
  x: number;
  y: number;
  title: string;
  sub: string;
  accent?: string;
}) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={BOX.w}
        height={BOX.h}
        fill="var(--paper)"
        stroke={accent ?? "var(--rule-2)"}
      />
      <text
        x={x + 8}
        y={y + 20}
        fill="var(--ink)"
        fontSize={12.5}
        fontFamily="Public Sans"
        fontWeight={500}
      >
        {title}
      </text>
      <text
        x={x + 8}
        y={y + 38}
        fill="var(--ink-3)"
        fontSize={10.5}
        fontFamily="Public Sans"
      >
        {sub}
      </text>
    </g>
  );
}

function Topic({ x, y, name }: { x: number; y: number; name: string }) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={112}
        height={24}
        fill="none"
        stroke="var(--cable-power)"
        strokeDasharray="3 2"
      />
      <text
        x={x + 56}
        y={y + 16}
        fill="var(--cable-power)"
        fontSize={11}
        fontFamily="Public Sans"
        textAnchor="middle"
      >
        {name}
      </text>
    </g>
  );
}

function Arrow({ d }: { d: string }) {
  return (
    <path
      d={d}
      fill="none"
      stroke="var(--ink-3)"
      strokeWidth={1}
      markerEnd="url(#arr)"
    />
  );
}

export default function Architecture({ bare = false }: { bare?: boolean }) {
  const diagram = (
      <div className="scroll-x">
        <svg
          viewBox="0 0 1060 300"
          width="100%"
          style={{ minWidth: 760 }}
          role="img"
          aria-label="Pipeline architecture diagram"
        >
          <defs>
            <marker
              id="arr"
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="7"
              markerHeight="7"
              orient="auto"
            >
              <path d="M0,0 L8,4 L0,8 z" fill="var(--ink-3)" />
            </marker>
          </defs>
          <Node x={10} y={20} title="DMA archive" sub="daily zip, streamed" />
          <Node
            x={10}
            y={120}
            title="aisstream.io"
            sub="WebSocket, needs key"
          />
          <Node x={10} y={220} title="Cable routes" sub="EMODnet + OpenStreetMap" />
          <Node x={200} y={20} title="Extractor" sub="bbox filter, Parquet" />
          <Node x={200} y={120} title="Live consumer" sub="to DMA row shape" />
          <Node x={200} y={220} title="Route index" sub="H3 res 8, segments" />
          <Node
            x={390}
            y={20}
            title="Replay producer"
            sub="event time, disorder"
          />
          <Topic x={410} y={135} name="ais.raw" />
          <Node
            x={580}
            y={110}
            title="Stream processor"
            sub="reorder, DQ, rules"
            accent="var(--ink)"
          />
          <Topic x={780} y={60} name="cable.alerts" />
          <Topic x={780} y={150} name="ais.late" />
          <Node
            x={900}
            y={20}
            title="Parquet + DuckDB"
            sub="alerts, run audits"
          />
          <Node x={900} y={220} title="Static site" sub="precomputed JSON" />
          <Arrow d="M160,47 L198,47" />
          <Arrow d="M160,147 L198,147" />
          <Arrow d="M160,247 L198,247" />
          <Arrow d="M350,47 L388,47" />
          <Arrow d="M465,74 L465,133" />
          <Arrow d="M350,147 L408,147" />
          <Arrow d="M522,147 L578,137" />
          <Arrow d="M350,247 L655,247 L655,166" />
          <Arrow d="M730,125 L778,75" />
          <Arrow d="M730,145 L778,160" />
          <Arrow d="M892,72 L898,60" />
          <Arrow d="M975,74 L975,218" />
          <text
            x={580}
            y={190}
            fill="var(--ink-3)"
            fontSize={10.5}
            fontFamily="Public Sans"
          >
            per-MMSI reorder buffer, 120 s bound
          </text>
          <text
            x={580}
            y={204}
            fill="var(--ink-3)"
            fontSize={10.5}
            fontFamily="Public Sans"
          >
            schema, MMSI, duplicate, teleport checks
          </text>
          <text
            x={10}
            y={292}
            fill="var(--ink-3)"
            fontSize={10.5}
            fontFamily="Public Sans"
          >
            Bus: Redpanda (checked end to end with make kafka-check) or an
            embedded append-only log, same interface. Backfills: make -j4 backfill.
          </text>
        </svg>
      </div>
  );
  if (bare) return diagram;
  return (
    <section className="section" id="architecture">
      <h2>Pipeline</h2>
      <p className="lede">
        One processor, three ways to feed it. The archive replay and the live
        consumer both publish DMA-shaped rows keyed by MMSI, so every fix of a
        vessel lands in one partition and keeps its order. The processor holds
        per-vessel state and writes alerts to a topic and to Parquet, which
        DuckDB reads.
      </p>
      <figure className="fig">
        {diagram}
        <figcaption>
          The pipeline. Archive replay and live feed share one row format and
          one processor; the bus is Redpanda or an embedded log behind the same
          interface.
        </figcaption>
      </figure>
    </section>
  );
}
