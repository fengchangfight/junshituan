"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Advisor } from "@/lib/types";
import { fetchAdvisors, createCouncil } from "@/lib/api";
import AdvisorCard from "@/components/AdvisorCard/AdvisorCard";

const CATEGORY_MAP: Record<string, { label: string; icon: string }> = {
  军事家: { label: "军事家", icon: "⚔️" },
  哲学家: { label: "哲学家", icon: "☯️" },
  政治家: { label: "政治家", icon: "👑" },
  佛学大师: { label: "佛学大师", icon: "🪷" },
  企业家: { label: "企业家", icon: "💡" },
};

export default function HomePage() {
  const router = useRouter();
  const [advisors, setAdvisors] = useState<Advisor[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeCategory, setActiveCategory] = useState<string>("全部");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchAdvisors()
      .then(setAdvisors)
      .catch(() => {
        setAdvisors([
          {
            id: "zhuge-liang",
            name: "诸葛亮",
            title: "军事家·政治家",
            category: "军事家",
            era: "三国",
            avatar: "/avatars/zhuge-liang.png",
            shortBio: "字孔明，号卧龙，三国时期蜀汉丞相。",
            style: "谨慎周密，以史为鉴",
          },
        ]);
      });
  }, []);

  const categories = [
    "全部",
    ...Array.from(new Set(advisors.map((a) => a.category))),
  ];

  const filtered =
    activeCategory === "全部"
      ? advisors
      : advisors.filter((a) => a.category === activeCategory);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 5) {
        next.add(id);
      }
      return next;
    });
  };

  const handleConsult = async () => {
    if (selected.size === 0) return;
    setLoading(true);
    try {
      const ids = Array.from(selected);
      const council = await createCouncil(ids);
      const names = ids.map((id) => advisors.find((a) => a.id === id)?.name || id);
      const title = names.join("、") + "的议事厅";
      router.push(
        `/council?id=${council.id}&advisors=${ids.join(",")}&title=${encodeURIComponent(title)}`
      );
    } catch {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-3 sm:px-6 py-6 sm:py-12 pb-24">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-6 sm:mb-12"
      >
        <h2 className="text-2xl sm:text-4xl font-display text-ancient-400 mb-2 sm:mb-4 tracking-widest">
          选择你的军师团
        </h2>
        <p className="text-xs sm:text-base text-ink-400 max-w-xl mx-auto px-2">
          向历史智者请教，让千年智慧照亮你的困惑。选择 1-5 位军师，组成你的专属议事团。
        </p>
      </motion.div>

      <div className="flex justify-center gap-1.5 sm:gap-3 mb-6 sm:mb-10 flex-wrap">
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setActiveCategory(cat)}
            className={`min-h-[44px] px-4 sm:px-5 py-2.5 sm:py-2 rounded-full text-xs sm:text-sm transition-all duration-300 ${
              activeCategory === cat
                ? "bg-ancient-600 text-white shadow-lg shadow-ancient-600/20"
                : "bg-ink-900/50 text-ink-400 hover:text-ink-200 hover:bg-ink-800/50 border border-ink-800/30"
            }`}
          >
            {CATEGORY_MAP[cat]?.icon}{" "}
            {CATEGORY_MAP[cat]?.label || cat}
          </button>
        ))}
      </div>

      <motion.div
        layout
        className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 sm:gap-6"
      >
        <AnimatePresence mode="popLayout">
          {filtered.map((advisor) => (
            <AdvisorCard
              key={advisor.id}
              advisor={advisor}
              selected={selected.has(advisor.id)}
              onToggle={() => toggleSelect(advisor.id)}
              disabled={!selected.has(advisor.id) && selected.size >= 5}
            />
          ))}
        </AnimatePresence>
      </motion.div>

      {selected.size > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="fixed bottom-0 left-0 right-0 bg-ink-950/95 backdrop-blur-md border-t border-ancient-700/30 p-2.5 sm:p-4 z-40"
          style={{ paddingBottom: "calc(0.75rem + env(safe-area-inset-bottom, 0px))" }}
        >
          <div className="max-w-7xl mx-auto flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 sm:gap-4 min-w-0">
              <span className="text-ink-400 text-xs sm:text-sm shrink-0">
                已选 {selected.size}/5
              </span>
              <div className="flex -space-x-2 shrink-0">
                {Array.from(selected).map((id) => {
                  const adv = advisors.find((a) => a.id === id);
                  if (!adv) return null;
                  return (
                    <div
                      key={id}
                      className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-ink-800 border-2 border-ancient-600 flex items-center justify-center text-sm sm:text-lg font-bold text-ink-200"
                      title={adv.name}
                    >
                      {adv.name[0]}
                    </div>
                  );
                })}
              </div>
            </div>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={handleConsult}
              disabled={loading}
              className="px-5 sm:px-8 py-2.5 sm:py-3 bg-gradient-to-r from-ancient-600 to-ancient-500 text-white rounded-xl font-bold text-sm sm:text-lg shadow-lg shadow-ancient-600/30 disabled:opacity-50 transition-all shrink-0"
            >
              {loading ? (
                <span className="flex items-center gap-1.5 sm:gap-2">
                  <motion.span
                    animate={{ rotate: 360 }}
                    transition={{ repeat: Infinity, duration: 1 }}
                    className="text-sm"
                  >
                    ⚔️
                  </motion.span>
                  召集军师中...
                </span>
              ) : (
                "咨 询 军 师"
              )}
            </motion.button>
          </div>
        </motion.div>
      )}
    </div>
  );
}
