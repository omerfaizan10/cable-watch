import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import ChartView from "@/components/ChartView";
import Scorecard from "@/components/Scorecard";
import FalseAlerts from "@/components/FalseAlerts";
import Architecture from "@/components/Architecture";
import DataQuality from "@/components/DataQuality";
import Method from "@/components/Method";
import Masthead from "@/components/Masthead";
import Intro from "@/components/Intro";
import OutageLookup from "@/components/OutageLookup";
import { AUTHOR } from "@/lib/site";
import type { ReplayMeta } from "@/lib/types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function load(name: string): any | null {
  const p = path.join(process.cwd(), "public", "data", name);
  return existsSync(p) ? JSON.parse(readFileSync(p, "utf8")) : null;
}

export default function Page() {
  const score = load("scorecard.json");
  const coverage = load("coverage.json");
  const replays: ReplayMeta[] = score?.replays ?? [];
  const runs = Object.entries(score?.runs ?? {}).filter(([k]) => k.startsWith("gated_"));
  const days = runs.map(([k]) => k.slice(6)).sort();
  const built = score ? score.generated_utc.slice(0, 10) : undefined;
  return (
    <>
      <Masthead built={built} />
      <main className="wrap report">
        <header className="title-block">
          <p className="kicker">Data engineering case study</p>
          <h1>Ships over the cables under the Baltic</h1>
          <p className="standfirst">
            A streaming pipeline that replays Danish ship-position data, flags
            ships behaving as if they are dragging an anchor across a subsea
            cable, and is graded against every publicly reported cable break
            the data can test.
          </p>
          <dl className="meta-row">
            <div>
              <dt>Data</dt>
              <dd>Danish Maritime Authority AIS</dd>
            </div>
            <div>
              <dt>Coverage</dt>
              <dd>
                {days.length} days, {days[0]?.slice(0, 7)} to{" "}
                {days[days.length - 1]?.slice(0, 7)}
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

        <section className="section" id="replay">
          <h2>Replay</h2>
          <p className="lede">
            Pick a window and press play. Every ship is drawn where the archive
            put it at that moment, with the cable routes the detector watches.
            Ships turn red when a rule flags them, and the panel on the right
            says why.
          </p>
          {replays.length ? (
            <figure className="fig">
              <ChartView replays={replays} />
              <figcaption>
                Replay of the Danish Maritime Authority archive in event time.
                Cable routes from EMODnet and OpenStreetMap; shaded cells show
                where Danish receivers actually picked ships up. A flag is a lead
                for a person to check, not an accusation.
              </figcaption>
            </figure>
          ) : (
            <p>
              No replay files were found in web/public/data. Run make eval in
              the repository to build them.
            </p>
          )}
        </section>

        <OutageLookup score={score} />
        <Scorecard score={score} coverage={coverage} />
        <FalseAlerts score={score} />
        <DataQuality score={score} />
        <Architecture />
        <Method score={score} />
      </main>
    </>
  );
}
