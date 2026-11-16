// Four small sketches of what each rule looks for, drawn against one cable line.
// Plain SVG so the shapes use the chart's own colours.

const W = 220;
const H = 120;
const CABLE = "M 0 78 C 60 70, 150 86, 220 76";

function Frame({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={label} className="sketch">
      <rect width={W} height={H} fill="var(--sea)" />
      <path d={CABLE} fill="none" stroke="var(--cable-power)" strokeWidth={2} />
      <text x={6} y={H - 8} className="sk-t">cable</text>
      {children}
    </svg>
  );
}

const dot = (x: number, y: number, k: number, hot = false) => (
  <circle key={k} cx={x} cy={y} r={hot ? 3.2 : 2.4} fill={hot ? "var(--alert)" : "var(--vessel)"} />
);

export function SpeedDrop() {
  // Evenly spaced dots, then bunched up near the cable: same time between fixes, less distance.
  const xs = [10, 38, 66, 94, 122, 136, 146, 153, 158, 162];
  return (
    <Frame label="A ship slowing sharply as it reaches the cable: its position dots bunch together">
      {xs.map((x, i) => dot(x, 30 + i * 4.6, i, i >= 5))}
      <text x={10} y={18} className="sk-t">evenly spaced, then bunched</text>
    </Frame>
  );
}

export function SlowDwell() {
  const pts = [
    [100, 70], [104, 73], [99, 76], [103, 79], [106, 74], [101, 72], [98, 78], [104, 76],
  ];
  return (
    <Frame label="A ship sitting almost still on top of the cable for half an hour or more">
      <path d="M 20 20 L 96 68" stroke="var(--vessel)" strokeDasharray="2 4" fill="none" />
      {pts.map(([x, y], i) => dot(x, y, i, true))}
      <text x={10} y={18} className="sk-t">parked on the cable</text>
    </Frame>
  );
}

export function DragSignature() {
  // Ship points one way (heading arrows) while drifting sideways along the cable.
  const pts = [
    [40, 66], [62, 72], [84, 64], [106, 75], [128, 67], [150, 76], [172, 68],
  ];
  return (
    <Frame label="A ship pointing one way while being pulled sideways along the cable, with a wandering track">
      {pts.map(([x, y], i) => (
        <g key={i}>
          <line x1={x} y1={y} x2={x - 3} y2={y - 16} stroke="var(--alert)" strokeWidth={1.2} />
          {dot(x, y, i, true)}
        </g>
      ))}
      <text x={10} y={18} className="sk-t">points north, slides east</text>
    </Frame>
  );
}

export function RepeatCrossing() {
  return (
    <Frame label="A ship zigzagging back and forth across the same cable several times in ninety minutes">
      <path
        d="M 30 30 L 70 110 L 100 40 L 130 112 L 160 36 L 196 108"
        fill="none"
        stroke="var(--alert)"
        strokeWidth={1.4}
      />
      <text x={10} y={18} className="sk-t">three crossings in 90 min</text>
    </Frame>
  );
}
