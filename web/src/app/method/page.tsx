import type { Metadata } from "next";
import Method from "@/components/Method";
import PageHead from "@/components/PageHead";
import PageNav from "@/components/PageNav";
import { load } from "@/lib/data";

export const metadata: Metadata = {
  title: "Method",
  description:
    "Every threshold in the Cable Watch detector, where it came from, the data sources and licences, and the limits of the study.",
  alternates: { canonical: "/method/" },
};

export default function MethodPage() {
  const score = load("scorecard.json");
  return (
    <main className="wrap report">
      <PageHead kicker="Section 6" title="Method">
        The rules, their thresholds and the data behind them. Nothing here is
        typed by hand: the numbers are read from the same config file the
        processor uses.
      </PageHead>
      <Method score={score} />
      <section className="section">
        <h2>Limits</h2>
        <ul className="plain-list">
          <li>One testable incident is a case study, not an accuracy figure.</li>
          <li>
            Danish receivers do not reach the Gulf of Finland, where several of
            the recent breaks happened, and the public daily files stop in
            February 2025.
          </li>
          <li>
            EMODnet&apos;s Baltic coverage is mostly German and Norwegian data, so
            many Danish and Swedish routes are missing; I add routes the
            incidents depend on from OpenStreetMap.
          </li>
          <li>
            Every alert on an ordinary day is counted as false, though some may
            be real anchoring near a cable.
          </li>
          <li>
            The free live feed carries about a thirteenth of the archive&apos;s
            report rate, too sparse for the rules in live use.
          </li>
          <li>A ship with its transponder switched off is invisible to any AIS system.</li>
        </ul>
      </section>
      <PageNav current="/method/" />
    </main>
  );
}
