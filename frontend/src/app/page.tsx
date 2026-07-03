"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Advisor } from "@/lib/types";
import { fetchAdvisors, createCouncil, getToken, getUserInfo } from "@/lib/api";
import AdvisorCard from "@/components/AdvisorCard/AdvisorCard";
import { Plus, Sparkles, Zap, Loader2, X } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const CATEGORIES = ["军事家", "哲学家", "政治家", "文学家", "科学家", "企业家", "其他"];

const CATEGORY_MAP: Record<string, { label: string; icon: string }> = {
  军事家: { label: "军事家", icon: "⚔️" },
  哲学家: { label: "哲学家", icon: "☯️" },
  政治家: { label: "政治家", icon: "👑" },
  佛学大师: { label: "佛学大师", icon: "🪷" },
  企业家: { label: "企业家", icon: "💡" },
};

const STEPS = [
  { num: 1, label: "选择军师", desc: "点击头像选择 1-12 位" },
  { num: 2, label: "创建议事厅", desc: "确认后自动创建会话" },
  { num: 3, label: "开始提问", desc: "与军师团对话" },
];

export default function HomePage() {
  const router = useRouter();
  const [advisors, setAdvisors] = useState<Advisor[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeCategory, setActiveCategory] = useState<string>("全部");
  const [loading, setLoading] = useState(false);
  const [showNameModal, setShowNameModal] = useState(false);
  const [customTitle, setCustomTitle] = useState("");

  // Create advisor states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createMode, setCreateMode] = useState<"smart" | "manual" | null>(null);
  const [smartName, setSmartName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [createForm, setCreateForm] = useState({
    name: "", title: "", category: "其他", era: "", avatar: "", short_bio: "", style: "",
  });
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    fetchAdvisors()
      .then(setAdvisors)
      .catch(() => {
        setAdvisors([
          {
            id: "zhuge-liang", name: "诸葛亮", title: "军事家·政治家",
            category: "军事家", era: "三国", avatar: "/avatars/zhuge-liang.png",
            shortBio: "字孔明，号卧龙，三国时期蜀汉丞相。", style: "谨慎周密，以史为鉴",
          },
        ]);
      });
    setIsLoggedIn(!!getToken());
  }, []);

  const handleCreateClick = () => {
    if (!getToken()) { router.push("/login"); return; }
    setShowCreateModal(true);
    setCreateMode(null);
    setCreateError("");
  };

  const handleSmartCreate = async () => {
    if (!smartName.trim()) { setCreateError("请输入军师名称"); return; }
    setCreating(true); setCreateError("");
    const token = getToken();
    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors/smart-create`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: smartName.trim() }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "创建失败"); }
      setShowCreateModal(false); setSmartName("");
      fetchAdvisors().then(setAdvisors);
    } catch (e: any) { setCreateError(e.message); }
    finally { setCreating(false); }
  };

  const handleManualCreate = async () => {
    if (!createForm.name || !createForm.title) { setCreateError("名称、称号为必填项"); return; }
    setCreating(true); setCreateError("");
    const token = getToken();
    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(createForm),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "创建失败"); }
      setShowCreateModal(false);
      setCreateForm({ name: "", title: "", category: "其他", era: "", avatar: "", short_bio: "", style: "" });
      fetchAdvisors().then(setAdvisors);
    } catch (e: any) { setCreateError(e.message); }
    finally { setCreating(false); }
  };

  const categories = ["全部", ...Array.from(new Set(advisors.map((a) => a.category)))];
  const filtered = activeCategory === "全部"
    ? advisors
    : advisors.filter((a) => a.category === activeCategory);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < 12) next.add(id);
      return next;
    });
  };

  const handleConsult = () => {
    if (selected.size === 0) return;
    if (!getToken()) { router.push("/login"); return; }
    const ids = Array.from(selected);
    const names = ids.map((id) => advisors.find((a) => a.id === id)?.name || id);
    setCustomTitle(names.join("、") + "的议事厅");
    setShowNameModal(true);
  };

  const handleConfirmCreate = async () => {
    if (selected.size === 0) return;
    setShowNameModal(false);
    setLoading(true);
    try {
      const ids = Array.from(selected);
      const title = customTitle.trim() || ids.map((id) => advisors.find((a) => a.id === id)?.name || id).join("、") + "的议事厅";
      const council = await createCouncil(ids, title);
      router.push(`/council?id=${council.id}&advisors=${ids.join(",")}&title=${encodeURIComponent(title)}`);
    } catch {
      setLoading(false);
      router.push("/login");
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-3 sm:px-6 py-6 sm:py-10 pb-28">
      {/* ── Header: clear CTA ─────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-8 sm:mb-10"
      >
        <h1 className="text-2xl sm:text-3xl font-display text-ancient-400 tracking-wider mb-3">
          ⚔️ 创建议事厅
        </h1>
        <p className="text-sm text-ink-400 max-w-lg mx-auto">
          召集 1-12 位历史智者组成专属顾问团，向他们请教任何问题
        </p>
      </motion.div>

      {/* ── Steps indicator ───────────────────────────────────────── */}
      <div className="flex justify-center gap-2 sm:gap-4 mb-8">
        {STEPS.map((s, i) => (
          <div key={s.num} className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
              i === 0 ? "bg-ancient-600 text-white" : "bg-ink-800 text-ink-500"
            }`}>
              {s.num}
            </div>
            <div className="hidden sm:block text-left">
              <p className={`text-xs font-medium ${i === 0 ? "text-ink-200" : "text-ink-500"}`}>
                {s.label}
              </p>
              <p className="text-[10px] text-ink-600">{s.desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* ── Category filters ──────────────────────────────────────── */}
      <div className="flex justify-center gap-1.5 sm:gap-2 mb-6 flex-wrap">
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setActiveCategory(cat)}
            className={`px-3 sm:px-4 py-1.5 rounded-full text-xs sm:text-sm transition-all ${
              activeCategory === cat
                ? "bg-ancient-600 text-white shadow-md"
                : "bg-ink-900/50 text-ink-400 hover:text-ink-200 border border-ink-800/30"
            }`}
          >
            {CATEGORY_MAP[cat]?.icon} {CATEGORY_MAP[cat]?.label || cat}
          </button>
        ))}
      </div>

      {/* ── Selected count hint ───────────────────────────────────── */}
      <div className="text-center mb-4">
        {selected.size === 0 ? (
          <p className="text-xs text-ink-500">点击军师头像开始选择</p>
        ) : (
          <p className="text-xs text-ancient-400">
            已选 <span className="font-bold">{selected.size}</span>/12 位 · 点击下方按钮开始
          </p>
        )}
      </div>

      {/* ── Advisor grid ──────────────────────────────────────────── */}
      <motion.div layout className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 sm:gap-5">
        <AnimatePresence mode="popLayout">
          {/* ── 创建军师 button as first grid item ── */}
          <motion.button
            key="create-advisor"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            whileHover={{ scale: 1.03, y: -4 }}
            whileTap={{ scale: 0.97 }}
            onClick={handleCreateClick}
            className="relative w-full p-3 sm:p-5 rounded-xl sm:rounded-2xl border-2 border-dashed border-ancient-600/50 bg-gradient-to-br from-ancient-900/30 to-purple-900/20 backdrop-blur-sm hover:border-ancient-400/70 hover:from-ancient-900/50 hover:to-purple-900/40 transition-all duration-300 text-left flex flex-col items-center justify-center min-h-[200px] sm:min-h-[240px] gap-3 cursor-pointer group"
          >
            <motion.div
              animate={{ rotate: [0, 0, 0] }}
              whileHover={{ rotate: 90 }}
              transition={{ duration: 0.3 }}
              className="w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-gradient-to-br from-ancient-600 to-purple-600 flex items-center justify-center shadow-lg shadow-ancient-600/30 group-hover:shadow-ancient-500/50"
            >
              <Plus size={28} className="text-white" />
            </motion.div>
            <div className="text-center">
              <h3 className="text-sm sm:text-lg font-bold text-ancient-300 group-hover:text-ancient-200 font-display">
                创建军师
              </h3>
              <p className="text-[10px] sm:text-xs text-ink-500 mt-1">
                AI 智能生成或手动配置
              </p>
            </div>
          </motion.button>

          {filtered.map((advisor) => (
            <AdvisorCard
              key={advisor.id}
              advisor={advisor}
              selected={selected.has(advisor.id)}
              onToggle={() => toggleSelect(advisor.id)}
              disabled={!selected.has(advisor.id) && selected.size >= 12}
            />
          ))}
        </AnimatePresence>
      </motion.div>

      {/* ── Fixed bottom bar ──────────────────────────────────────── */}
      <AnimatePresence>
        {selected.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-0 left-0 right-0 bg-ink-950/95 backdrop-blur-md border-t border-ancient-700/30 p-2.5 sm:p-4 z-40"
            style={{ paddingBottom: "calc(0.75rem + env(safe-area-inset-bottom, 0px))" }}
          >
            <div className="max-w-7xl mx-auto flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                <div className="flex -space-x-2">
                  {Array.from(selected).map((id) => {
                    const adv = advisors.find((a) => a.id === id);
                    return adv ? (
                      <div
                        key={id}
                        className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-ink-800 border-2 border-ancient-600 flex items-center justify-center text-sm font-bold text-ink-200"
                        title={adv.name}
                      >
                        {adv.name[0]}
                      </div>
                    ) : null;
                  })}
                </div>
                <span className="text-xs text-ink-400">已选 {selected.size}/12</span>
              </div>
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={handleConsult}
                disabled={loading}
                className="px-5 sm:px-8 py-2.5 sm:py-3 bg-gradient-to-r from-ancient-600 to-ancient-500 text-white rounded-xl font-bold text-sm sm:text-base shadow-lg shadow-ancient-600/30 disabled:opacity-50"
              >
                {loading ? "召集军师中..." : "⚔️ 开始议事"}
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Name Modal ─────────────────────────────────────────────── */}
      {showNameModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowNameModal(false)}>
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            onClick={(e) => e.stopPropagation()}
            className="bg-ink-900 border border-ink-700 rounded-2xl p-6 w-full max-w-md mx-4 shadow-2xl"
          >
            <h3 className="text-base font-bold text-ink-100 mb-4">为议事厅命名</h3>
            <input
              type="text"
              value={customTitle}
              onChange={(e) => setCustomTitle(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleConfirmCreate(); }}
              className="w-full bg-ink-800 border border-ink-700 rounded-xl px-4 py-2.5 text-ink-100 text-sm placeholder:text-ink-600 focus:outline-none focus:border-ancient-500/50 mb-4"
              autoFocus
              onFocus={(e) => e.target.select()}
            />
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowNameModal(false)}
                className="px-4 py-2 text-sm text-ink-400 hover:text-ink-200 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleConfirmCreate}
                className="px-6 py-2 bg-ancient-600 hover:bg-ancient-500 text-white rounded-xl text-sm font-medium transition-colors"
              >
                确认创建
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* ── Create Advisor Modal ──────────────────────────────────── */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowCreateModal(false)}>
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            onClick={(e) => e.stopPropagation()}
            className="bg-ink-900 border border-ink-700 rounded-xl p-6 w-full max-w-lg mx-4 max-h-[85vh] overflow-y-auto shadow-2xl"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-ink-100">创建军师</h3>
              <button onClick={() => setShowCreateModal(false)} className="text-ink-500 hover:text-ink-300">
                <X size={20} />
              </button>
            </div>

            {createError && (
              <div className="mb-4 p-3 bg-red-900/30 border border-red-800/50 rounded-lg text-red-400 text-sm">
                {createError}
              </div>
            )}

            {createMode === null ? (
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => setCreateMode("smart")}
                  className="p-6 rounded-xl bg-gradient-to-br from-purple-600/20 to-blue-600/20 border border-purple-700/30 hover:border-purple-500/50 transition-all text-center group"
                >
                  <Zap size={32} className="mx-auto mb-3 text-purple-400 group-hover:scale-110 transition-transform" />
                  <h4 className="text-sm font-bold text-ink-100 mb-1">智能创建</h4>
                  <p className="text-xs text-ink-500">只需输入名字，AI 自动生成完整配置</p>
                </button>
                <button
                  onClick={() => setCreateMode("manual")}
                  className="p-6 rounded-xl bg-gradient-to-br from-ancient-600/20 to-amber-600/20 border border-ancient-700/30 hover:border-ancient-500/50 transition-all text-center group"
                >
                  <Sparkles size={32} className="mx-auto mb-3 text-ancient-400 group-hover:scale-110 transition-transform" />
                  <h4 className="text-sm font-bold text-ink-100 mb-1">手动创建</h4>
                  <p className="text-xs text-ink-500">自己填写名称、称号、分类等信息</p>
                </button>
              </div>
            ) : createMode === "smart" ? (
              <div className="space-y-4">
                <button onClick={() => setCreateMode(null)} className="text-xs text-ink-400 hover:text-ink-200">
                  ← 返回选择
                </button>
                <div>
                  <label className="block text-xs text-ink-400 mb-1">军师名称 *</label>
                  <input
                    value={smartName}
                    onChange={(e) => setSmartName(e.target.value)}
                    placeholder="输入名字即可，如：黑格尔、亚里士多德、鲁迅..."
                    className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-purple-600"
                    onKeyDown={(e) => { if (e.key === "Enter") handleSmartCreate(); }}
                    autoFocus
                  />
                </div>
                <div className="p-3 rounded-xl bg-purple-900/20 border border-purple-800/30 text-xs text-purple-300 leading-relaxed">
                  <Sparkles size={14} className="inline mr-1.5" />
                  AI 将自动生成：人物身份、思维框架、核心信条、知识边界、代表著作、以及完整的认知操作系统。
                </div>
                <button
                  onClick={handleSmartCreate}
                  disabled={creating}
                  className="w-full py-2.5 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-all"
                >
                  {creating ? <><Loader2 size={16} className="animate-spin" /> AI 正在生成...</> : <><Zap size={16} /> 一键生成</>}
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <button onClick={() => setCreateMode(null)} className="text-xs text-ink-400 hover:text-ink-200">
                  ← 返回选择
                </button>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-ink-400 mb-1">名称 *</label>
                    <input
                      value={createForm.name}
                      onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                      placeholder="例如: 孙子"
                      className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-ink-400 mb-1">称号 *</label>
                    <input
                      value={createForm.title}
                      onChange={(e) => setCreateForm({ ...createForm, title: e.target.value })}
                      placeholder="例如: 军事家·兵圣"
                      className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-ink-400 mb-1">分类</label>
                    <select
                      value={createForm.category}
                      onChange={(e) => setCreateForm({ ...createForm, category: e.target.value })}
                      className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 focus:outline-none focus:border-ancient-600"
                    >
                      {CATEGORIES.map((c) => (<option key={c} value={c}>{c}</option>))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-ink-400 mb-1">朝代/时代</label>
                    <input
                      value={createForm.era}
                      onChange={(e) => setCreateForm({ ...createForm, era: e.target.value })}
                      placeholder="例如: 春秋"
                      className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-ink-400 mb-1">简介</label>
                  <textarea
                    value={createForm.short_bio}
                    onChange={(e) => setCreateForm({ ...createForm, short_bio: e.target.value })}
                    rows={2}
                    placeholder="一两句话介绍这位军师..."
                    className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600 resize-none"
                  />
                </div>
                <div>
                  <label className="block text-xs text-ink-400 mb-1">说话风格</label>
                  <textarea
                    value={createForm.style}
                    onChange={(e) => setCreateForm({ ...createForm, style: e.target.value })}
                    rows={2}
                    placeholder="例如: 言简意赅，多用兵法比喻..."
                    className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600 resize-none"
                  />
                </div>
                <button
                  onClick={handleManualCreate}
                  disabled={creating}
                  className="w-full py-2.5 bg-ancient-700 hover:bg-ancient-600 disabled:opacity-50 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors"
                >
                  {creating ? <><Loader2 size={16} className="animate-spin" /> 创建中...</> : "创建"}
                </button>
              </div>
            )}
          </motion.div>
        </div>
      )}
    </div>
  );
}
