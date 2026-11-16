import { AUTHOR } from "@/lib/site";

export default function Footer() {
  return (
    <footer className="wrap">
      <div className="footer">
      <p className="credit">
        Built by{" "}
        <a href={AUTHOR.url} rel="author">
          {AUTHOR.name}
        </a>
        . More of my work is at{" "}
        <a href={AUTHOR.url}>omerfaizan.com</a>
        {AUTHOR.email && (
          <>
            , or write to me at{" "}
            <a href={`mailto:${AUTHOR.email}`}>{AUTHOR.email}</a>
          </>
        )}
        .
      </p>
      <p className="sources">
        Ship positions: Danish Maritime Authority AIS archive. Cable routes:
        EMODnet Human Activities (CC BY 4.0, originator Cogea Srl) and
        OpenStreetMap contributors (ODbL). Land: Natural Earth. Incident dates
        and vessel names come from public reporting, cited row by row in the
        repository. A flag on this site is a lead for a person to check, not an
        accusation.
      </p>
      </div>
    </footer>
  );
}
