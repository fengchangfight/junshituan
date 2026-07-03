"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { getToken, removeToken, getUserInfo } from "@/lib/api";

export default function NavBar() {
  const [username, setUsername] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    const info = getUserInfo();
    if (info) {
      setUsername(info.username);
      setIsAdmin(info.isAdmin);
    }
  }, []);

  const handleLogout = () => {
    removeToken();
    setUsername("");
    window.location.href = "/";
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-ink-950/80 backdrop-blur-sm border-b border-ink-800/50">
      <div className="mx-auto px-4 sm:px-6 h-12 sm:h-16 flex items-center justify-between max-w-7xl">
        <Link href="/" className="flex items-center gap-2 sm:gap-3">
          <span className="text-lg sm:text-2xl">&#9876;&#65039;</span>
          <h1 className="text-base sm:text-xl font-display text-ancient-500 tracking-wider">
            军师团
          </h1>
        </Link>
        <nav className="flex items-center gap-3 sm:gap-5 text-xs sm:text-sm text-ink-300">
          <Link href="/" className="hover:text-ancient-400 transition-colors">
            军师大厅
          </Link>
          {username ? (
            <>
              <Link href="/sessions" className="hover:text-ancient-400 transition-colors">
                我的议事
              </Link>
              <Link href="/admin" className="text-amber-400 hover:text-amber-300 transition-colors">
                管理军师
              </Link>
              <span className="text-ink-500">{username}</span>
              <button
                onClick={handleLogout}
                className="hover:text-red-400 transition-colors"
              >
                退出
              </button>
            </>
          ) : (
            <Link href="/login" className="text-ancient-400 hover:text-ancient-300 transition-colors">
              登录
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
