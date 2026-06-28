"use client";

import { Suspense, useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Advisor, Message, SessionDetail, BudgetInfo } from "@/lib/types";
import { fetchAdvisors, askCouncil, fetchSessionDetail } from "@/lib/api";
import { Send, ArrowLeft, Users, ChevronDown } from "lucide-react";
import ChatBubble from "@/components/ChatRoom/ChatBubble";

const AVATAR_COLORS = [
  "from-red-600 to-red-800",
  "from-amber-600 to-amber-800",
  "from-emerald-600 to-emerald-800",
  "from-blue-600 to-blue-800",
  "from-purple-600 to-purple-800",
  "from-teal-600 to-teal-800",
  "from-rose-600 to-rose-800",
];

function buildMessagesFromSession(session: SessionDetail): Message[] {
  const msgs: Message[] = [];
  if (session.messages) {
    for (const m of session.messages) {
      msgs.push({
        id: m.id,
        role: m.role as "user" | "advisor" | "system",
        advisorId: m.advisor_id,
        advisorName: m.advisor_name,
        content: m.content,
        timestamp: new Date(m.created_at).getTime(),
        sequence: m.sequence,
        metadata: m.metadata,
      });
    }
  }
  if (msgs.length === 0) {
    msgs.push({
      id: "system-welcome",
      role: "system",
      content: "议事厅已开启。请说出你的困惑。",
      timestamp: Date.now(),
    });
  }
  return msgs;
}

