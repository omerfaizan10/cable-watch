import Link from "next/link";

// The report's chapters, in reading order. Used by the masthead, the contents list and
// the previous/next links at the foot of each page.
export const CHAPTERS = [
  { href: "/", label: "Report", short: "Report", blurb: "Summary, key findings and the contents of this report." },
  { href: "/replay/", label: "Replay", short: "Replay", blurb: "Watch the archive play back with every ship, cable and alert on the chart." },
  { href: "/incidents/", label: "Incidents tested", short: "Incidents", blurb: "Every publicly reported Baltic cable break, what the data can test, and what the detector did." },
  { href: "/false-alerts/", label: "False alerts", short: "False alerts", blurb: "How many alerts the detector raises on ordinary days, and which rules raise them." },
  { href: "/pipeline/", label: "Pipeline and correctness", short: "Pipeline", blurb: "The streaming architecture, the data quality ledger, and the checks that the answer does not depend on timing." },
  { href: "/method/", label: "Method", short: "Method", blurb: "Every threshold, data source and limit, read from the code." },
  { href: "/how-it-works/", label: "How it works", short: "How it works", blurb: "The whole project explained without jargon." },
];

export default function PageNav({ current }: { current: string }) {
  const i = CHAPTERS.findIndex((c) => c.href === current);
  const prev = i > 0 ? CHAPTERS[i - 1] : null;
  const next = i >= 0 && i < CHAPTERS.length - 1 ? CHAPTERS[i + 1] : null;
  return (
    <nav className="page-nav" aria-label="Previous and next page">
      {prev ? (
        <Link href={prev.href} className="prev">
          <span>Previous</span>
          {prev.label}
        </Link>
      ) : (
        <span />
      )}
      {next && (
        <Link href={next.href} className="next">
          <span>Next</span>
          {next.label}
        </Link>
      )}
    </nav>
  );
}
