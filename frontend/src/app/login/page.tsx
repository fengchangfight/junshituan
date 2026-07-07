"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { login, sendCode, loginPhone } from "@/lib/api";
import { ArrowRight, Loader2, User, Smartphone } from "lucide-react";

type Mode = "phone" | "password";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [error, setError] = useState("");
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  const handleSendCode = async () => {
    const p = phone.trim();
    if (!p || p.length !== 11) { setError("请输入正确的11位手机号"); return; }
    setError(""); setSending(true);
    try {
      await sendCode(p);
      setCountdown(60);
      codeRef.current?.focus();
    } catch (e: any) {
      setError(e.message);
    } finally { setSending(false); }
  };

  const handlePhoneLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    const p = phone.trim(); const c = code.trim();
    if (!p || !c) { setError("请输入手机号和验证码"); return; }
    setError(""); setLoading(true);
    try {
      await loginPhone(p, c);
      router.push("/");
      window.location.href = "/";
    } catch (e: any) {
      setError(e.message);
    } finally { setLoading(false); }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const u = phone.trim();
    if (!u || !password) { setError("请输入账号和密码"); return; }
    setError(""); setLoading(true);
    try {
      await login(u, password);
      router.push("/");
      window.location.href = "/";
    } catch (e: any) {
      setError(e.message);
    } finally { setLoading(false); }
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
          <p className="text-sm text-ink-500 mt-1">验证码登录，秒进议事厅</p>
        </div>

        <div className="bg-ink-900/70 border border-ink-800/50 rounded-2xl p-6">
          <div className="flex mb-6 bg-ink-800/50 rounded-lg p-1">
            <button
              onClick={() => { setMode("phone"); setError(""); }}
              className={`flex-1 py-2 text-sm rounded-md transition-colors ${
                mode === "phone" ? "bg-ink-700 text-ink-100" : "text-ink-400"
              }`}
            >
              <Smartphone size={14} className="inline mr-1" />验证码登录
            </button>
            <button
              onClick={() => { setMode("password"); setError(""); }}
              className={`flex-1 py-2 text-sm rounded-md transition-colors ${
                mode === "password" ? "bg-ink-700 text-ink-100" : "text-ink-400"
              }`}
            >
              <User size={14} className="inline mr-1" />密码登录
            </button>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-900/30 border border-red-800/50 rounded-lg text-red-400 text-xs">
              {error}
            </div>
          )}

          {mode === "phone" ? (
            <form onSubmit={handlePhoneLogin} className="space-y-3">
              <div>
                <label className="text-xs text-ink-400 mb-1 block">手机号</label>
                <input
                  type="tel" maxLength={11}
                  value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
                  placeholder="输入手机号"
                  className="w-full bg-ink-800 border border-ink-700 rounded-xl px-3 py-2.5 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
                />
              </div>
              <div className="flex gap-2">
                <input
                  ref={codeRef} type="text" maxLength={6} inputMode="numeric"
                  value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="验证码"
                  className="flex-1 bg-ink-800 border border-ink-700 rounded-xl px-3 py-2.5 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
                />
                <button
                  type="button" onClick={handleSendCode}
                  disabled={sending || countdown > 0 || phone.length !== 11}
                  className="shrink-0 px-4 py-2.5 bg-blue-600/20 border border-blue-600/40 text-blue-400 text-sm rounded-xl hover:bg-blue-600/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {sending ? <Loader2 size={14} className="animate-spin" /> : countdown > 0 ? `${countdown}s` : "获取验证码"}
                </button>
              </div>
              <motion.button
                whileTap={{ scale: 0.98 }} type="submit"
                disabled={loading || phone.length !== 11 || code.length < 4}
                className="w-full py-2.5 bg-gradient-to-r from-ancient-600 to-ancient-500 text-white rounded-xl font-medium text-sm disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
                登录 / 注册
              </motion.button>
              <p className="text-[10px] text-ink-600 text-center">未注册手机号将自动创建账号</p>
            </form>
          ) : (
            <form onSubmit={handlePasswordSubmit} className="space-y-3">
              <div>
                <label className="text-xs text-ink-400 mb-1 block">账号</label>
                <input
                  type="text" value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="用户名或手机号"
                  className="w-full bg-ink-800 border border-ink-700 rounded-xl px-3 py-2.5 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
                />
              </div>
              <div>
                <label className="text-xs text-ink-400 mb-1 block">密码</label>
                <input
                  type="password" value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="输入密码"
                  className="w-full bg-ink-800 border border-ink-700 rounded-xl px-3 py-2.5 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
                />
              </div>
              <motion.button
                whileTap={{ scale: 0.98 }} type="submit"
                disabled={loading || !phone.trim() || !password}
                className="w-full py-2.5 bg-gradient-to-r from-ancient-600 to-ancient-500 text-white rounded-xl font-medium text-sm disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
                登录
              </motion.button>
            </form>
          )}

        </div>
      </motion.div>
    </div>
  );
}