function CouncilChat() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("id") || "";
  const advisorIdsParam = (searchParams.get("advisors") || "").split(",").filter(Boolean);
  const title = searchParams.get("title") || "";
  const resumeParam = searchParams.get("resume") || "";

  const [advisors, setAdvisors] = useState<Advisor[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showMembers, setShowMembers] = useState(false);
  const [thinkingIds, setThinkingIds] = useState<Set<string>>(new Set());
  const [budget, setBudget] = useState<BudgetInfo | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const [initialLoading, setInitialLoading] = useState(true);

  useEffect(() => {
    async function init() {
      const list = await fetchAdvisors().catch(() => []);
      const selected = list.filter((a) => advisorIdsParam.includes(a.id));
      setAdvisors(selected);

      if (resumeParam === "1" && sessionId) {
        const detail = await fetchSessionDetail(sessionId).catch(() => null);
        if (detail && detail.messages) {
          setMessages(buildMessagesFromSession(detail));
        } else {
          setMessages([
            {
              id: "system-welcome",
              role: "system",
              content: `${selected.map((a) => a.name).join("、")} 已就位，议事厅开启。`,
              timestamp: Date.now(),
            },
          ]);
        }
      } else {
        setMessages([
          {
            id: "system-welcome",
            role: "system",
            content: `${selected.map((a) => a.name).join("、")} 已就位，议事厅开启。`,
            timestamp: Date.now(),
          },
        ]);
      }
      setInitialLoading(false);
    }
    init();
  }, [sessionId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(async () => {
    const question = input.trim();
    if (!question || loading || !sessionId) return;

    setInput("");
    setLoading(true);

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: question,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);

    const pendingIds = new Set<string>();
    const pendingMsgs = advisorIdsParam.map((aid) => {
      pendingIds.add(aid);
      return {
        id: `pending-${aid}`,
        role: "advisor" as const,
        advisorId: aid,
        advisorName: advisors.find((a) => a.id === aid)?.name || aid,
        content: "",
        timestamp: Date.now(),
        isStreaming: true,
      };
    });
    setThinkingIds(pendingIds);
    setMessages((prev) => [...prev, ...pendingMsgs]);

    try {
      const stream = askCouncil(sessionId, question);
      for await (const event of stream) {
        if (event.metadata?.type === "budget" || event.metadata?.type === "budget_update") {
          setBudget(event.metadata.budget);
        }
        if (event.done) {
          setThinkingIds((prev) => {
            const next = new Set(prev);
            next.delete(event.advisorId);
            return next;
          });
        }
        if (event.content || event.done) {
          setMessages((prev) =>
            prev.map((m) => {
              if (m.advisorId === event.advisorId && m.isStreaming) {
                const newContent = m.content + (event.content || "");
                return {
                  ...m,
                  content: newContent,
                  advisorName: event.advisorName || m.advisorName,
                  isStreaming: !event.done,
                };
              }
              return m;
            })
          );
        }
      }
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.isStreaming ? { ...m, content: "[回答失败，请重试]", isStreaming: false } : m
        )
      );
      setThinkingIds(new Set());
    } finally {
      setLoading(false);
    }
  }, [input, loading, sessionId, advisorIdsParam, advisors]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const groupName = title || advisors.map((a) => a.name).join("、") + "的议事厅";

  if (initialLoading) {
    return (
      <div className="flex items-center justify-center h-[100dvh] bg-ink-950">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
          className="text-4xl"
        >
          ⚔️
        </motion.div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[100dvh] bg-ink-950">
      <div className="shrink-0 bg-ink-900/95 backdrop-blur-md border-b border-ink-800/60 px-3 py-2">
        <div className="flex items-center gap-2">
          <a
            href="/"
            className="flex items-center justify-center w-9 h-9 rounded-lg hover:bg-ink-800/50 transition-colors shrink-0"
          >
            <ArrowLeft size={20} className="text-ink-300" />
          </a>

          <button
            onClick={() => setShowMembers(!showMembers)}
            className="flex-1 flex items-center gap-2.5 min-w-0"
          >
            <div className="flex -space-x-2 shrink-0">
              {advisors.slice(0, 4).map((adv, i) => (
                <div
                  key={adv.id}
                  className={`w-8 h-8 rounded-full bg-gradient-to-br ${AVATAR_COLORS[i % AVATAR_COLORS.length]} border-2 border-ink-900 flex items-center justify-center text-white text-xs font-bold`}
                >
                  {adv.name[0]}
                </div>
              ))}
              {advisors.length > 4 && (
                <div className="w-8 h-8 rounded-full bg-ink-700 border-2 border-ink-900 flex items-center justify-center text-ink-300 text-xs">
                  +{advisors.length - 4}
                </div>
              )}
            </div>
            <div className="min-w-0 text-left">
              <h2 className="text-sm font-bold text-ink-100 truncate">
                {groupName}
              </h2>
              {thinkingIds.size > 0 ? (
                <p className="text-xs text-ancient-400 animate-pulse-soft">
                  {advisors.find((a) => thinkingIds.has(a.id))?.name || "军师"} 正在思考...
                </p>
              ) : (
                <p className="text-xs text-ink-500">
                  {advisors.length}位军师在线
                </p>
              )}
            </div>
          </button>

          <button
            onClick={() => setShowMembers(!showMembers)}
            className="w-9 h-9 rounded-lg hover:bg-ink-800/50 flex items-center justify-center transition-colors"
          >
            <ChevronDown
              size={18}
              className={`text-ink-400 transition-transform duration-200 ${
                showMembers ? "rotate-180" : ""
              }`}
            />
          </button>
        </div>

        <AnimatePresence>
          {showMembers && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="flex flex-wrap gap-2 pt-3 pb-1 px-1">
                {advisors.map((adv, i) => (
                  <div
                    key={adv.id}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-ink-800/50 border border-ink-700/30"
                  >
                    <div
                      className={`w-5 h-5 rounded-full bg-gradient-to-br ${AVATAR_COLORS[i % AVATAR_COLORS.length]} flex items-center justify-center text-white text-[10px] font-bold`}
                    >
                      {adv.name[0]}
                    </div>
                    <span className="text-xs text-ink-200">{adv.name}</span>
                    <span className="text-[10px] text-ink-500">
                      {adv.era}·{adv.title}
                    </span>
                    {thinkingIds.has(adv.id) && (
                      <motion.span
                        animate={{ opacity: [0.4, 1, 0.4] }}
                        transition={{ repeat: Infinity, duration: 0.8 }}
                        className="w-1.5 h-1.5 rounded-full bg-ancient-400"
                      />
                    )}
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {budget && (
        <div className="px-3 py-1.5 border-b border-ink-800/30 bg-ink-900/40">
          <div className="flex items-center gap-2 text-[10px] text-ink-500">
            <span>额度</span>
            <div className="flex-1 h-1.5 rounded-full bg-ink-800 overflow-hidden">
              <motion.div
                className={`h-full rounded-full ${
                  budget.over_budget ? "bg-red-500" : budget.budget_percent > 80 ? "bg-amber-500" : "bg-emerald-500"
                }`}
                initial={{ width: 0 }}
                animate={{ width: `${Math.min(budget.budget_percent, 100)}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
            <span className={budget.over_budget ? "text-red-400" : "text-ink-500"}>
              ¥{budget.total_cost_cny.toFixed(2)} / ¥{budget.max_budget}
            </span>
            <span className="text-ink-600">
              {budget.total_tokens.toLocaleString()} tokens
            </span>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto scrollbar-thin bg-ink-950">
        <div className="px-3 py-4 space-y-1">
          <AnimatePresence>
            {messages.map((msg, idx) => {
              const adv = msg.advisorId
                ? advisors.find((a) => a.id === msg.advisorId)
                : undefined;
              const avatarIdx = adv
                ? advisors.findIndex((a) => a.id === adv.id)
                : 0;

              const showAvatar =
                msg.role === "advisor" &&
                (!messages[idx - 1] ||
                  messages[idx - 1].advisorId !== msg.advisorId ||
                  messages[idx - 1].role !== "advisor");

              return (
                <ChatBubble
                  key={msg.id}
                  message={msg}
                  advisor={adv}
                  avatarColor={AVATAR_COLORS[avatarIdx % AVATAR_COLORS.length]}
                  showAvatar={showAvatar}
                />
              );
            })}
          </AnimatePresence>
        </div>
        <div ref={chatEndRef} className="h-4" />
      </div>

      <div className="shrink-0 bg-ink-900/95 backdrop-blur-md border-t border-ink-800/60 px-3 py-2.5 safe-area-bottom">
        <div className="flex gap-2 items-end">
          <div className="flex-1 bg-ink-800/80 border border-ink-700/40 rounded-2xl px-4 py-2.5">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="向军师团提问..."
              disabled={loading}
              className="w-full bg-transparent text-ink-100 text-sm placeholder:text-ink-600 focus:outline-none"
            />
          </div>
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.9 }}
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="w-10 h-10 rounded-full bg-gradient-to-br from-ancient-500 to-ancient-700 hover:from-ancient-400 hover:to-ancient-600 disabled:from-ink-700 disabled:to-ink-800 flex items-center justify-center shrink-0 transition-all shadow-lg shadow-ancient-600/20"
          >
            {loading ? (
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
              >
                <Send size={16} className="text-white/70" />
              </motion.div>
            ) : (
              <Send size={16} className="text-white" />
            )}
          </motion.button>
        </div>
      </div>
    </div>
  );
}

export default function CouncilPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-screen bg-ink-950">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
            className="text-4xl"
          >
            ⚔️
          </motion.div>
        </div>
      }
    >
      <CouncilChat />
    </Suspense>
  );
}
