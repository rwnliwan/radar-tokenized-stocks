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
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        {children}
      </body>
    </html>
  );
}
