"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Shield, LogIn } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AdminLoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "登录失败");
      }

      const data = await res.json();
      if (!data.is_admin) {
        throw new Error("需要管理员权限");
      }

      localStorage.setItem("junshituan_token", data.access_token);
      router.push("/admin");
    } catch (err: any) {
      setError(err.message || "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-ink-950 px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-sm"
      >
        <div className="text-center mb-8">
          <motion.div
            animate={{ y: [0, -8, 0] }}
            transition={{ repeat: Infinity, duration: 3 }}
            className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-ancient-600/20 border border-ancient-500/30 mb-4"
          >
            <Shield size={28} className="text-ancient-400" />
          </motion.div>
          <h1 className="text-2xl font-display text-ancient-400">军师团管理</h1>
          <p className="text-sm text-ink-500 mt-1">管理员登录</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          {error && (
            <div className="bg-red-900/30 border border-red-700/50 text-red-400 text-sm rounded-xl px-4 py-3">
              {error}
            </div>
          )}

          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="用户名"
            className="w-full bg-ink-900/80 border border-ink-700/50 rounded-xl px-4 py-3 text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-ancient-600/50"
          />

          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="密码"
            className="w-full bg-ink-900/80 border border-ink-700/50 rounded-xl px-4 py-3 text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-ancient-600/50"
          />

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            type="submit"
            disabled={loading || !username || !password}
            className="w-full py-3 bg-gradient-to-r from-ancient-600 to-ancient-500 text-white rounded-xl font-bold flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {loading ? (
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 1 }}
              >
                <LogIn size={18} />
              </motion.div>
            ) : (
              <>
                <LogIn size={18} /> 登录
              </>
            )}
          </motion.button>
        </form>
      </motion.div>
    </div>
  );
}
