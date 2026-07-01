"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { fetchSessions } from "@/lib/api";
import { SessionDetail } from "@/lib/types";
import { ArrowLeft, Loader2, MessageSquare, Clock, ChevronRight } from "lucide-react";

export default function SessionsPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionDetail[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSessions()
      .then(setSessions)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-ink-500" size={24} />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4">
      <button
        onClick={() => router.back()}
        className="flex items-center gap-2 text-ink-400 hover:text-ink-200 mb-6"
      >
        <ArrowLeft size={18} /> 返回
      </button>

      <h2 className="text-xl font-display text-ink-200 mb-6">我的议事厅</h2>

      {sessions.length === 0 ? (
        <div className="text-center py-16 text-ink-500">
          <MessageSquare size={40} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">还没有议事记录</p>
          <Link href="/" className="text-xs text-ancient-400 hover:text-ancient-300 mt-2 inline-block">
            去创建新的议事厅
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {sessions.map((s) => (
            <motion.div
              key={s.id}
              whileHover={{ scale: 1.01 }}
              onClick={() => router.push(`/council?id=${s.id}&advisors=${s.advisor_ids.join(",")}&title=${encodeURIComponent(s.title)}&resume=1`)}
              className="p-4 bg-ink-900/50 border border-ink-800/50 rounded-xl cursor-pointer hover:border-ancient-700/30 transition-all"
            >
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-bold text-ink-100 truncate">
                    {s.title || "议事厅"}
                  </h3>
                  <div className="flex items-center gap-3 mt-1 text-xs text-ink-500">
                    <span className="flex items-center gap-1">
                      <MessageSquare size={12} />
                      {s.message_count || 0} 条消息
                    </span>
                    {s.advisor_ids && (
                      <span>{s.advisor_ids.length} 位军师</span>
                    )}
                    {s.created_at && (
                      <span className="flex items-center gap-1">
                        <Clock size={12} />
                        {new Date(s.created_at).toLocaleDateString("zh-CN")}
                      </span>
                    )}
                  </div>
                </div>
                <ChevronRight size={16} className="text-ink-600 shrink-0" />
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
