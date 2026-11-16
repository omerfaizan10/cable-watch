// Public site identity, used by metadata, the sitemap, JSON-LD and the footer.
export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://cable-watch.vercel.app"
).replace(/\/$/, "");
export const SITE_NAME = "Cable Watch";
export const SITE_TITLE = "Cable Watch: ships over Baltic subsea cables";
export const SITE_DESCRIPTION =
  "A streaming pipeline that replays Danish Maritime Authority ship positions, flags behavior consistent with anchor drag over Baltic subsea cables, and grades itself against publicly reported cable and pipeline incidents.";
export const AUTHOR = {
  name: "Omer Faizan",
  url: "https://omerfaizan.com",
  // Set in web/.env.production so the address lives in one place.
  email: process.env.NEXT_PUBLIC_CONTACT_EMAIL || "",
};
