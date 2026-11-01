import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LiteLink — Links, checked",
  description: "Short links checked for phishing before they go live."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
