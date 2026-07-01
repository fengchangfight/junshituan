"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { login, register } from "@/lib/api";
import { ArrowRight, Loader2, User } from "lucide-react";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const u = account.trim();
    if (!u) return;
    setError("");
    setLoading(true);

    try {
      if (mode === "register") {
        const pwd = password || u;
        await register(u, pwd, u);
      } else {
        await login(u, password);
      }
      router.push("/");
      window.location.href = "/";  // Force NavBar refresh
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const quickDemoLogin = async (demoUser: string) => {
    setError("");
    setLoading(true);
    try {
      await login(demoUser, "demo123");
      router.push("/");
      window.location.href = "/";  // Force NavBar refresh
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-ink-950">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-sm"
      >
        <div className="text-center mb-8">
          <span className="text-3xl">&#9876;&#65039;</span>
          <h1 className="text-2xl font-display text-ancient-500 mt-2">军师团</h1>
          <p className="text-sm text-ink-500 mt-1">与历史智者对话，汲取千年智慧</p>
        </div>

        <div className="bg-ink-900/70 border border-ink-800/50 rounded-2xl p-6">
          <div className="flex mb-6 bg-ink-800/50 rounded-lg p-1">
            <button
              onClick={() => { setMode("login"); setError(""); }}
              className={`flex-1 py-2 text-sm rounded-md transition-colors ${
                mode === "login" ? "bg-ink-700 text-ink-100" : "text-ink-400"
              }`}
            >
              登录
            </button>
            <button
              onClick={() => { setMode("register"); setError(""); }}
              className={`flex-1 py-2 text-sm rounded-md transition-colors ${
                mode === "register" ? "bg-ink-700 text-ink-100" : "text-ink-400"
              }`}
            >
              注册
            </button>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-900/30 border border-red-800/50 rounded-lg text-red-400 text-xs">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="text-xs text-ink-400 mb-1 block">
                {mode === "register" ? "手机号或用户名（快速注册）" : "手机号或用户名"}
              </label>
              <div className="relative">
                <User size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-500" />
                <input
                  type={mode === "register" ? "tel" : "text"}
                  value={account}
                  onChange={(e) => setAccount(e.target.value)}
                  placeholder={mode === "register" ? "输入手机号快速注册" : "输入用户名或手机号"}
                  className="w-full bg-ink-800 border border-ink-700 rounded-xl pl-9 pr-3 py-2.5 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
                />
              </div>
            </div>

            <div>
              <label className="text-xs text-ink-400 mb-1 block">
                密码{mode === "register" && "（留空则与账号相同）"}
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === "register" ? "设置密码，留空则与账号相同" : "输入密码"}
                className="w-full bg-ink-800 border border-ink-700 rounded-xl px-3 py-2.5 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
              />
            </div>

            <motion.button
              whileTap={{ scale: 0.98 }}
              type="submit"
              disabled={loading || !account.trim()}
              className="w-full py-2.5 bg-gradient-to-r from-ancient-600 to-ancient-500 text-white rounded-xl font-medium text-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
              {mode === "register" ? "注册并登录" : "登录"}
            </motion.button>
          </form>

          <div className="mt-5 pt-4 border-t border-ink-800/50">
            <p className="text-xs text-ink-500 mb-2 text-center">体验账号</p>
            <div className="flex gap-2">
              {["libai", "caocao", "songhuizong"].map((u) => (
                <button
                  key={u}
                  onClick={() => quickDemoLogin(u)}
                  disabled={loading}
                  className="flex-1 py-1.5 bg-ink-800 hover:bg-ink-700 text-ink-300 text-xs rounded-lg transition-colors disabled:opacity-50"
                >
                  {u}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-ink-600 text-center mt-2">密码: demo123</p>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
