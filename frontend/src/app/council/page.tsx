"use client";

import { Suspense, useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Advisor, Message, SessionDetail, BudgetInfo } from "@/lib/types";
import { fetchAdvisors, askCouncil, fetchSessionDetail, addAdvisorsToSession } from "@/lib/api";
import { Send, ArrowLeft, Users, UserPlus, PanelRightOpen, PanelRightClose, X, Loader2, Shuffle } from "lucide-react";
import ChatBubble from "@/components/ChatRoom/ChatBubble";
import Avatar from "@/components/ChatRoom/Avatar";

const AVATAR_COLORS = [
  "from-red-600 to-red-800",
  "from-amber-600 to-amber-800",
  "from-emerald-600 to-emerald-800",
  "from-blue-600 to-blue-800",
  "from-purple-600 to-purple-800",
  "from-teal-600 to-teal-800",
  "from-rose-600 to-rose-800",
];

// System-generated prompts that should not appear in chat history
const SYSTEM_PROMPTS = new Set([
  "请根据之前的讨论继续发言。",
]);

function buildMessagesFromSession(session: SessionDetail): Message[] {
  const msgs: Message[] = [];
  if (session.messages) {
    for (const m of session.messages) {
      // Skip system-generated prompts
      if (m.role === "user" && SYSTEM_PROMPTS.has(m.content)) continue;
      msgs.push({
        id: m.id, role: m.role as "user" | "advisor" | "system",
        advisorId: m.advisor_id, advisorName: m.advisor_name,
        content: m.content, timestamp: new Date(m.created_at).getTime(),
        sequence: m.sequence, metadata: m.metadata,
      });
    }
  }
  if (msgs.length === 0) {
    msgs.push({ id: "system-welcome", role: "system", content: "议事厅已开启。请向军师团提问。", timestamp: Date.now() });
  }
  return msgs;
}

function parseMentions(text: string, advisors: Advisor[]): Advisor[] {
  const matches = text.match(/@(\S+)/g);
  if (!matches) return [];
  const seen = new Set<string>();
  const result: Advisor[] = [];
  for (const m of matches) {
    const name = m.slice(1); // strip @
    const adv = advisors.find((a) => a.name.includes(name) || a.id === name);
    if (adv && !seen.has(adv.id)) {
      seen.add(adv.id);
      result.push(adv);
    }
  }
  return result;
}

