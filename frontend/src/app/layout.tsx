import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "StackForge",
  description: "Self-hosted AI app builder for trusted internal teams",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
