import type { Metadata } from "next";
import Architecture from "@/components/Architecture";
import DataQuality from "@/components/DataQuality";
import PageHead from "@/components/PageHead";
import PageNav from "@/components/PageNav";
import { load } from "@/lib/data";

export const metadata: Metadata = {
  title: "Pipeline and correctness",
  description:
    "Cable Watch's streaming architecture, the per-run data quality ledger, and the ordering, late-data, Redpanda and live-feed checks.",
  alternates: { canonical: "/pipeline/" },
};

export default function PipelinePage() {
  const score = load("scorecard.json");
  return (
    <main className="wrap report">
      <PageHead kicker="Section 5" title="Pipeline and correctness">
        Most of the engineering is making sure a messy, out-of-order feed gives
        one answer. Every run ends with a ledger that has to balance, and the
        same day replayed in a different order, through Kafka, or from the live
        feed goes through exactly the same code.
      </PageHead>
      <Architecture />
      <DataQuality score={score} />
      <PageNav current="/pipeline/" />
    </main>
  );
}
