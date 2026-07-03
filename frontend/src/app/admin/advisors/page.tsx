"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, CheckCircle, AlertCircle, Loader2, Circle, Plus, X, Sparkles, Zap } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface Advisor {
  id: string;
  name: string;
  title: string;
  category: string;
  era: string;
  avatar: string;
  kb_status: string;
  kb_doc_count: number;
  is_published: boolean;
  visibility: string;
  creator_id: string;
}

const CATEGORIES = ["军事家", "哲学家", "政治家", "文学家", "科学家", "企业家", "其他"];

export default function AdminAdvisorsPage() {
  const [advisors, setAdvisors] = useState<Advisor[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const [showSmartCreate, setShowSmartCreate] = useState(false);
  const [smartName, setSmartName] = useState("");
  const [smartCreating, setSmartCreating] = useState(false);
  const [smartError, setSmartError] = useState("");
  const [role, setRole] = useState("user");
  const isViewer = role === "viewer";

  const [form, setForm] = useState({
    name: "",
    title: "",
    category: "其他",
    era: "",
    avatar: "",
    short_bio: "",
    style: "",
  });

  const fetchAdvisors = () => {
    const token = localStorage.getItem("junshituan_token");
    fetch(`${API_BASE}/api/admin/advisors`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setAdvisors)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchAdvisors();
    const t = localStorage.getItem("junshituan_token");
    if (t) {
      try {
        const p = JSON.parse(atob(t.split(".")[1]));
        if (p.role) setRole(p.role);
      } catch {}
    }
  }, []);

  const handleCreate = async () => {
    if (!form.name || !form.title) {
      setCreateError("名称、称号为必填项");
      return;
    }
    setCreating(true);
    setCreateError("");
    const token = localStorage.getItem("junshituan_token");
    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "创建失败");
      }
      setShowCreate(false);
      setForm({ name: "", title: "", category: "其他", era: "", avatar: "", short_bio: "", style: "" });
      setLoading(true);
      fetchAdvisors();
    } catch (e: any) {
      setCreateError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleSmartCreate = async () => {
    if (!smartName.trim()) {
      setSmartError("请输入军师名称");
      return;
    }
    setSmartCreating(true);
    setSmartError("");
    const token = localStorage.getItem("junshituan_token");
    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors/smart-create`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name: smartName.trim() }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "创建失败");
      }
      setShowSmartCreate(false);
      setSmartName("");
      setLoading(true);
      fetchAdvisors();
    } catch (e: any) {
      setSmartError(e.message);
    } finally {
      setSmartCreating(false);
    }
  };

  const handleAvatarFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        const MAX = 128;
        let w = img.width, h = img.height;
        if (w > h) { if (w > MAX) { h = h * MAX / w; w = MAX; } }
        else { if (h > MAX) { w = w * MAX / h; h = MAX; } }
        w = Math.round(w); h = Math.round(h);
        const canvas = document.createElement("canvas");
        canvas.width = w; canvas.height = h;
        const ctx = canvas.getContext("2d")!;
        ctx.drawImage(img, 0, 0, w, h);
        setForm((prev) => ({ ...prev, avatar: canvas.toDataURL("image/jpeg", 0.75) }));
      };
      img.src = ev.target?.result as string;
    };
    reader.readAsDataURL(file);
  };

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
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-display text-ink-200">
            {isViewer ? "知识库管理（只读）" : role === "user" ? "我的军师" : "知识库管理"}
          </h2>
          <p className="text-sm text-ink-500 mt-1">
            {role === "user"
              ? "管理你创建的私人军师，补充知识文档后即可在议事厅中使用"
              : "管理每个军师的知识文档，消化后发布为可用状态"}
          </p>
        </div>
        {!isViewer && (
        <div className="flex gap-2">
          <button
            onClick={() => { setShowCreate(true); setCreateError(""); }}
            className="flex items-center gap-2 px-4 py-2 bg-ancient-700 hover:bg-ancient-600 text-white text-sm rounded-lg transition-colors"
          >
            <Plus size={16} />
            手动创建
          </button>
          <button
            onClick={() => { setShowSmartCreate(true); setSmartError(""); }}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white text-sm rounded-lg transition-all"
          >
            <Sparkles size={16} />
            智能创建
          </button>
        </div>
        )}
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="bg-ink-900 border border-ink-700 rounded-xl p-6 w-full max-w-lg mx-4 max-h-[80vh] overflow-y-auto"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-ink-100">创建新军师</h3>
              <button onClick={() => setShowCreate(false)} className="text-ink-500 hover:text-ink-300">
                <X size={20} />
              </button>
            </div>

            {createError && (
              <div className="mb-4 p-3 bg-red-900/30 border border-red-800/50 rounded-lg text-red-400 text-sm">
                {createError}
              </div>
            )}

            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-ink-400 mb-1">名称 *</label>
                  <input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="例如: 孙子"
                    className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
                  />
                </div>
                <div>
                  <label className="block text-xs text-ink-400 mb-1">称号 *</label>
                  <input
                    value={form.title}
                    onChange={(e) => setForm({ ...form, title: e.target.value })}
                    placeholder="例如: 军事家·兵圣"
                    className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-ink-400 mb-1">分类</label>
                  <select
                    value={form.category}
                    onChange={(e) => setForm({ ...form, category: e.target.value })}
                    className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 focus:outline-none focus:border-ancient-600"
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-ink-400 mb-1">朝代/时代</label>
                  <input
                    value={form.era}
                    onChange={(e) => setForm({ ...form, era: e.target.value })}
                    placeholder="例如: 春秋"
                    className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs text-ink-400 mb-1">头像</label>
                <div className="flex items-center gap-2">
                  {form.avatar && (
                    <img src={form.avatar} alt="preview" className="w-10 h-10 rounded-full object-cover bg-ink-800" />
                  )}
                  <label className="flex-1 cursor-pointer bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-xs text-ink-400 hover:text-ink-200 text-center transition-colors">
                    <input type="file" accept="image/*" onChange={handleAvatarFile} className="hidden" />
                    {form.avatar ? "更换头像" : "上传头像（自动压缩）"}
                  </label>
                </div>
              </div>
              <div>
                <label className="block text-xs text-ink-400 mb-1">简介</label>
                <textarea
                  value={form.short_bio}
                  onChange={(e) => setForm({ ...form, short_bio: e.target.value })}
                  rows={2}
                  placeholder="一两句话介绍这位军师..."
                  className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600 resize-none"
                />
              </div>
              <div>
                <label className="block text-xs text-ink-400 mb-1">说话风格</label>
                <textarea
                  value={form.style}
                  onChange={(e) => setForm({ ...form, style: e.target.value })}
                  rows={2}
                  placeholder="例如: 言简意赅，多用兵法比喻..."
                  className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600 resize-none"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowCreate(false)}
                className="flex-1 px-4 py-2 bg-ink-800 hover:bg-ink-700 text-ink-300 text-sm rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                disabled={creating}
                className="flex-1 px-4 py-2 bg-ancient-700 hover:bg-ancient-600 disabled:opacity-50 text-white text-sm rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                {creating ? <Loader2 size={16} className="animate-spin" /> : null}
                创建
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* Smart Create Modal */}
      {showSmartCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="bg-ink-900 border border-ink-700 rounded-xl p-6 w-full max-w-md mx-4"
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-bold text-ink-100 flex items-center gap-2">
                  <Zap size={20} className="text-purple-400" />
                  智能创建军师
                </h3>
                <p className="text-xs text-ink-500 mt-1">
                  AI 会根据人物名自动补全所有配置：思维框架、语言风格、信条、认知操作系统等
                </p>
              </div>
              <button onClick={() => setShowSmartCreate(false)} className="text-ink-500 hover:text-ink-300">
                <X size={20} />
              </button>
            </div>

            {smartError && (
              <div className="mb-4 p-3 bg-red-900/30 border border-red-800/50 rounded-lg text-red-400 text-sm">
                {smartError}
              </div>
            )}

            <div className="space-y-4">
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
                AI 将自动生成：人物身份、思维框架、核心信条、知识边界、代表著作、
                以及完整的认知操作系统（心智模型、决策启发式、表达 DNA 等）。
                你可以事后再补充头像、上传著作进行消化。
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowSmartCreate(false)}
                className="flex-1 px-4 py-2 bg-ink-800 hover:bg-ink-700 text-ink-300 text-sm rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleSmartCreate}
                disabled={smartCreating}
                className="flex-1 px-4 py-2 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 disabled:opacity-50 text-white text-sm rounded-lg transition-all flex items-center justify-center gap-2"
              >
                {smartCreating ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    AI 正在生成...
                  </>
                ) : (
                  <>
                    <Zap size={16} />
                    一键生成
                  </>
                )}
              </button>
            </div>
          </motion.div>
        </div>
      )}

      <div className="space-y-3">
        {advisors.map((adv) => (
          <Link key={adv.id} href={`/admin/advisors/${adv.id}`}>
            <motion.div
              whileHover={{ scale: 1.01 }}
              className="flex items-center gap-4 p-4 rounded-xl bg-ink-900/50 border border-ink-800/50 hover:border-ancient-700/30 transition-all"
            >
              {adv.avatar ? (
                <img
                  src={adv.avatar}
                  alt={adv.name}
                  className="w-10 h-10 rounded-full object-cover shrink-0 bg-ink-800"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                    (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden");
                  }}
                />
              ) : null}
              <div className={`w-10 h-10 rounded-full bg-gradient-to-br from-ink-800 to-ink-700 flex items-center justify-center text-sm font-bold text-ink-200 shrink-0 ${adv.avatar ? "hidden" : ""}`}>
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
                  {adv.visibility === "private" ? (
                    <span className="text-[10px] bg-purple-900/40 text-purple-400 px-2 py-0.5 rounded-full">
                      私人
                    </span>
                  ) : adv.is_published ? (
                    <span className="text-[10px] bg-emerald-900/40 text-emerald-400 px-2 py-0.5 rounded-full">
                      已发布
                    </span>
                  ) : adv.kb_status === "ready" ? (
                    <span className="text-[10px] bg-amber-900/40 text-amber-400 px-2 py-0.5 rounded-full">
                      未发布
                    </span>
                  ) : (
                    <span className="text-[10px] bg-ink-800 text-ink-500 px-2 py-0.5 rounded-full">
                      未配置
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
