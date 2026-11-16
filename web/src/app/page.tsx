import Link from "next/link";
import Intro from "@/components/Intro";
import OutageLookup from "@/components/OutageLookup";
import PageNav, { CHAPTERS } from "@/components/PageNav";
import { AUTHOR } from "@/lib/site";
import { load, runDays } from "@/lib/data";

export default function Page() {
  const score = load("scorecard.json");
  const days = runDays(score);
  const built = score ? score.generated_utc.slice(0, 10) : undefined;
  const bt = score?.backtest;
  const fa = bt?.false_alerts_per_day;
  const inc: { status: string }[] = bt?.incidents ?? [];
  const keyFact: Record<string, string> = {
    "/replay/": `${score?.replays?.length ?? 0} replay windows`,
    "/incidents/": `${inc.length} incidents, ${inc.filter((r) => r.status === "testable").length} testable`,
    "/false-alerts/": fa?.gated ? `median ${fa.gated.median ?? fa.gated.mean_alerts_per_day} a day` : "",
    "/pipeline/": score?.kafka?.passed ? "Kafka check passed" : "",
  };
  return (
    <main className="wrap report home">
      <header className="title-block">
        <p className="kicker">Data engineering case study</p>
        <h1>Ships over the cables under the Baltic</h1>
        <p className="standfirst">
          A streaming pipeline that replays Danish ship-position data, flags
          ships behaving as if they are dragging an anchor across a subsea cable,
          and is graded against every publicly reported cable break the data can
          test.
        </p>
        <dl className="meta-row">
          <div>
            <dt>Data</dt>
            <dd>Danish Maritime Authority AIS</dd>
          </div>
          <div>
            <dt>Coverage</dt>
            <dd>
              {days.length} days, {days[0]?.slice(0, 7)} to {days[days.length - 1]?.slice(0, 7)}
            </dd>
          </div>
          <div>
            <dt>Prepared by</dt>
            <dd>
              <a href={AUTHOR.url} rel="author">
                {AUTHOR.name}
              </a>
            </dd>
          </div>
          {built && (
            <div>
              <dt>Data built</dt>
              <dd>{built}</dd>
            </div>
          )}
        </dl>
      </header>

      <Intro score={score} />
      <OutageLookup score={score} only="bornholm-2022" title="The headline result" />

      <section className="section" id="contents">
        <h2>Contents</h2>
        <ol className="contents">
          {CHAPTERS.slice(1).map((c, i) => (
            <li key={c.href}>
              <span className="c-num">{i + 2}</span>
              <div>
                <Link href={c.href}>{c.label}</Link>
                <p>{c.blurb}</p>
              </div>
              <span className="c-fact">{keyFact[c.href]}</span>
            </li>
          ))}
        </ol>
      </section>
      <PageNav current="/" />
    </main>
  );
}
