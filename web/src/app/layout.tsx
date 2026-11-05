import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "EXIT RADAR — Tokenized-stock deviation & redemption radar",
  description:
    "Deviation & redemption radar for tokenized stocks — free, public, human-checked methodology.",
  authors: [
    { name: "Septian Panjaya", url: "https://www.linkedin.com/in/septian-panjaya" },
  ],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

/* No-flash theme script: runs before body paints, so a stored "light"
   choice never flashes dark first. Default (no stored value) = dark. */
const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem('exit-radar-theme');document.documentElement.setAttribute('data-theme',t==='light'?'light':'dark');}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body>
        <link rel="preconnect" href="https://api.omdanny.site" crossOrigin="anonymous" />
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        {/* Schema.org Person — Septian Panjaya */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "Person",
              name: "Septian Panjaya",
              url: "https://www.linkedin.com/in/septian-panjaya",
              jobTitle: "Finance Risk Analytics",
              knowsAbout: ["Credit Risk", "Fraud/AML Analytics", "Financial Modeling", "Financial Statement Analysis"],
              sameAs: [
                "https://www.linkedin.com/in/septian-panjaya",
                "https://github.com/rwnliwan",
                "https://fmva-sprint.pages.dev/",
                "https://fsa-lab.pages.dev/",
                "https://credit-desk-afy.pages.dev/",
                "https://investment-desk.pages.dev/",
                "https://simulator-fmva.pages.dev/",
                "https://learn-platform-cyo.pages.dev/v2",
                "https://radar.omdanny.site/",
              ],
            }),
          }}
        />

        <main>{children}</main>
      </body>
    </html>
  );
}
