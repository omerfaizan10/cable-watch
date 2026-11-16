"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AUTHOR } from "@/lib/site";
import { CHAPTERS } from "@/components/PageNav";

const NAV = CHAPTERS.map((c) => ({ href: c.href, label: c.short }));

export default function Masthead() {
  const path = usePathname() || "/";
  const active = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, ""));
  return (
    <header className="masthead">
      <div className="wrap mast-inner">
      <Link href="/" className="wordmark" aria-label="Cable Watch, home">
        <svg width="22" height="22" viewBox="0 0 64 64" aria-hidden="true">
          <path d="M4 44 C 20 36, 44 52, 60 44" fill="none" stroke="var(--cable-power)" strokeWidth="6" strokeLinecap="round" />
          <path d="M32 6 L 46 40 L 32 31 L 18 40 Z" fill="var(--alert)" stroke="var(--bg)" strokeWidth="3" strokeLinejoin="round" />
        </svg>
        Cable Watch
      </Link>
      <nav className="nav" aria-label="Sections">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} aria-current={active(n.href) ? "page" : undefined}>
            {n.label}
          </Link>
        ))}
      </nav>
      <div className="mast-right">
        <a href={AUTHOR.url} className="byline" rel="author">
          Built by <span>{AUTHOR.name}</span>
        </a>
        {AUTHOR.email && (
          <a href={`mailto:${AUTHOR.email}`} className="contact">
            Contact me
          </a>
        )}
      </div>
      </div>
    </header>
  );
}
