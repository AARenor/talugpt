import type { Metadata, Viewport } from "next";
import { Fraunces, Alegreya_Sans } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin", "latin-ext"],
  axes: ["opsz", "SOFT", "WONK"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-display",
});

const alegreyaSans = Alegreya_Sans({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "700", "800"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-body",
});

export const metadata: Metadata = {
  title: "TaluGPT — Eesti Talukaart",
  description:
    "Eesti talud, turud, tootjad, poed ja toidusündmused — andmed PTA mahepõllumajanduse registrist ja avalikest allikatest.",
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
    shortcut: [{ url: "/favicon.svg", type: "image/svg+xml" }],
    apple: [{ url: "/favicon.svg", type: "image/svg+xml" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: "#1f4424",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="et" className={`${fraunces.variable} ${alegreyaSans.variable}`}>
      <body>{children}</body>
    </html>
  );
}
