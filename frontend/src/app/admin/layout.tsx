"use client";

import { useState, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { BookOpen, LogOut, Shield, X, Loader2 } from "lucide-react";
import { motion } from "framer-motion";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [avatar, setAvatar] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [showProfile, setShowProfile] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem("junshituan_token");
    if (!t && pathname !== "/admin/login") {
      router.push("/admin/login");
    } else if (t) {
      setToken(t);
      try {
        const payload = JSON.parse(atob(t.split(".")[1]));
        setUsername(payload.username || payload.sub || "");
      } catch {}
      fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${t}` },
      })
        .then((r) => r.json())
        .then((d) => {
          if (d.avatar_url) setAvatar(d.avatar_url);
          if (d.display_name) setDisplayName(d.display_name);
        })
        .catch(() => {});
    }
  }, [pathname]);

  const handleLogout = () => {
    localStorage.removeItem("junshituan_token");
    router.push("/admin/login");
  };

  const handleAvatarFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        const MAX = 128;
        let w = img.width, h = img.height;
        if (w > h) { if (w > MAX) { h = h * MAX / w; w = MAX; } }
        else { if (h > MAX) { w = w * MAX / h; h = MAX; } }
        w = Math.round(w); h = Math.round(h);
        const canvas = document.createElement("canvas");
        canvas.width = w; canvas.height = h;
        const ctx = canvas.getContext("2d")!;
        ctx.drawImage(img, 0, 0, w, h);
        setAvatar(canvas.toDataURL("image/jpeg", 0.75));
      };
      img.src = ev.target?.result as string;
    };
    reader.readAsDataURL(file);
  };

  const handleSaveProfile = async () => {
    setSaving(true);
    try {
      await fetch(`${API_BASE}/api/auth/profile`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ avatar_url: avatar, display_name: displayName }),
      });
      setShowProfile(false);
    } catch {}
    setSaving(false);
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
              onClick={() => setShowProfile(true)}
              className="flex items-center gap-2 hover:opacity-80 transition-opacity"
            >
              {avatar ? (
                <img
                  src={avatar}
                  alt="avatar"
                  className="w-7 h-7 rounded-full object-cover border border-ink-700"
                />
              ) : (
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-ancient-600 to-ancient-800 flex items-center justify-center text-white text-xs font-bold border border-ink-700">
                  {(displayName || username)[0]?.toUpperCase() || "?"}
                </div>
              )}
              <span className="text-xs text-ink-400">{displayName || username}</span>
            </button>
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

      {/* ── Profile modal ── */}
      {showProfile && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={(e) => { if (e.target === e.currentTarget) setShowProfile(false); }}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="bg-ink-900 border border-ink-700 rounded-xl p-6 w-full max-w-sm mx-4"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-ink-100">编辑资料</h3>
              <button onClick={() => setShowProfile(false)} className="text-ink-500 hover:text-ink-300">
                <X size={20} />
              </button>
            </div>

            <div className="flex flex-col items-center gap-4 mb-4">
              <label className="cursor-pointer group">
                {avatar ? (
                  <img
                    src={avatar}
                    alt="avatar"
                    className="w-20 h-20 rounded-full object-cover border-2 border-ink-700 group-hover:border-ancient-500 transition-colors"
                  />
                ) : (
                  <div className="w-20 h-20 rounded-full bg-gradient-to-br from-ancient-600 to-ancient-800 flex items-center justify-center text-white text-2xl font-bold border-2 border-ink-700 group-hover:border-ancient-500 transition-colors">
                    {(displayName || username)[0]?.toUpperCase() || "?"}
                  </div>
                )}
                <input type="file" accept="image/*" onChange={handleAvatarFile} className="hidden" />
                <p className="text-xs text-ink-500 mt-2 text-center">点击更换头像（自动压缩）</p>
              </label>
            </div>

            <div className="mb-4">
              <label className="block text-xs text-ink-400 mb-1">显示名称</label>
              <input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 focus:outline-none focus:border-ancient-600"
              />
            </div>

            <button
              onClick={handleSaveProfile}
              disabled={saving}
              className="w-full py-2.5 bg-ancient-700 hover:bg-ancient-600 disabled:opacity-50 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : null}
              保存
            </button>
          </motion.div>
        </div>
      )}
    </div>
  );
}
