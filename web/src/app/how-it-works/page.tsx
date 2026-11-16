/* eslint-disable @typescript-eslint/no-explicit-any */
import type { Metadata } from "next";
import Link from "next/link";
import PageNav from "@/components/PageNav";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import Architecture from "@/components/Architecture";
import { SpeedDrop, SlowDwell, DragSignature, RepeatCrossing } from "@/components/RuleSketches";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "A plain-language walk through Cable Watch: what ships broadcast, what anchor dragging looks like in that data, how the streaming pipeline works, and how it was graded against real Baltic cable breaks.",
  alternates: { canonical: "/how-it-works/" },
};

function load(name: string): any | null {
  const p = path.join(process.cwd(), "public", "data", name);
  return existsSync(p) ? JSON.parse(readFileSync(p, "utf8")) : null;
}

const VERDICT: Record<string, string> = {
  testable: "Testable: the ship is in the data before the break",
  in_coverage_only_after_damage: "The ship only enters Danish coverage after the break",
  vessel_not_in_coverage: "The ship never comes into Danish coverage",
  outside_coverage_not_downloaded: "Too far east for Danish receivers",
  not_in_archive: "After the public archive ends",
  damage_time_unknown: "Only the date of the break is public",
};

export default function HowItWorks() {
  const score = load("scorecard.json");
  const bt = score?.backtest;
  const inc: any[] = bt?.incidents ?? [];
  const fa = bt?.false_alerts_per_day;
  const east = load("coverage.json")?.east_limit_lon_1000_fixes_per_day ?? 18.6;
  return (
    <>
      <main className="wrap explainer">
        <header className="ex-head">
          <p className="kicker">Section 7 · How it works</p>
          <h1>Watching ships over the cables under the Baltic</h1>
          <p className="ex-lede">
            Power lines and internet cables run along the floor of the Baltic
            Sea between Sweden, Denmark, Germany, Finland and the Baltic states.
            Since 2022 several have been cut, and in most of the cases that were
            investigated a ship had dragged its anchor across them. This page
            explains, without jargon, how I built a system that watches ship
            traffic for that behavior, and how well it actually did.
          </p>
        </header>

        <section className="ex-sec">
          <span className="ex-num">1.</span>
          <div>
            <h2>Every large ship says where it is</h2>
            <p>
              Ships over a certain size must carry a transponder called AIS. It
              broadcasts the ship&apos;s identity, position, speed, the
              direction it is moving and the direction its bow points, every few
              seconds while under way. Coast stations pick these messages up.
              Denmark&apos;s Maritime Authority publishes everything its stations
              heard as one file per day.
            </p>
            <p>
              A single busy day in the western Baltic is about 13 million
              messages. Many are repeats (several stations hear the same
              message), some have impossible positions, and they do not arrive
              in order. Cleaning that up correctly is most of the engineering.
            </p>
          </div>
        </section>

        <section className="ex-sec">
          <span className="ex-num">2.</span>
          <div>
            <h2>What dragging an anchor looks like in that data</h2>
            <p>
              Nobody broadcasts &ldquo;my anchor is down&rdquo;. But an anchor
              biting into the seabed changes how a ship moves, and those changes
              show up in its position reports. I watch for four patterns, each
              taken from published accounts of real incidents rather than tuned
              to make the results look good.
            </p>
            <div className="sketches">
              <figure>
                <SpeedDrop />
                <figcaption>
                  <b>Sharp slowdown over a cable.</b> The anchor acts as a
                  brake. Eagle S fell from about 12 to 9 knots when its anchor
                  dropped in 2024.
                </figcaption>
              </figure>
              <figure>
                <SlowDwell />
                <figcaption>
                  <b>Sitting on a cable.</b> Barely moving, within 1.5 km of the
                  same cable, for half an hour or more.
                </figcaption>
              </figure>
              <figure>
                <DragSignature />
                <figcaption>
                  <b>Pointing one way, moving another.</b> A ship pulled by its
                  own anchor slides sideways, so its bow and its track disagree.
                </figcaption>
              </figure>
              <figure>
                <RepeatCrossing />
                <figcaption>
                  <b>Crossing the same cable again and again.</b> Three or more
                  times within 90 minutes, which a ship on passage never does.
                </figcaption>
              </figure>
            </div>
            <p className="note">
              A flag only means a ship behaved in a way consistent with anchor
              drag near a cable. It is a lead for a person to check, never proof
              that anyone did anything wrong.
            </p>
          </div>
        </section>

        <section className="ex-sec">
          <span className="ex-num">3.</span>
          <div>
            <h2>The pipeline, step by step</h2>
            <p>
              The archive is replayed as if it were arriving live, at 120 times
              real speed, with messages deliberately
              shuffled and delayed the way a real feed would deliver them. A
              stream processor keeps a short memory of each ship, puts its
              messages back in time order, throws out repeats and impossible
              jumps, and runs the four checks on every position near a cable.
              Alerts land in a small warehouse for analysis, and every run ends
              with a ledger that must balance: every message read is accounted
              for as accepted, rejected, a duplicate or late.
            </p>
            <Architecture bare />
            <p>
              To trust the output, I replay the same day in three random orders
              and with extra late messages, and check the alerts come out
              exactly the same. They do.
            </p>
          </div>
        </section>

        <section className="ex-sec">
          <span className="ex-num">4.</span>
          <div>
            <h2>Grading it against real cable breaks</h2>
            <p>
              I collected every publicly reported Baltic cable or pipeline break
              since 2022, with the ship that was named and the time of the
              break, from news reports and investigators&apos; statements. Then
              I asked, for each one, whether the data can fairly test it.
              Most cannot, and the reasons are worth saying out loud:
            </p>
            <ul className="verdicts">
              {inc.map((r) => (
                <li key={r.incident_id}>
                  <span className="v-date">{r.damage_utc.slice(0, 10)}</span>
                  <span className="v-asset">
                    {r.asset.split(" (")[0]}
                    {r.vessel ? `, ${r.vessel}` : ""}
                  </span>
                  <span className={r.status === "testable" ? "v-tag ok" : "v-tag"}>
                    {VERDICT[r.status] ?? r.status}
                  </span>
                </li>
              ))}
            </ul>
            <p>
              Danish coast stations reliably hear ships out to about{" "}
              {east.toFixed(1)} degrees east, short of eastern Gotland and the Gulf of Finland, where most of the
              recent breaks happened. The public daily files also stop in
              February 2025.
            </p>
          </div>
        </section>

        <section className="ex-sec">
          <span className="ex-num">5.</span>
          <div>
            <h2>What I found</h2>
            <p>
              <b>The behavior checks missed the one break they could be tested
              on.</b> On 26 February 2022 the Bornholm power cable failed at
              05:17 UTC. The Danish court later found the tanker Samus Swan had
              been dragging its anchor for about 35 hours. In the data, Samus
              Swan crosses the cable at a steady 9.6 knots on a straight course,
              which looks like any other ship on passage. It only stops more than
              two hours later, when its status changes to &ldquo;not under
              command&rdquo;. No rule built on
              speed or course could have flagged it.
            </p>
            <p>
              <b>Timing and position found it.</b> Listing every ship that
              crossed the cable in the eight hours around the failure, and
              sorting by how close each crossing came to 05:17, puts Samus Swan
              first: it crossed three minutes after the reported time, at a
              point 16.7 km from Sweden. The operator reported the break 17 km
              from Sweden. That is the question an investigator asks first, and
              it needs no behavior rule at all.
            </p>
            {fa?.gated && fa?.agnostic && (
              <p>
                <b>The cable map matters.</b> On a typical ordinary day (the
                median of {fa.gated.days}) the checks raise{" "}
                {Math.round(fa.gated.median ?? fa.gated.mean_alerts_per_day)} alerts
                when they only watch mapped cables, and about{" "}
                {Math.round(fa.agnostic.median ?? fa.agnostic.mean_alerts_per_day).toLocaleString("en-US")}{" "}
                when they watch the whole sea. But a cable missing from the map
                is invisible: the official EU route data does not include the
                Bornholm cable, so I took that route from OpenStreetMap.
              </p>
            )}
          </div>
        </section>

        <section className="ex-sec">
          <span className="ex-num">6.</span>
          <div>
            <h2>Limits</h2>
            <ul className="plain">
              <li>One testable incident is an anecdote, not an accuracy figure. I report it as one case.</li>
              <li>Every alert on an ordinary day is counted as false, though some may be real anchoring near a cable.</li>
              <li>Cable routes on public maps are approximate; a route that is a kilometre off can move a ship in or out of range.</li>
              <li>A ship that switches off its transponder disappears from this kind of system entirely.</li>
            </ul>
            <p>
              <Link href="/">Back to the replay and the full results</Link>
            </p>
          </div>
        </section>
        <PageNav current="/how-it-works/" />
      </main>
    </>
  );
}
