"use client";

import { Suspense, useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Advisor, Message, SessionDetail, BudgetInfo } from "@/lib/types";
import { fetchAdvisors, askCouncil, fetchSessionDetail, addAdvisorsToSession } from "@/lib/api";
import { Send, ArrowLeft, Users, UserPlus, PanelRightOpen, PanelRightClose, X, Loader2, Shuffle, Wrench, CheckCircle, Download } from "lucide-react";
import html2canvas from "html2canvas";
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
  const [advisors, setAdvisors] = useState<Advisor[]>([]);
  const [allAdvisors, setAllAdvisors] = useState<Advisor[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [showToolPanel, setShowToolPanel] = useState(true);
  const [replyingId, setReplyingId] = useState<string | null>(null);
  const [budget, setBudget] = useState<BudgetInfo | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [inviting, setInviting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const [toolActivities, setToolActivities] = useState<Array<{id: string; advisorId: string; advisorName: string; toolName: string; query: string; status: "running"|"done"; ts: number; results?: Array<{title: string; href: string; snippet: string}>}>>([]);
  const [useWebSearch, setUseWebSearch] = useState(true);

  useEffect(() => {
    // Mobile: start with sidebar/tool-panel hidden so chat is front and center
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      setShowSidebar(false);
      setShowToolPanel(false);
    }

    async function init() {
      const list = await fetchAdvisors().catch(() => []);
      setAllAdvisors(list);

      // Resolve session advisors — create placeholders for deleted ones
      const resolved = advisorIdsParam.map((id) => {
        const found = list.find((a) => a.id === id);
        return found || {
          id,
          name: "已删除",
          title: "该军师已被删除",
          category: "",
          era: "",
          avatar: "",
          shortBio: "",
          style: "",
          visibility: "",
        } as Advisor;
      });
      setAdvisors(resolved);

      if (sessionId) {
        const detail = await fetchSessionDetail(sessionId).catch(() => null);
        if (detail && detail.messages && detail.messages.length > 0) {
          setMessages(buildMessagesFromSession(detail));
        } else {
          const names = resolved.map((a) => a.name).join("、");
          setMessages([{ id: "system-welcome", role: "system", content: `${names} 已就位。请向军师团提问，或 @军师名 指定谁回答。`, timestamp: Date.now() }]);
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
      const stream = askCouncil(sessionId, cleanQ, targets.map((t) => t.id), useWebSearch);
      timeout = setTimeout(() => {
        setMessages((prev) =>
          prev.map((m) => (m.isStreaming ? { ...m, content: "[回答超时，请重试]", isStreaming: false } : m))
        );
        setReplyingId(null);
        setLoading(false);
      }, 120000 * Math.max(targets.length, 1));
      for await (const event of stream) {
        if (event.metadata?.type === "budget" || event.metadata?.type === "budget_update") {
          setBudget(event.metadata.budget);
        }
        if (event.metadata?.type === "tool_progress" && event.metadata?.tool_name === "web_search") {
          // Update tool activity panel (right side)
          const tp = event.metadata;
          const actId = `${event.advisor_id}-${tp.query}`;
          setToolActivities((prev) => {
            if (tp.action === "tool_start") {
              return [...prev.filter((a) => a.id !== actId), {
                id: actId, advisorId: event.advisor_id, advisorName: event.advisor_name || "",
                toolName: tp.tool_name, query: tp.query || "", status: "running" as const, ts: Date.now(),
              }];
            } else {
              return prev.map((a) => a.id === actId ? { ...a, status: "done" as const, results: tp.results || [] } : a);
            }
          });
          // Show status in chat bubble only on tool_start (keeps user informed without
          // the confusing "done → wait → done again" flicker from multi-round tool calls)
          if (tp.action === "tool_start") {
            const statusText = `📚 正在搜集汇总资料：${tp.query || "..."}`;
            setReplyingId(event.advisor_id);
            setMessages((prev) => {
              const hasPending = prev.some((m) => m.advisorId === event.advisor_id && m.isStreaming);
              let msgs = prev;
              if (!hasPending && event.advisor_id !== "system") {
                msgs = [...prev, {
                  id: `pending-${event.advisor_id}-${Math.random().toString(36).slice(2, 8)}`, role: "advisor" as const,
                  advisorId: event.advisor_id, advisorName: event.advisor_name || "",
                  content: statusText, timestamp: Date.now(), isStreaming: true,
                }];
              }
              return msgs.map((m) => {
                if (m.advisorId === event.advisor_id && m.isStreaming) {
                  return { ...m, content: statusText };
                }
                return m;
              });
            });
          }
        } else if (event.content || event.done) {
          clearTimeout(timeout);
          if (event.done) {
            setReplyingId((prev) => prev === event.advisor_id ? null : prev);
          } else {
            setReplyingId(event.advisor_id);
          }
          setMessages((prev) => {
            const hasPending = prev.some((m) => m.advisorId === event.advisor_id && m.isStreaming);
            let msgs = prev;
            if (!hasPending && event.advisor_id !== "system") {
              msgs = [...prev, {
                id: `pending-${event.advisor_id}-${Math.random().toString(36).slice(2, 8)}`, role: "advisor" as const,
                advisorId: event.advisor_id, advisorName: event.advisor_name || "",
                content: "", timestamp: Date.now(), isStreaming: true,
              }];
            }
            return msgs.map((m) => {
              if (m.advisorId === event.advisor_id && m.isStreaming) {
                const isToolStatus = m.content.startsWith("📚");
                return {
                  ...m,
                  content: isToolStatus ? (event.content || "") : m.content + (event.content || ""),
                  advisorName: event.advisor_name || m.advisorName,
                  isStreaming: !event.done,
                };
              }
              return m;
            });
          });
        } else if (event.advisor_id !== "system") {
          // Initial ping: advisor is about to start thinking.
          // Show yellow dot + thinking indicator immediately,
          // instead of waiting ~10s for the first real token.
          setReplyingId(event.advisor_id);
          setMessages((prev) => {
            const hasPending = prev.some((m) => m.advisorId === event.advisor_id && m.isStreaming);
            if (!hasPending) {
              return [...prev, {
                id: `pending-${event.advisor_id}-${Math.random().toString(36).slice(2, 8)}`, role: "advisor" as const,
                advisorId: event.advisor_id, advisorName: event.advisor_name || "",
                content: "", timestamp: Date.now(), isStreaming: true,
              }];
            }
            return prev;
          });
        }
      }
      clearTimeout(timeout);
    } catch (err) {
      console.error("[handleSend] stream error:", err);
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
      id: `pending-${advisor.id}-${Math.random().toString(36).slice(2, 8)}`, role: "advisor",
      advisorId: advisor.id, advisorName: advisor.name,
      content: "（正在根据之前的讨论接话...）", timestamp: Date.now(), isStreaming: true,
    };
    setMessages((prev) => [...prev, pendingMsg]);

    let timeout2: ReturnType<typeof setTimeout> | undefined;
    try {
      let gotContent = false;
      const stream = askCouncil(sessionId, "请根据之前的讨论继续发言。", [advisor.id], useWebSearch);
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
        if (event.metadata?.type === "tool_progress" && event.metadata?.tool_name === "web_search") {
          const tp = event.metadata;
          const actId = `${event.advisor_id}-${tp.query}`;
          setToolActivities((prev) => {
            if (tp.action === "tool_start") {
              return [...prev.filter((a) => a.id !== actId), {
                id: actId, advisorId: event.advisor_id, advisorName: event.advisor_name || "",
                toolName: tp.tool_name, query: tp.query || "", status: "running" as const, ts: Date.now(),
              }];
            } else {
              return prev.map((a) => a.id === actId ? { ...a, status: "done" as const, results: tp.results || [] } : a);
            }
          });
          // Only update chat bubble on tool_start (avoid confusing "done/done again" flicker)
          if (tp.action === "tool_start") {
            const statusText = `📚 正在搜集汇总资料：${tp.query || "..."}`;
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id === pendingMsg.id) return { ...m, content: statusText };
                if (m.advisorId === event.advisor_id && m.isStreaming) return { ...m, content: statusText };
                return m;
              })
            );
          }
        } else if (event.content || event.done) {
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
                  const isToolStatus = m.content.startsWith("📚");
                  return {
                    ...m,
                    content: isToolStatus ? (event.content || "") : m.content + (event.content || ""),
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

  const [exporting, setExporting] = useState(false);
  const [exportImageUrl, setExportImageUrl] = useState<string | null>(null);
  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      // Build a clean capture DOM — mobile-width, chat-style, no UI chrome
      const container = document.createElement("div");
      container.style.cssText =
        "position:fixed;left:-9999px;top:0;width:420px;background:#0f0f1a;padding:16px 12px 24px;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;color:#d0cfd4;line-height:1.6;z-index:99999;";
      document.body.appendChild(container);

      // Header
      const header = document.createElement("div");
      header.style.cssText = "text-align:center;padding:12px 0 16px;border-bottom:1px solid rgba(180,140,60,0.25);margin-bottom:16px;";
      header.innerHTML = `<div style="font-size:20px;color:#d4852c;letter-spacing:2px;margin-bottom:4px;">⚔️ ${groupName}</div><div style="font-size:11px;color:#6b6b7b;">${messages.filter(m => !m.isStreaming).length} 条消息</div>`;
      container.appendChild(header);

      // Messages
      const msgContainer = document.createElement("div");
      for (const m of messages) {
        if (m.isStreaming) continue;
        const esc = (s: string) => s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
        if (m.role === "system") {
          const el = document.createElement("div");
          el.style.cssText = "display:flex;justify-content:center;padding:6px 0;margin-bottom:6px;";
          el.innerHTML = `<span style="font-size:11px;color:#6b6b7b;background:rgba(255,255,255,0.04);padding:4px 12px;border-radius:12px;">${esc(m.content)}</span>`;
          msgContainer.appendChild(el);
        } else if (m.role === "user") {
          const el = document.createElement("div");
          el.style.cssText = "display:flex;justify-content:flex-end;margin-bottom:8px;";
          el.innerHTML = `<div style="max-width:80%;padding:10px 14px;border-radius:16px;border-bottom-right-radius:4px;font-size:14px;line-height:1.55;white-space:pre-wrap;word-break:break-word;background:linear-gradient(135deg,#b86b2a,#d4852c);color:#fff;">${esc(m.content)}</div>`;
          msgContainer.appendChild(el);
        } else {
          const adv = advisors.find(a => a.id === m.advisorId);
          const avatarHtml = adv?.avatar
            ? `<img src="${adv.avatar}" style="width:36px;height:36px;border-radius:50%;object-fit:cover;flex-shrink:0;" onerror="this.style.display='none'" />`
            : `<div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#2a2a3e,#3a3a4e);display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:bold;color:#d0cfd4;flex-shrink:0;">${(m.advisorName || "?")[0]}</div>`;
          const el = document.createElement("div");
          el.style.cssText = "display:flex;gap:8px;align-items:flex-start;margin-bottom:8px;";
          el.innerHTML = `${avatarHtml}<div style="min-width:0;"><div style="font-size:11px;font-weight:600;color:#90909e;margin-bottom:3px;">${m.advisorName || ""}</div><div style="max-width:100%;padding:10px 14px;border-radius:16px;border-top-left-radius:4px;font-size:14px;line-height:1.55;white-space:pre-wrap;word-break:break-word;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.08);">${esc(m.content)}</div></div>`;
          msgContainer.appendChild(el);
        }
      }
      container.appendChild(msgContainer);

      // Branding footer with QR code
      const brandFooter = document.createElement("div");
      brandFooter.style.cssText = "margin-top:20px;padding-top:16px;border-top:1px solid rgba(180,140,60,0.2);display:flex;align-items:center;justify-content:center;gap:16px;";
      // Load QR code as data URI (bypass CORS issues with html2canvas)
      let qrDataUrl = "";
      try {
        const qrBlob = await fetch(
          "https://api.qrserver.com/v1/create-qr-code/?size=100x100&data=https://www.junshituan.com&margin=6&color=07c160&bgcolor=0f0f1a"
        ).then(r => r.blob());
        qrDataUrl = await new Promise<string>(resolve => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.readAsDataURL(qrBlob);
        });
      } catch {}
      brandFooter.innerHTML =
        `<div style="text-align:right;">` +
        `<div style="font-size:15px;font-weight:bold;color:#d4852c;letter-spacing:1px;margin-bottom:2px;">⚔️ 议事厅</div>` +
        `<div style="font-size:11px;color:#6b6b7b;margin-bottom:4px;">junshituan.com</div>` +
        `<div style="font-size:10px;color:#4a4a5a;">召集你的智者团</div>` +
        `</div>` +
        (qrDataUrl
          ? `<img src="${qrDataUrl}" style="width:80px;height:80px;border-radius:8px;border:2px solid rgba(7,193,96,0.3);" />`
          : `<div style="width:80px;height:80px;border-radius:8px;border:2px dashed rgba(255,255,255,0.1);display:flex;align-items:center;justify-content:center;font-size:9px;color:#4a4a5a;">扫码访问</div>`);
      container.appendChild(brandFooter);

      // Render to canvas
      const canvas = await html2canvas(container, {
        backgroundColor: "#0f0f1a",
        scale: 2,
        useCORS: true,
        logging: false,
      });

      // Clean up hidden DOM
      document.body.removeChild(container);

      // Use data URI (not blob) — WeChat needs self-contained data to save/share
      const dataUrl = canvas.toDataURL("image/png");
      setExportImageUrl(dataUrl);
    } catch (e) {
      console.error("Export failed:", e);
    } finally {
      setExporting(false);
    }
  }, [groupName, messages, advisors]);

  const closePreview = () => {
    setExportImageUrl(null);
  };

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
      <div className="sticky top-0 z-30 shrink-0 bg-ink-900/95 backdrop-blur-md border-b border-ink-800/60 px-3 py-2">
        <div className="flex items-center gap-2">
          <a href="/" className="flex items-center justify-center w-11 h-11 rounded-lg hover:bg-ink-800/50 transition-colors shrink-0"><ArrowLeft size={20} className="text-ink-300" /></a>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-bold text-ink-100 truncate">{groupName}</h2>
            <p className="text-xs text-ink-500 hidden sm:block">
              {replyingId ? `${advisors.find((a) => a.id === replyingId)?.name || "军师"} 正在发言...` : `${advisors.length}位军师在线 — 输入问题开始讨论`}
            </p>
          </div>
          {/* Desktop sidebar toggle */}
          <button onClick={() => setShowSidebar(!showSidebar)} className="hidden md:flex w-9 h-9 rounded-lg hover:bg-ink-800/50 items-center justify-center transition-colors">
            {showSidebar ? <PanelRightClose size={18} className="text-ink-400" /> : <PanelRightOpen size={18} className="text-ink-400" />}
          </button>
          <button onClick={() => setShowToolPanel(!showToolPanel)} className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors relative shrink-0 ${
            toolActivities.some((a) => a.status === "running") ? "bg-blue-900/30 text-blue-400" :
            toolActivities.length > 0 ? "text-ink-300 hover:bg-ink-800/50 hover:text-ink-200" :
            "text-ink-500 hover:bg-ink-800/50 hover:text-ink-400"
          }`}>
            <motion.div
              animate={toolActivities.some((a) => a.status === "running") ? { rotate: 360 } : {}}
              transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
            >
              <Wrench size={16} />
            </motion.div>
            {toolActivities.some((a) => a.status === "running") && (
              <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-blue-400 rounded-full animate-pulse" />
            )}
          </button>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gradient-to-r from-emerald-600 to-teal-600 text-white text-xs font-bold shadow-lg shadow-emerald-600/20 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 transition-all shrink-0"
            title="导出长图"
          >
            {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            导出
          </button>
        </div>
      </div>

      {/* ── Mobile advisor strip ── */}
      <div className="md:hidden sticky top-[53px] z-30 shrink-0 bg-ink-900/80 border-b border-ink-800/50 px-2 py-1.5">
        <div className="flex items-center gap-1.5 overflow-x-auto [&::-webkit-scrollbar]:hidden">
          <button
            onClick={() => setShowSidebar(true)}
            className="shrink-0 flex items-center gap-1 px-2 py-1 rounded-lg bg-ink-800/80 border border-ink-700/50 text-ink-400 text-xs hover:text-ink-200 transition-colors"
          >
            <Users size={14} />
            <span>{advisors.length}人</span>
          </button>
          {advisors.map((adv, i) => {
            const isReplying = replyingId === adv.id;
            const isDeleted = adv.name === "已删除";
            return (
              <button
                key={adv.id}
                disabled={isDeleted}
                onClick={() => {
                  if (isDeleted) return;
                  setInput((prev) => prev.includes(`@${adv.name}`) ? prev : `${prev}@${adv.name} `);
                  inputRef.current?.focus();
                }}
                className={`shrink-0 flex items-center gap-1.5 px-2 py-1 rounded-full text-xs transition-all border ${
                  isReplying
                    ? "bg-amber-900/30 border-amber-600/50"
                    : isDeleted
                    ? "opacity-40 border-ink-800"
                    : "bg-ink-800/50 border-ink-700/50 hover:border-ink-500 text-ink-300"
                }`}
              >
                {adv.avatar ? (
                  <img src={adv.avatar} className="w-5 h-5 rounded-full object-cover shrink-0" />
                ) : (
                  <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0 ${
                    isDeleted ? "bg-ink-700" : `bg-gradient-to-br ${AVATAR_COLORS[i % AVATAR_COLORS.length]}`
                  }`}>
                    {adv.name[0]}
                  </div>
                )}
                <span className={isDeleted ? "text-ink-600 line-through" : ""}>{adv.name}</span>
                {isReplying && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
              </button>
            );
          })}
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
        {/* ── Sidebar (mobile: overlay with backdrop, desktop: inline column) ── */}
        <AnimatePresence>
          {showSidebar && (
            <>
              {/* Mobile backdrop */}
              <motion.div
                key="sidebar-backdrop"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="md:hidden fixed inset-0 z-30 bg-black/60"
                onClick={() => setShowSidebar(false)}
              />
              {/* Sidebar content */}
              <motion.div
                key="sidebar-content"
                initial={{ x: -280, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: -280, opacity: 0 }}
                transition={{ type: "spring", damping: 25, stiffness: 300 }}
                className="fixed md:relative left-0 top-0 bottom-0 z-40 md:z-0 w-[280px] shrink-0 border-r border-ink-800/60 bg-ink-900/95 md:bg-ink-900/30 overflow-y-auto scrollbar-thin">
              <div className="p-3">
                <div className="flex items-center justify-between mb-3 px-1">
                  <h3 className="text-xs font-bold text-ink-400 uppercase tracking-wider"><Users size={12} className="inline mr-1.5" />议事成员 ({advisors.length})</h3>
                  <button onClick={() => setShowSidebar(false)} className="md:hidden text-ink-500 hover:text-ink-300"><X size={16} /></button>
                </div>
                <div className="space-y-1.5">
                  {advisors.map((adv, i) => {
                    const isReplying = replyingId === adv.id;
                    const isDeleted = adv.name === "已删除";
                    return (
                      <motion.div key={adv.id} initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.08 }}
                        onDoubleClick={() => { if (!isDeleted) { setInput((prev) => prev.includes(`@${adv.name}`) ? prev : `${prev}@${adv.name} `); inputRef.current?.focus(); } }}
                        title={isDeleted ? "该军师已被删除" : `双击 @${adv.name}`}
                        className={`flex items-center gap-3 p-2.5 rounded-xl transition-colors ${isDeleted ? "opacity-50 cursor-default" : "cursor-pointer hover:bg-ink-800/30"} ${isReplying ? "bg-amber-900/20 border border-amber-800/30" : "border border-transparent"}`}>
                        <Avatar src={adv.avatar} name={adv.name} size="lg" colorClass={isDeleted ? "from-ink-700 to-ink-800" : AVATAR_COLORS[i % AVATAR_COLORS.length]} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span className={`text-sm font-bold truncate ${isDeleted ? "text-ink-500 line-through" : "text-ink-100"}`}>{adv.name}</span>
                            {isReplying && <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 0.6 }} className="w-2 h-2 rounded-full bg-amber-400 shrink-0" />}
                          </div>
                          <p className="text-[11px] text-ink-600 truncate">{isDeleted ? "该军师已被删除" : `${adv.era} · ${adv.title}`}</p>
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
            </>
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
          <div className="shrink-0 bg-ink-900/95 backdrop-blur-md border-t border-ink-800/60 px-2 sm:px-3 py-2.5"
            style={{ paddingBottom: "calc(0.625rem + env(safe-area-inset-bottom, 0px))" }}>
            <div className="flex gap-2 items-end">
              <div className="flex-1 bg-ink-800/80 border border-ink-700/40 rounded-2xl px-4 py-2.5">
                <input ref={inputRef} type="text" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown}
                  placeholder={hasStreaming || loading ? "军师正在发言..." : "提问，或双击头像 @军师名 指定谁回答..."}
                  disabled={loading || !!hasStreaming}
                  className="w-full bg-transparent text-ink-100 text-sm placeholder:text-ink-600 focus:outline-none" />
              </div>
              <button
                onClick={() => setUseWebSearch(!useWebSearch)}
                title={useWebSearch ? "已启用网络搜索" : "已禁用网络搜索（更快）"}
                className={`shrink-0 px-2 py-1 rounded-lg text-[10px] font-medium transition-colors border ${
                  useWebSearch
                    ? "bg-blue-900/20 border-blue-700/40 text-blue-400"
                    : "bg-ink-800 border-ink-700/40 text-ink-600"
                }`}
              >
                {useWebSearch ? "🌐 联网" : "⚡ 快速"}
              </button>
              <button
                onClick={handleExport}
                disabled={exporting}
                title="导出长图"
                className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gradient-to-r from-emerald-600 to-teal-600 text-white text-xs font-bold shadow-lg shadow-emerald-600/20 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 transition-all"
              >
                {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                导出
              </button>
              <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.9 }}
                onClick={handleSend} disabled={!input.trim() || loading || !!hasStreaming}
                className="w-11 h-11 rounded-full bg-gradient-to-br from-ancient-500 to-ancient-700 hover:from-ancient-400 hover:to-ancient-600 disabled:from-ink-700 disabled:to-ink-800 flex items-center justify-center shrink-0 transition-all shadow-lg shadow-ancient-600/20">
                {loading ? <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}><Send size={16} className="text-white/70" /></motion.div>
                  : <Send size={16} className="text-white" />}
              </motion.button>
            </div>
          </div>
        </div>

        {/* ── Tool Activity Panel (mobile: bottom sheet, desktop: inline column) ── */}
        <AnimatePresence>
          {showToolPanel && (
            <>
              {/* Mobile backdrop */}
              <motion.div
                key="tool-backdrop"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="md:hidden fixed inset-0 z-30 bg-black/60"
                onClick={() => setShowToolPanel(false)}
              />
              {/* Panel content */}
              <motion.div
                key="tool-content"
                initial={{ y: "100%", opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={{ y: "100%", opacity: 0 }}
                transition={{ type: "spring", damping: 28, stiffness: 300 }}
                className="fixed md:relative bottom-0 md:bottom-auto left-0 md:left-auto right-0 md:right-auto z-40 md:z-0
                           max-h-[60vh] md:max-h-none w-full md:w-[260px] shrink-0
                           border-t md:border-t-0 md:border-l border-ink-800/60
                           bg-ink-900/95 md:bg-ink-900/30 overflow-y-auto scrollbar-thin
                           rounded-t-2xl md:rounded-none"
            >
              <div className="p-3">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-bold text-ink-400 uppercase tracking-wider flex items-center gap-1.5">
                    <span className="text-[10px]">⚙️</span> 工具调用
                  </h3>
                  <button onClick={() => setShowToolPanel(false)} className="text-ink-600 hover:text-ink-400">
                    <X size={12} />
                  </button>
                </div>
                {toolActivities.length === 0 ? (
                  <p className="text-xs text-ink-600 italic py-4 text-center">
                    暂无工具调用记录
                  </p>
                ) : (
                <div className="space-y-1.5">
                  {toolActivities.slice(-20).reverse().map((act) => (
                    <div key={act.id} className="relative group">
                      <div className={`p-2 rounded-lg text-xs border transition-colors cursor-default ${
                        act.status === "running"
                          ? "bg-blue-900/15 border-blue-800/30"
                          : "bg-ink-900/30 border-ink-800/30 hover:border-ink-600/50"
                      }`}>
                        <div className="flex items-center gap-1.5 mb-0.5">
                          {act.status === "running" ? (
                            <Loader2 size={10} className="text-blue-400 animate-spin shrink-0" />
                          ) : (
                            <CheckCircle size={10} className="text-emerald-400 shrink-0" />
                          )}
                          <span className="text-ink-300 font-medium truncate">{act.advisorName}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <span className="text-[10px] px-1 py-0.5 rounded bg-ink-800 text-ink-500 font-mono shrink-0">
                            {act.toolName === "web_search" ? "搜索" : act.toolName}
                          </span>
                          <span className="text-ink-500 truncate">{act.query}</span>
                        </div>
                      </div>
                      {/* Hover tooltip — stays open for click interaction */}
                      {act.results && act.results.length > 0 && (
                        <div className="absolute left-0 right-0 top-full z-50 pt-1
                                        opacity-0 pointer-events-none
                                        group-hover:opacity-100 group-hover:pointer-events-auto
                                        transition-opacity duration-150">
                          <div className="bg-ink-800 border border-ink-600 rounded-lg p-2 shadow-xl max-h-48 overflow-y-auto">
                            {act.results.map((r, i) => (
                              <a key={i} href={r.href} target="_blank" rel="noopener noreferrer"
                                className="block p-1.5 rounded hover:bg-ink-700/50 transition-colors mb-0.5 last:mb-0">
                                <div className="text-[11px] text-ink-200 font-medium truncate">{r.title}</div>
                                <div className="text-[10px] text-ink-500 truncate">{r.href}</div>
                                {r.snippet && <div className="text-[10px] text-ink-600 mt-0.5 line-clamp-2">{r.snippet}</div>}
                              </a>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                )}
              </div>
            </motion.div>
            </>
          )}
        </AnimatePresence>
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

      {/* ── Export preview modal ──────────────────────────────────── */}
      <AnimatePresence>
        {exportImageUrl && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] bg-black/90 flex flex-col items-center justify-center p-4"
            onClick={closePreview}
          >
            <div className="absolute top-4 right-4 flex items-center gap-2 z-10">
              <button
                onClick={() => {
                  const a = document.createElement("a");
                  a.href = exportImageUrl;
                  a.download = `${groupName}.png`;
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                }}
                className="px-4 py-2 rounded-xl bg-white/10 border border-white/20 text-white text-sm font-medium hover:bg-white/20 transition-colors"
              >
                保存图片
              </button>
              <button
                onClick={closePreview}
                className="w-10 h-10 rounded-full bg-white/10 border border-white/20 flex items-center justify-center text-white hover:bg-white/20 transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            <motion.p
              initial={{ y: -10, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              className="text-white/60 text-sm mb-3"
            >
              长按图片即可分享到微信
            </motion.p>
            <motion.img
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              src={exportImageUrl}
              alt={groupName}
              className="max-h-[85vh] max-w-full rounded-xl shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            />
          </motion.div>
        )}
      </AnimatePresence>
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
