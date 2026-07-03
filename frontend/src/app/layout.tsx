import type { Metadata, Viewport } from "next";
import "@/styles/globals.css";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "军师团 - 虚拟历史顾问团",
  description: "与历史智者对话，汲取千年智慧",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="min-h-[100dvh] bg-mesh">
        <NavBar />
        <main className="pt-12 sm:pt-16 min-h-[100dvh]">{children}</main>
      </body>
    </html>
  );
}
