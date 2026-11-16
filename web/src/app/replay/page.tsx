import type { Metadata } from "next";
import ChartView from "@/components/ChartView";
import PageHead from "@/components/PageHead";
import PageNav from "@/components/PageNav";
import { load } from "@/lib/data";
import type { ReplayMeta } from "@/lib/types";

export const metadata: Metadata = {
  title: "Replay",
  description:
    "Play back the Danish AIS archive around the 2022 Bornholm cable failure, Yi Peng 3 in 2024 and an ordinary day, with every ship, cable route and detector alert on the chart.",
  alternates: { canonical: "/replay/" },
};

export default function ReplayPage() {
  const score = load("scorecard.json");
  const replays: ReplayMeta[] = score?.replays ?? [];
  return (
    <main className="wrap report">
      <PageHead kicker="Section 2" title="Replay">
        Pick a window and press play. Every ship is drawn where the archive put
        it at that moment, with the cable routes the detector watches. Ships turn
        red when a rule flags them, and the panel on the right says why.
      </PageHead>
      <section className="section" id="replay">
        <h2>The chart</h2>
        {replays.length ? (
          <figure className="fig">
            <ChartView replays={replays} />
            <figcaption>
              Replay of the Danish Maritime Authority archive in event time.
              Cable routes from EMODnet and OpenStreetMap; shaded cells show where
              Danish receivers actually picked ships up. A flag is a lead for a
              person to check, not an accusation.
            </figcaption>
          </figure>
        ) : (
          <p>No replay files were found. Run make eval in the repository to build them.</p>
        )}
      </section>
      <section className="section">
        <h2>What to look for</h2>
        <ul className="plain-list">
          <li>
            <b>Samus Swan, 26 Feb 2022.</b> Follow the ship heading south-west
            past Bornholm. It crosses the Bornholm power cable at 05:20 UTC at a
            steady 9.6 knots, three minutes after the reported failure. Nothing
            about its movement looks unusual at that moment, which is why the
            behavior rules stay quiet; it only stops two hours later.
          </li>
          <li>
            <b>Yi Peng 3, 18 Nov 2024.</b> The ship enters Danish receiver range
            only after the C-Lion1 break further east, so this window shows its
            track, not the damage.
          </li>
          <li>
            <b>Ordinary traffic, 12 Feb 2025.</b> A full day in the Arkona Basin
            with no alerts near the cables in view: what normal looks like.
          </li>
        </ul>
      </section>
      <PageNav current="/replay/" />
    </main>
  );
}
