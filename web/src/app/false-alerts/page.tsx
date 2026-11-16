import type { Metadata } from "next";
import FalseAlerts from "@/components/FalseAlerts";
import PageHead from "@/components/PageHead";
import PageNav from "@/components/PageNav";
import { load } from "@/lib/data";

export const metadata: Metadata = {
  title: "False alerts",
  description:
    "How many alerts the Cable Watch detector raises on ordinary days with no reported incident, by rule, with and without the cable map.",
  alternates: { canonical: "/false-alerts/" },
};

export default function FalseAlertsPage() {
  const score = load("scorecard.json");
  return (
    <main className="wrap report">
      <PageHead kicker="Section 4" title="False alerts">
        A detector that never stays quiet is useless to the person who has to
        check every alert. This page counts alerts on ordinary days, when no
        cable broke, and shows how much the cable map cuts them.
      </PageHead>
      <FalseAlerts score={score} />
      <PageNav current="/false-alerts/" />
    </main>
  );
}
