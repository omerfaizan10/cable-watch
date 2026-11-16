import type { Metadata, Viewport } from "next";
import "@fontsource/source-serif-4/400.css";
import "@fontsource/source-serif-4/600.css";
import "@fontsource/public-sans/400.css";
import "@fontsource/public-sans/600.css";
import "@fontsource/public-sans/700.css";
import "./globals.css";
import Footer from "@/components/Footer";
import { AUTHOR, SITE_DESCRIPTION, SITE_NAME, SITE_TITLE, SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: SITE_TITLE, template: `%s | ${SITE_NAME}` },
  description: SITE_DESCRIPTION,
  authors: [{ name: AUTHOR.name, url: AUTHOR.url }],
  creator: AUTHOR.name,
  keywords: [
    "AIS", "subsea cables", "Baltic Sea", "anchor drag", "streaming pipeline",
    "data engineering", "Kafka", "Redpanda", "DuckDB", "maritime",
  ],
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: SITE_NAME,
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
  },
  twitter: { card: "summary_large_image", title: SITE_TITLE, description: SITE_DESCRIPTION },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = { themeColor: "#fbfaf7", width: "device-width", initialScale: 1 };

const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebSite",
      name: SITE_NAME,
      url: SITE_URL,
      description: SITE_DESCRIPTION,
      author: { "@type": "Person", name: AUTHOR.name, url: AUTHOR.url },
    },
    {
      "@type": "Dataset",
      name: "Cable Watch backtest of Baltic cable incidents",
      description:
        "Danish Maritime Authority AIS replayed through a streaming anchor-drag detector, scored against publicly reported Baltic cable and pipeline incidents.",
      url: SITE_URL,
      creator: { "@type": "Person", name: AUTHOR.name, url: AUTHOR.url },
      isBasedOn: [
        "https://www.dma.dk/safety-at-sea/navigational-information/ais-data",
        "https://emodnet.ec.europa.eu/en/human-activities",
        "https://www.openstreetmap.org/copyright",
      ],
      spatialCoverage: "Western Baltic Sea",
    },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        {children}
        <Footer />
      </body>
    </html>
  );
}
