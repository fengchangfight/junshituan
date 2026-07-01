import type { Metadata, Viewport } from "next";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "军师团 - 虚拟历史顾问团",
  description: "与历史智者对话，汲取千年智慧",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="min-h-[100dvh] bg-mesh">
        <header className="fixed top-0 left-0 right-0 z-50 bg-ink-950/80 backdrop-blur-sm border-b border-ink-800/50">
          <div className="mx-auto px-4 sm:px-6 h-12 sm:h-16 flex items-center justify-between max-w-7xl">
            <a href="/" className="flex items-center gap-2 sm:gap-3">
              <span className="text-lg sm:text-2xl">⚔️</span>
              <h1 className="text-base sm:text-xl font-display text-ancient-500 tracking-wider">
                军师团
              </h1>
            </a>
            <nav className="flex items-center gap-4 sm:gap-6 text-xs sm:text-sm text-ink-300">
              <a href="/" className="hover:text-ancient-400 transition-colors">
                军师大厅
              </a>
            </nav>
          </div>
        </header>
        <main className="pt-12 sm:pt-16 min-h-[100dvh]">{children}</main>
      </body>
    </html>
  );
}