function CouncilChat() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("id") || "";
  const advisorIdsParam = (searchParams.get("advisors") || "").split(",").filter(Boolean);
  const title = searchParams.get("title") || "";
  const resumeParam = searchParams.get("resume") || "";

  const [advisors, setAdvisors] = useState<Advisor[]>([]);
  const [allAdvisors, setAllAdvisors] = useState<Advisor[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [replyingId, setReplyingId] = useState<string | null>(null);
  const [budget, setBudget] = useState<BudgetInfo | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [inviting, setInviting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    async function init() {
      const list = await fetchAdvisors().catch(() => []);
      const selected = list.filter((a) => advisorIdsParam.includes(a.id));
      setAdvisors(selected);
      setAllAdvisors(list);

      if (sessionId) {
        const detail = await fetchSessionDetail(sessionId).catch(() => null);
        if (detail && detail.messages && detail.messages.length > 0) {
          setMessages(buildMessagesFromSession(detail));
        } else {
          setMessages([{ id: "system-welcome", role: "system", content: `${selected.map((a) => a.name).join("、")} 已就位。请向军师团提问，或 @军师名 指定谁回答。`, timestamp: Date.now() }]);
        }
      } else {
        setMessages([{ id: "system-welcome", role: "system", content: "议事厅已开启。请向军师团提问。", timestamp: Date.now() }]);
      }
      setInitialLoading(false);
    }
    init();
  }, [sessionId]);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, replyingId]);

  /* ── select a random advisor ── */
  const pickRandom = () => {
    if (advisors.length === 0) return null;
    return advisors[Math.floor(Math.random() * advisors.length)];
  };

  /* ── send message ── */
  const handleSend = useCallback(async () => {
    const question = input.trim();
    if (!question || loading || replyingId || !sessionId) return;
    setInput("");

    const mentioned = parseMentions(question, advisors);
    const targets = mentioned.length > 0 ? mentioned : (() => { const r = pickRandom(); return r ? [r] : []; })();
    if (targets.length === 0) return;

    setLoading(true);
    setReplyingId(targets[0].id);

    const cleanQ = question.replace(/@\S+\s*/g, "").trim() || question;
    const userMsg: Message = {
      id: `user-${Date.now()}`, role: "user",
      content: question, timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);

    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      console.log("[handleSend] calling askCouncil with", targets.length, "targets");
      const stream = askCouncil(sessionId, cleanQ, targets.map((t) => t.id));
      timeout = setTimeout(() => {
        console.log("[handleSend] 120s TIMEOUT fired");
        setMessages((prev) =>
          prev.map((m) => (m.isStreaming ? { ...m, content: "[回答超时，请重试]", isStreaming: false } : m))
        );
        setReplyingId(null);
        setLoading(false);
      }, 120000 * Math.max(targets.length, 1));
      for await (const event of stream) {
        console.log("[handleSend] event:", { advisor_id: event.advisor_id, contentLen: event.content?.length, done: event.done });
        if (event.metadata?.type === "budget" || event.metadata?.type === "budget_update") {
          setBudget(event.metadata.budget);
        }
        if (event.content || event.done) {
          clearTimeout(timeout);
          if (event.done) {
            setReplyingId((prev) => prev === event.advisor_id ? null : prev);
          } else {
            setReplyingId(event.advisor_id);
          }
          setMessages((prev) => {
            // Create pending message lazily if not exists
            const hasPending = prev.some((m) => m.advisorId === event.advisor_id && m.isStreaming);
            let msgs = prev;
            if (!hasPending && event.advisor_id !== "system") {
              msgs = [...prev, {
                id: `pending-${event.advisor_id}`, role: "advisor" as const,
                advisorId: event.advisor_id, advisorName: event.advisor_name || "",
                content: "", timestamp: Date.now(), isStreaming: true,
              }];
            }
            return msgs.map((m) => {
              if (m.advisorId === event.advisor_id && m.isStreaming) {
                return {
                  ...m, content: m.content + (event.content || ""),
                  advisorName: event.advisor_name || m.advisorName,
                  isStreaming: !event.done,
                };
              }
              return m;
            });
          });
        }
      }
      clearTimeout(timeout);
      console.log("[handleSend] stream ended normally");
    } catch (err) {
      console.error("[handleSend] catch error:", err);
      setMessages((prev) => prev.map((m) => m.isStreaming ? { ...m, content: "[回答失败]", isStreaming: false } : m));
    } finally {
      clearTimeout(timeout);
      setReplyingId(null);
      setLoading(false);
    }
  }, [input, loading, replyingId, sessionId, advisors]);

  /* ── trigger specific advisor ── */
  const handlePickAdvisor = useCallback(async (advisor: Advisor) => {
    if (loading || replyingId || !sessionId) return;
    setLoading(true);
    setReplyingId(advisor.id);

    const pendingMsg: Message = {
      id: `pending-${advisor.id}`, role: "advisor",
      advisorId: advisor.id, advisorName: advisor.name,
      content: "（正在根据之前的讨论接话...）", timestamp: Date.now(), isStreaming: true,
    };
    setMessages((prev) => [...prev, pendingMsg]);

    let timeout2: ReturnType<typeof setTimeout> | undefined;
    try {
      let gotContent = false;
      const stream = askCouncil(sessionId, "请根据之前的讨论继续发言。", [advisor.id]);
      timeout2 = setTimeout(() => {
        setMessages((prev) =>
          prev.map((m) => (m.id === pendingMsg.id && m.isStreaming ? { ...m, content: "[回答超时，请重试]", isStreaming: false } : m))
        );
        setReplyingId(null);
        setLoading(false);
      }, 120000);
      for await (const event of stream) {
        if (event.metadata?.type === "budget" || event.metadata?.type === "budget_update") {
          setBudget(event.metadata.budget);
        }
        if (event.content || event.done) {
          clearTimeout(timeout2);
          if (!gotContent && event.content) {
            gotContent = true;
            // Replace the placeholder text
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id === pendingMsg.id) return { ...m, content: event.content || "", isStreaming: !event.done };
                return m;
              })
            );
          } else {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.advisorId === event.advisor_id && m.isStreaming) {
                  return {
                    ...m, content: m.content + (event.content || ""),
                    advisorName: event.advisor_name || m.advisorName,
                    isStreaming: !event.done,
                  };
                }
                return m;
              })
            );
          }
        }
      }
      clearTimeout(timeout2);
    } catch {
      setMessages((prev) => prev.map((m) => m.id === pendingMsg.id ? { ...m, content: "[回答失败]", isStreaming: false } : m));
    } finally {
      clearTimeout(timeout2);
      setReplyingId(null);
      setLoading(false);
    }
  }, [loading, replyingId, sessionId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const groupName = title || advisors.map((a) => a.name).join("、") + "的议事厅";

  const handleInviteAdvisors = useCallback(async (ids: string[]) => {
    if (ids.length === 0) return;
    setInviting(true);
    try {
      await addAdvisorsToSession(sessionId, ids);
      const newAdvisors = allAdvisors.filter((a) => ids.includes(a.id));
      setAdvisors((prev) => {
        const existingIds = new Set(prev.map((p) => p.id));
        return [...prev, ...newAdvisors.filter((a) => !existingIds.has(a.id))];
      });
      setMessages((prev) => [...prev, {
        id: `system-invite-${Date.now()}`, role: "system",
        content: `${newAdvisors.map((a) => a.name).join("、")} 加入了议事厅。`, timestamp: Date.now(),
      }]);
      setShowInvite(false);
    } catch { alert("邀请失败"); } finally { setInviting(false); }
  }, [sessionId, allAdvisors]);

  if (initialLoading) {
    return (
      <div className="flex items-center justify-center h-[100dvh] bg-ink-950">
        <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 2, ease: "linear" }} className="text-4xl">⚔️</motion.div>
      </div>
    );
  }

  const hasStreaming = messages.some((m) => m.isStreaming);

  return (
    <div className="flex flex-col h-[100dvh] bg-ink-950">
      {/* ── Top bar ── */}
      <div className="shrink-0 bg-ink-900/95 backdrop-blur-md border-b border-ink-800/60 px-3 py-2">
        <div className="flex items-center gap-2">
          <a href="/" className="flex items-center justify-center w-11 h-11 rounded-lg hover:bg-ink-800/50 transition-colors shrink-0"><ArrowLeft size={20} className="text-ink-300" /></a>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-bold text-ink-100 truncate">{groupName}</h2>
            <p className="text-xs text-ink-500">
              {replyingId ? `${advisors.find((a) => a.id === replyingId)?.name || "军师"} 正在发言...` : `${advisors.length}位军师在线 — 输入问题开始讨论`}
            </p>
          </div>
          <button onClick={() => setShowSidebar(!showSidebar)} className="w-9 h-9 rounded-lg hover:bg-ink-800/50 flex items-center justify-center transition-colors">
            {showSidebar ? <PanelRightClose size={18} className="text-ink-400" /> : <PanelRightOpen size={18} className="text-ink-400" />}
          </button>
        </div>
      </div>

      {/* ── Budget bar ── */}
      {budget && (
        <div className="px-3 py-1.5 border-b border-ink-800/30 bg-ink-900/40">
          <div className="flex items-center gap-2 text-[11px] text-ink-500">
            <span>额度</span>
            <div className="flex-1 h-1.5 rounded-full bg-ink-800 overflow-hidden">
              <motion.div className={`h-full rounded-full ${budget.over_budget ? "bg-red-500" : budget.budget_percent > 80 ? "bg-amber-500" : "bg-emerald-500"}`}
                initial={{ width: 0 }} animate={{ width: `${Math.min(budget.budget_percent, 100)}%` }} transition={{ duration: 0.5 }} />
            </div>
            <span className={budget.over_budget ? "text-red-400" : "text-ink-500"}>¥{budget.total_cost_cny.toFixed(2)} / ¥{budget.max_budget}</span>
            <span className="text-ink-600">{budget.total_tokens.toLocaleString()} tokens</span>
          </div>
        </div>
      )}

      {/* ── Body ── */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── Sidebar ── */}
        <AnimatePresence>
          {showSidebar && (
            <motion.div initial={{ width: 0, opacity: 0 }} animate={{ width: 280, opacity: 1 }} exit={{ width: 0, opacity: 0 }}
              className="shrink-0 border-r border-ink-800/60 bg-ink-900/30 overflow-y-auto scrollbar-thin">
              <div className="p-3">
                <h3 className="text-xs font-bold text-ink-400 uppercase tracking-wider mb-3 px-1"><Users size={12} className="inline mr-1.5" />议事成员 ({advisors.length})</h3>
                <div className="space-y-1.5">
                  {advisors.map((adv, i) => {
                    const isReplying = replyingId === adv.id;
                    return (
                      <motion.div key={adv.id} initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.08 }}
                        onDoubleClick={() => { setInput((prev) => prev.includes(`@${adv.name}`) ? prev : `${prev}@${adv.name} `); inputRef.current?.focus(); }}
                        title={`双击 @${adv.name}`}
                        className={`flex items-center gap-3 p-2.5 rounded-xl transition-colors cursor-pointer ${isReplying ? "bg-amber-900/20 border border-amber-800/30" : "hover:bg-ink-800/30 border border-transparent"}`}>
                        <Avatar src={adv.avatar} name={adv.name} size="lg" colorClass={AVATAR_COLORS[i % AVATAR_COLORS.length]} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span className="text-sm font-bold text-ink-100 truncate">{adv.name}</span>
                            {isReplying && <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 0.6 }} className="w-2 h-2 rounded-full bg-amber-400 shrink-0" />}
                          </div>
                          <p className="text-[11px] text-ink-500 truncate">{adv.era} · {adv.title}</p>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
                {advisors.length < 12 && (
                  <button onClick={() => setShowInvite(true)}
                    className="mt-3 w-full flex items-center justify-center gap-1.5 py-2 rounded-xl border border-dashed border-ink-600 text-ink-500 hover:text-ink-300 hover:border-ink-500 text-xs transition-colors">
                    <UserPlus size={14} /> 邀请军师加入
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Chat area ── */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 overflow-y-auto scrollbar-thin bg-ink-950">
            <div className="px-3 py-4 space-y-1">
              <AnimatePresence>
                {messages.map((msg, idx) => {
                  const adv = msg.advisorId ? advisors.find((a) => a.id === msg.advisorId) : undefined;
                  const avatarIdx = adv ? advisors.findIndex((a) => a.id === adv.id) : 0;
                  const showAvatar = msg.role === "advisor" && (!messages[idx - 1] || messages[idx - 1].advisorId !== msg.advisorId || messages[idx - 1].role !== "advisor");
                  const isLastAdvisorMsg = msg.role === "advisor" && idx === messages.length - 1;
                  const isDone = !msg.isStreaming && isLastAdvisorMsg;

                  return (
                    <div key={msg.id}>
                      <ChatBubble message={msg} advisor={adv} avatarColor={AVATAR_COLORS[avatarIdx % AVATAR_COLORS.length]} showAvatar={showAvatar} />
                      {/* ── 接话选择器 ── */}
                      {isDone && !replyingId && !loading && (
                        <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="ml-10 mt-2 mb-3"
                          onClick={(e) => e.stopPropagation()}>
                          <div className="text-[11px] text-ink-500 mb-2 flex items-center gap-1"><Shuffle size={12} /> 谁能接话？</div>
                          <div className="flex flex-wrap gap-1.5">
                            {advisors.map((a, i) => (
                              <button key={a.id}
                                onClick={() => handlePickAdvisor(a)}
                                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs transition-all border ${
                                  replyingId === a.id ? "opacity-50" : "bg-ink-800/80 border-ink-700 text-ink-300 hover:border-ancient-500/50 hover:text-ink-100"
                                }`}>
                                {a.avatar ? <img src={a.avatar} className="w-4 h-4 rounded-full object-cover" /> : <div className={`w-4 h-4 rounded-full bg-gradient-to-br ${AVATAR_COLORS[i % AVATAR_COLORS.length]} flex items-center justify-center text-white text-[8px] font-bold`}>{a.name[0]}</div>}
                                {a.name}
                              </button>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </div>
                  );
                })}
              </AnimatePresence>
            </div>
            <div ref={chatEndRef} className="h-4" />
          </div>

          {/* ── Input ── */}
          <div className="shrink-0 bg-ink-900/95 backdrop-blur-md border-t border-ink-800/60 px-3 py-2.5">
            <div className="flex gap-2 items-end">
              <div className="flex-1 bg-ink-800/80 border border-ink-700/40 rounded-2xl px-4 py-2.5">
                <input ref={inputRef} type="text" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown}
                  placeholder={hasStreaming || loading ? "军师正在发言..." : "提问，或双击头像 @军师名 指定谁回答..."}
                  disabled={loading || !!hasStreaming}
                  className="w-full bg-transparent text-ink-100 text-sm placeholder:text-ink-600 focus:outline-none" />
              </div>
              <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.9 }}
                onClick={handleSend} disabled={!input.trim() || loading || !!hasStreaming}
                className="w-11 h-11 rounded-full bg-gradient-to-br from-ancient-500 to-ancient-700 hover:from-ancient-400 hover:to-ancient-600 disabled:from-ink-700 disabled:to-ink-800 flex items-center justify-center shrink-0 transition-all shadow-lg shadow-ancient-600/20">
                {loading ? <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}><Send size={16} className="text-white/70" /></motion.div>
                  : <Send size={16} className="text-white" />}
              </motion.button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Invite modal ── */}
      {showInvite && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowInvite(false)}>
          <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} onClick={(e) => e.stopPropagation()}
            className="bg-ink-900 border border-ink-700 rounded-2xl p-5 w-full max-w-md mx-4 max-h-[70vh] overflow-y-auto shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-bold text-ink-100 flex items-center gap-2"><UserPlus size={18} className="text-ancient-400" />邀请军师加入议事厅</h3>
              <button onClick={() => setShowInvite(false)} className="text-ink-500 hover:text-ink-300"><X size={18} /></button>
            </div>
            <InvitePicker allAdvisors={allAdvisors} currentIds={advisors.map((a) => a.id)} onInvite={handleInviteAdvisors} inviting={inviting} />
          </motion.div>
        </div>
      )}
    </div>
  );
}

/* ── Invite picker component ── */
function InvitePicker({ allAdvisors, currentIds, onInvite, inviting }: { allAdvisors: Advisor[]; currentIds: string[]; onInvite: (ids: string[]) => void; inviting: boolean }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const available = allAdvisors.filter((a) => !currentIds.includes(a.id));

  return (
    <>
      {available.length === 0 ? <p className="text-sm text-ink-500 py-4 text-center">没有更多可用军师了</p> : (
        <div className="space-y-1.5 mb-4 max-h-96 overflow-y-auto">
          {available.map((adv, i) => {
            const isSel = selected.has(adv.id);
            return (
              <motion.div key={adv.id} whileTap={{ scale: 0.98 }}
                onClick={() => setSelected((prev) => { const next = new Set(prev); isSel ? next.delete(adv.id) : next.add(adv.id); return next; })}
                className={`flex items-center gap-3 p-2.5 rounded-xl cursor-pointer transition-all border ${isSel ? "bg-ancient-900/30 border-ancient-600/50" : "bg-ink-900/50 border-ink-800/40 hover:border-ink-600/50"}`}>
                <Avatar src={adv.avatar} name={adv.name} size="md" colorClass={AVATAR_COLORS[i % AVATAR_COLORS.length]} />
                <div className="min-w-0 flex-1"><div className="text-sm font-bold text-ink-100 truncate">{adv.name}</div><div className="text-[11px] text-ink-500 truncate">{adv.era} · {adv.title}</div></div>
                <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 ${isSel ? "border-ancient-500 bg-ancient-500" : "border-ink-600"}`}>
                  {isSel && <div className="w-2 h-2 rounded-full bg-white" />}
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
      <button onClick={() => onInvite(Array.from(selected))} disabled={selected.size === 0 || inviting}
        className="w-full py-2.5 bg-ancient-700 hover:bg-ancient-600 disabled:opacity-40 text-white rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-colors">
        {inviting ? <><Loader2 size={14} className="animate-spin" />邀请中...</> : <><UserPlus size={14} />{selected.size > 0 ? `邀请 ${selected.size} 位军师` : "选择要邀请的军师"}</>}
      </button>
    </>
  );
}

export default function CouncilPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-screen bg-ink-950"><motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 2, ease: "linear" }} className="text-4xl">⚔️</motion.div></div>}>
      <CouncilChat />
    </Suspense>
  );
}
