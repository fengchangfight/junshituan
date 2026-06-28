"use client";

import { useState, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { BookOpen, LogOut, Shield } from "lucide-react";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    const t = localStorage.getItem("junshituan_token");
    if (!t && pathname !== "/admin/login") {
      router.push("/admin/login");
    }
    setToken(t);
  }, [pathname]);

  const handleLogout = () => {
    localStorage.removeItem("junshituan_token");
    router.push("/admin/login");
  };

  if (pathname === "/admin/login") {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-ink-950">
      <header className="bg-ink-900/95 border-b border-ink-800/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/admin" className="flex items-center gap-2">
              <Shield size={20} className="text-ancient-400" />
              <span className="font-bold text-ancient-400 font-display">军师团管理</span>
            </Link>
            <Link
              href="/admin/advisors"
              className={`text-sm flex items-center gap-1.5 ${
                pathname.startsWith("/admin/advisors")
                  ? "text-ancient-400"
                  : "text-ink-400 hover:text-ink-200"
              }`}
            >
              <BookOpen size={16} />
              知识库管理
            </Link>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/" className="text-xs text-ink-500 hover:text-ink-300">
              返回前台
            </Link>
            <button
              onClick={handleLogout}
              className="text-xs text-ink-400 hover:text-red-400 flex items-center gap-1"
            >
              <LogOut size={14} /> 退出
            </button>
          </div>
        </div>
      </header>
      <main className="p-4 sm:p-6">{children}</main>
    </div>
  );
}
