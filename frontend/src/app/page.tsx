"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Advisor } from "@/lib/types";
import { fetchAdvisors, createCouncil, getToken } from "@/lib/api";
import AdvisorCard from "@/components/AdvisorCard/AdvisorCard";

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
  }, []);

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
    </div>
  );
}
