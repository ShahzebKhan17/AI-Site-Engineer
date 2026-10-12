import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Site Engineer Copilot",
  description: "Evidence-led structural drawing assistance for civil site engineers.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
