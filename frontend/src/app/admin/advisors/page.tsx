"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, CheckCircle, AlertCircle, Loader2, Circle } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Advisor {
  id: string;
  name: string;
  title: string;
  category: string;
  era: string;
  kb_status: string;
  kb_doc_count: number;
  is_published: boolean;
}

export default function AdminAdvisorsPage() {
  const [advisors, setAdvisors] = useState<Advisor[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("junshituan_token");
    fetch(`${API_BASE}/api/admin/advisors`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setAdvisors)
      .finally(() => setLoading(false));
  }, []);

  const statusIcon = (status: string) => {
    switch (status) {
      case "ready":
        return <CheckCircle size={14} className="text-emerald-400" />;
      case "ingesting":
        return <Loader2 size={14} className="text-amber-400 animate-spin" />;
      case "error":
        return <AlertCircle size={14} className="text-red-400" />;
      default:
        return <Circle size={14} className="text-ink-600" />;
    }
  };

  const statusLabel = (status: string) => {
    switch (status) {
      case "ready": return "已就绪";
      case "ingesting": return "消化中";
      case "error": return "失败";
      default: return "未配置";
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-ink-500" size={24} />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-display text-ink-200">知识库管理</h2>
        <p className="text-sm text-ink-500 mt-1">
          管理每个军师的知识文档，消化后发布为可用状态
        </p>
      </div>

      <div className="space-y-3">
        {advisors.map((adv) => (
          <Link key={adv.id} href={`/admin/advisors/${adv.id}`}>
            <motion.div
              whileHover={{ scale: 1.01 }}
              className="flex items-center gap-4 p-4 rounded-xl bg-ink-900/50 border border-ink-800/50 hover:border-ancient-700/30 transition-all"
            >
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-ink-800 to-ink-700 flex items-center justify-center text-sm font-bold text-ink-200 shrink-0">
                {adv.name[0]}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="font-bold text-ink-100">{adv.name}</h3>
                  <span className="text-xs text-ink-500">{adv.era}·{adv.title}</span>
                </div>
                <div className="flex items-center gap-3 mt-1">
                  <span className="flex items-center gap-1 text-xs">
                    {statusIcon(adv.kb_status)}
                    <span className={
                      adv.kb_status === "ready" ? "text-emerald-400" :
                      adv.kb_status === "error" ? "text-red-400" :
                      "text-ink-500"
                    }>
                      {statusLabel(adv.kb_status)}
                    </span>
                  </span>
                  {adv.kb_doc_count > 0 && (
                    <span className="text-xs text-ink-600">{adv.kb_doc_count} 条索引</span>
                  )}
                  {adv.is_published && (
                    <span className="text-[10px] bg-emerald-900/40 text-emerald-400 px-2 py-0.5 rounded-full">
                      已发布
                    </span>
                  )}
                  {!adv.is_published && adv.kb_status === "ready" && (
                    <span className="text-[10px] bg-amber-900/40 text-amber-400 px-2 py-0.5 rounded-full">
                      未发布
                    </span>
                  )}
                </div>
              </div>
              <ArrowRight size={16} className="text-ink-600 shrink-0" />
            </motion.div>
          </Link>
        ))}
      </div>
    </div>
  );
}
