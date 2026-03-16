import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Identity Studio",
  description: "Identity Studio MVP"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
