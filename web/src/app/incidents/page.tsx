import type { Metadata } from "next";
import Scorecard from "@/components/Scorecard";
import OutageLookup from "@/components/OutageLookup";
import PageHead from "@/components/PageHead";
import PageNav from "@/components/PageNav";
import { load } from "@/lib/data";

export const metadata: Metadata = {
  title: "Incidents tested",
  description:
    "Every publicly reported Baltic cable and pipeline break since 2022, whether the Danish AIS archive can test it, and what the detector did.",
  alternates: { canonical: "/incidents/" },
};

export default function IncidentsPage() {
  const score = load("scorecard.json");
  const coverage = load("coverage.json");
  return (
    <main className="wrap report">
      <PageHead kicker="Section 3" title="Incidents tested">
        I collected every publicly reported Baltic cable or pipeline break since
        2022 with the ship that was named and the time of the break. For each one
        the backtest decides from the data whether it can be tested fairly, then
        reports what the detector did. Open any incident for its sources and the
        full record.
      </PageHead>
      <Scorecard score={score} coverage={coverage} />
      <OutageLookup score={score} />
      <PageNav current="/incidents/" />
    </main>
  );
}
