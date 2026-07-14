"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Upload,
  FileText,
  Trash2,
  Play,
  Send,
  CheckCircle,
  AlertCircle,
  Loader2,
  BookOpen,
  Edit,
  Settings,
  Sparkles,
  Zap,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface Doc {
  id: string;
  filename: string;
  title: string;
  content_type: string;
  file_path: string;
  chunk_count: number;
  status: string;
  created_at: string;
  updated_at: string;
}

interface AdvisorDetail {
  id: string;
  name: string;
  title: string;
  category: string;
  era: string;
  avatar: string;
  short_bio: string;
  style: string;
  kb_status: string;
  kb_doc_count: number;
  is_published: boolean;
  visibility: string;
  creator_id: string;
  creator_name?: string;
  documents: Doc[];
  thinking_framework?: {
    analysis?: string;
    decision?: string;
    foresight?: string;
    methodology?: string;
  };
  voice?: {
    tone?: string;
    style?: string;
    length?: string;
    opening?: string;
  };
  core_beliefs?: string[];
  canonical_works?: { title: string; source: string }[];
  knowledge_domain?: {
    known?: string[];
    unknown?: string[];
    attitude_to_unknown?: string;
  };
  skill_config?: Record<string, any>;
}

export default function AdvisorKBPage() {
  const params = useParams();
  const router = useRouter();
  const personaId = params.id as string;

  const [advisor, setAdvisor] = useState<AdvisorDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [textContent, setTextContent] = useState("");
  const [docTitle, setDocTitle] = useState("");
  const [docFilename, setDocFilename] = useState("untitled.txt");
  const [successMsg, setSuccessMsg] = useState("");
  const [error, setError] = useState("");

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [editingMeta, setEditingMeta] = useState(false);
  const [savingMeta, setSavingMeta] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [generatingSkill, setGeneratingSkill] = useState(false);
  const [editingConfig, setEditingConfig] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [editingSkillJson, setEditingSkillJson] = useState(false);
  const [skillJsonText, setSkillJsonText] = useState("");
  const [editConfig, setEditConfig] = useState<Record<string, any>>({});
  const [role, setRole] = useState("user");
  const isViewer = role === "viewer";
  const isAdmin = role === "super_admin" || role === "admin";

  // Structured skill editing
  const [skillForm, setSkillForm] = useState<Record<string, any>>({});
  const [skillFormReady, setSkillFormReady] = useState(false);
  const [savingSkill, setSavingSkill] = useState(false);

  const initSkillForm = (skill: Record<string, any> | undefined) => {
    setSkillForm({
      mental_models: (skill?.mental_models || []).map((m: any) => ({ ...m })),
      heuristics: (skill?.heuristics || []).map((h: any) => ({ ...h })),
      expression: { ...(skill?.expression || { sentence_patterns: [], tone: "", rhythm: "", certainty: "", vocabulary: { preferred: [], avoided: [] } }) },
      anti_patterns: (skill?.anti_patterns || []).map((a: any) => ({ ...a })),
      limitations: [...(skill?.limitations || [])],
    });
    setSkillFormReady(true);
  };

  const saveSkillStructured = async () => {
    setSavingSkill(true); setError("");
    try {
      const merged = {
        ...(advisor?.skill_config || {}),
        mental_models: skillForm.mental_models,
        heuristics: skillForm.heuristics,
        expression: skillForm.expression,
        anti_patterns: skillForm.anti_patterns,
        limitations: skillForm.limitations,
      };
      const res = await fetch(`${API_BASE}/api/admin/advisors/${personaId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ skill_config: merged }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "保存失败"); }
      setSuccessMsg("认知配置已保存");
      fetchAdvisor();
    } catch (e: any) { setError(e.message); }
    finally { setSavingSkill(false); }
  };

  useEffect(() => {
    const t = localStorage.getItem("junshituan_token");
    if (t) {
      try {
        const p = JSON.parse(atob(t.split(".")[1]));
        if (p.role) setRole(p.role);
      } catch {}
    }
  }, []);
  const [metaForm, setMetaForm] = useState({
    name: "",
    title: "",
    category: "",
    era: "",
    avatar: "",
    short_bio: "",
    style: "",
  });

  const token = typeof window !== "undefined" ? localStorage.getItem("junshituan_token") : "";

  const fetchAdvisor = () => {
    fetch(`${API_BASE}/api/admin/advisors/${personaId}?_=${Date.now()}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data: AdvisorDetail) => {
        setAdvisor(data);
        initSkillForm(data.skill_config);
        setMetaForm({
          name: data.name,
          title: data.title,
          category: data.category,
          era: data.era || "",
          avatar: data.avatar || "",
          short_bio: data.short_bio || "",
          style: data.style || "",
        });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchAdvisor();
  }, [personaId]);

  const handleSaveMeta = async () => {
    setSavingMeta(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors/${personaId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(metaForm),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "保存失败");
      }
      setEditingMeta(false);
      fetchAdvisor();
      setSuccessMsg("信息已更新");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSavingMeta(false);
    }
  };

  const handleAvatarFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        // Resize client-side to max 128x128
        const MAX = 128;
        let w = img.width, h = img.height;
        if (w > h) { if (w > MAX) { h = h * MAX / w; w = MAX; } }
        else { if (h > MAX) { w = w * MAX / h; h = MAX; } }
        w = Math.round(w); h = Math.round(h);

        const canvas = document.createElement("canvas");
        canvas.width = w; canvas.height = h;
        const ctx = canvas.getContext("2d")!;
        ctx.drawImage(img, 0, 0, w, h);
        const dataUri = canvas.toDataURL("image/jpeg", 0.75);
        setMetaForm((prev) => ({ ...prev, avatar: dataUri }));
      };
      img.src = ev.target?.result as string;
    };
    reader.readAsDataURL(file);
  };

  const uploadAvatarNow = async (dataUri: string) => {
    setError(""); setSuccessMsg("");
    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors/${personaId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ avatar: dataUri }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "上传失败"); }
      setSuccessMsg("头像已更新");
      fetchAdvisor();
    } catch (e: any) { setError(e.message); }
  };

  const handleAvatarQuickUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
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
        canvas.getContext("2d")!.drawImage(img, 0, 0, w, h);
        const dataUri = canvas.toDataURL("image/jpeg", 0.75);
        setMetaForm((prev) => ({ ...prev, avatar: dataUri }));
        uploadAvatarNow(dataUri);
      };
      img.src = ev.target?.result as string;
    };
    reader.readAsDataURL(file);
  };

  const validateFilename = (name: string): boolean => {
    const ext = name.split(".").pop()?.toLowerCase() || "";
    return ext === "md" || ext === "txt" || ext === "markdown";
  };

  const handleFile = (file: File) => {
    if (!validateFilename(file.name)) {
      setError("仅支持 .md 和 .txt 格式的文件");
      return;
    }
    setError("");
    setSelectedFile(file);
    setDocFilename(file.name);
    const title = file.name.replace(/\.[^.]+$/, "");
    setDocTitle(title);

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setTextContent(content);
    };
    reader.onerror = () => {
      setError("文件读取失败");
    };
    reader.readAsText(file, "UTF-8");
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => setDragOver(false);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const clearFile = () => {
    setSelectedFile(null);
    setTextContent("");
    setDocTitle("");
    setDocFilename("untitled.txt");
  };

  const handleUpload = async () => {
    if (!textContent.trim()) {
      setError("请输入知识内容");
      return;
    }
    const fname = docFilename.trim() || "untitled.txt";
    if (!validateFilename(fname)) {
      setError("仅支持 .md 和 .txt 格式的文件");
      return;
    }
    setError("");
    setSuccessMsg("");
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append("persona_id", personaId);
      formData.append("title", docTitle || fname);
      formData.append("filename", fname);
      formData.append("file_path", fname);
      formData.append("text", textContent);

      const res = await fetch(`${API_BASE}/api/admin/advisors/upload-text`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "上传失败");
      }

      const result = await res.json();

      if (result.overwritten) {
        setSuccessMsg(`"${fname}" 已覆盖。请重新点击消化以更新知识库。`);
      } else {
        setSuccessMsg(`"${fname}" 上传成功。`);
      }

      setTextContent("");
      setDocTitle("");
      setDocFilename("untitled.txt");
      fetchAdvisor();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleIngest = async (force = false) => {
    setIngesting(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors/ingest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ persona_id: personaId, force }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "消化失败");
      }

      const result = await res.json();
      if (result.message) setSuccessMsg(result.message);
      fetchAdvisor();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIngesting(false);
    }
  };

  const handlePublish = async (publish: boolean) => {
    setPublishing(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors/publish`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ persona_id: personaId, publish }),
      });

      if (!res.ok) throw new Error("操作失败");

      fetchAdvisor();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setPublishing(false);
    }
  };

  const handleVisibility = async (visibility: string) => {
    setPublishing(true);
    setError(""); setSuccessMsg("");
    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors/visibility`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ persona_id: personaId, visibility }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "操作失败");
      setSuccessMsg(data.message || "操作成功");
      fetchAdvisor();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setPublishing(false);
    }
  };

  const handleDeleteDoc = async (docId: string) => {
    await fetch(
      `${API_BASE}/api/admin/advisors/${personaId}/documents/${docId}`,
      {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      }
    );
    fetchAdvisor();
  };

  const handleEnrich = async () => {
    setEnriching(true);
    setError(""); setSuccessMsg("");
    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors/${personaId}/enrich`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "充实失败");
      }
      if (data.status === "insufficient_knowledge") {
        setError(`${data.message}\n\n建议补充：${(data.suggested_fields || []).join("、")}`);
      } else {
        setSuccessMsg("配置已由 AI 充实完成");
        fetchAdvisor();
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setEnriching(false);
    }
  };

  const handleGenerateSkill = async () => {
    setGeneratingSkill(true);
    setError(""); setSuccessMsg("");
    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors/${personaId}/skill/generate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "生成失败");
      }
      if (data.status === "insufficient_knowledge") {
        setError(`${data.message}\n\n建议补充：${(data.suggested_fields || []).join("、")}`);
      } else {
        setSuccessMsg("认知操作系统已由 AI 生成");
        fetchAdvisor();
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGeneratingSkill(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true); setError("");
    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors/${personaId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "删除失败");
      router.push("/admin/advisors");
    } catch (e: any) {
      setError(e.message);
      setShowDeleteConfirm(false);
      setDeleting(false);
    }
  };

  const enterConfigEdit = () => {
    if (!advisor) return;
    setEditConfig({
      thinking_framework: { ...(advisor.thinking_framework || {}) },
      voice: { ...(advisor.voice || {}) },
      core_beliefs: [...(advisor.core_beliefs || [])],
      knowledge_domain: { ...(advisor.knowledge_domain || {}), known: [...(advisor.knowledge_domain?.known || [])], unknown: [...(advisor.knowledge_domain?.unknown || [])] },
      canonical_works: [...(advisor.canonical_works || [])],
    });
    setEditingConfig(true);
  };

  const saveConfig = async () => {
    setSavingConfig(true);
    setError("");
    try {
      const body: Record<string, any> = {};
      if (editConfig.thinking_framework) body.thinking_framework = editConfig.thinking_framework;
      if (editConfig.voice) body.voice = editConfig.voice;
      if (editConfig.core_beliefs) body.core_beliefs = editConfig.core_beliefs;
      if (editConfig.knowledge_domain) body.knowledge_domain = editConfig.knowledge_domain;
      if (editConfig.canonical_works) body.canonical_works = editConfig.canonical_works;

      const res = await fetch(`${API_BASE}/api/admin/advisors/${personaId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "保存失败");
      }
      setEditingConfig(false);
      setSuccessMsg("配置已保存");
      fetchAdvisor();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSavingConfig(false);
    }
  };

  const saveSkillJson = async () => {
    setSavingConfig(true);
    setError("");
    try {
      let parsed: any;
      try {
        parsed = JSON.parse(skillJsonText);
      } catch {
        setError("JSON 格式错误，请检查语法");
        setSavingConfig(false);
        return;
      }
      const res = await fetch(`${API_BASE}/api/admin/advisors/${personaId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ skill_config: parsed }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "保存失败");
      }
      setEditingSkillJson(false);
      setSuccessMsg("Skill 已保存");
      fetchAdvisor();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSavingConfig(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-ink-500" size={24} />
      </div>
    );
  }

  if (!advisor) return <div className="text-ink-400">军师不存在</div>;

  return (
    <div className="max-w-4xl mx-auto">
      <button
        onClick={() => router.back()}
        className="flex items-center gap-2 text-ink-400 hover:text-ink-200 mb-6"
      >
        <ArrowLeft size={18} /> 返回列表
      </button>

      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-8">
        <div>
          <h2 className="text-2xl font-display text-ink-100">
            {advisor.name}
            {advisor.visibility === "private" && (
              <span className="ml-2 px-2 py-0.5 text-xs rounded-md bg-amber-900/30 border border-amber-700/40 text-amber-400 align-middle">
                私密
              </span>
            )}
          </h2>
          <p className="text-sm text-ink-500 mt-1">
            {advisor.era} · {advisor.title} · {advisor.category}
          </p>
          {advisor.creator_name && (
            <p className="text-xs text-ink-600 mt-0.5">
              创建者：{advisor.creator_name}
            </p>
          )}
          <p className="text-xs text-ink-600 mt-1 max-w-md">{advisor.short_bio}</p>
        </div>
        <div className="flex gap-2 shrink-0">
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => handleIngest(false)}
            disabled={isViewer || ingesting || advisor.documents.length === 0}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-600/20 border border-amber-600/40 text-amber-400 text-sm font-medium hover:bg-amber-600/30 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {ingesting ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            消化
          </motion.button>

          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => handleIngest(true)}
            disabled={isViewer || ingesting || advisor.documents.length === 0}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-red-600/10 border border-red-600/30 text-red-400 text-sm font-medium hover:bg-red-600/20 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            强制重建
          </motion.button>

          {isAdmin && advisor.visibility !== "private" && (
            advisor.is_published ? (
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => handlePublish(false)}
                disabled={isViewer || publishing}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-red-600/20 border border-red-600/40 text-red-400 text-sm font-medium hover:bg-red-600/30 disabled:opacity-40"
              >
                取消发布
              </motion.button>
            ) : (
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => handlePublish(true)}
                disabled={isViewer || publishing || (advisor.kb_status !== "ready" && !advisor.thinking_framework?.analysis && !advisor.skill_config)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-600/20 border border-emerald-600/40 text-emerald-400 text-sm font-medium hover:bg-emerald-600/30 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Send size={16} />
                发布
              </motion.button>
            )
          )}

          {role === "super_admin" && (
            advisor.visibility === "private" ? (
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => handleVisibility("public")}
                disabled={publishing}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-purple-600/20 border border-purple-600/40 text-purple-400 text-sm font-medium hover:bg-purple-600/30 disabled:opacity-40"
              >
                <Sparkles size={16} />
                推广为公开
              </motion.button>
            ) : (
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => handleVisibility("private")}
                disabled={publishing}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-600/20 border border-amber-600/40 text-amber-400 text-sm font-medium hover:bg-amber-600/30 disabled:opacity-40"
              >
                取消公开
              </motion.button>
            )
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-400 text-sm rounded-xl px-4 py-3 mb-4 whitespace-pre-line">
          {error}
        </div>
      )}
      {successMsg && (
        <div className="bg-emerald-900/30 border border-emerald-700/50 text-emerald-400 text-sm rounded-xl px-4 py-3 mb-4">
          {successMsg}
        </div>
      )}

      {/* Edit Metadata */}
      <div className="mb-6 p-4 rounded-xl bg-ink-900/40 border border-ink-800/40">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <label className="cursor-pointer relative group shrink-0">
              <input type="file" accept="image/*" onChange={handleAvatarQuickUpload} className="hidden" />
              {metaForm.avatar ? (
                <img
                  src={metaForm.avatar}
                  alt="avatar"
                  className="w-10 h-10 rounded-full object-cover bg-ink-800"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                />
              ) : (
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-ink-800 to-ink-700 flex items-center justify-center text-sm font-bold text-ink-200">
                  {advisor.name[0]}
                </div>
              )}
              <div className="absolute inset-0 rounded-full bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                <span className="text-white text-[10px] font-medium">换</span>
              </div>
            </label>
            <div>
              <h4 className="text-sm font-bold text-ink-200">{advisor.name}</h4>
              <p className="text-xs text-ink-500">军师信息</p>
            </div>
          </div>
            {isViewer ? null : (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => { setEditingMeta(!editingMeta); setError(""); setSuccessMsg(""); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-ink-800 border border-ink-700 text-ink-300 text-xs font-medium hover:bg-ink-700 hover:text-ink-200 transition-colors"
                >
                  <Edit size={14} />
                  {editingMeta ? "取消" : "编辑基本信息"}
                </button>
                <button
                  onClick={() => setShowConfig(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-ink-800 border border-ink-700 text-ink-300 text-xs font-medium hover:bg-ink-700 hover:text-ink-200 transition-colors"
                >
                  <Settings size={14} />
                  能力配置
                </button>
              </div>
            )}
        </div>

        {editingMeta && (
          <div className="space-y-3 pt-3 border-t border-ink-800/50">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-ink-400 mb-1">名称</label>
                <input
                  value={metaForm.name}
                  onChange={(e) => setMetaForm({ ...metaForm, name: e.target.value })}
                  className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 focus:outline-none focus:border-ancient-600"
                />
              </div>
              <div>
                <label className="block text-xs text-ink-400 mb-1">称号</label>
                <input
                  value={metaForm.title}
                  onChange={(e) => setMetaForm({ ...metaForm, title: e.target.value })}
                  className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 focus:outline-none focus:border-ancient-600"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-ink-400 mb-1">朝代/时代</label>
                <input
                  value={metaForm.era}
                  onChange={(e) => setMetaForm({ ...metaForm, era: e.target.value })}
                  className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 focus:outline-none focus:border-ancient-600"
                />
              </div>
              <div>
                <label className="block text-xs text-ink-400 mb-1">分类</label>
                <input
                  value={metaForm.category}
                  onChange={(e) => setMetaForm({ ...metaForm, category: e.target.value })}
                  className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 focus:outline-none focus:border-ancient-600"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-ink-400 mb-1">头像</label>
              <div className="flex items-center gap-3">
                <label className="cursor-pointer relative group shrink-0">
                  <input type="file" accept="image/*" onChange={handleAvatarQuickUpload} className="hidden" />
                  {metaForm.avatar ? (
                    <img
                      src={metaForm.avatar}
                      alt="avatar"
                      className="w-12 h-12 rounded-full object-cover bg-ink-800 border border-ink-700"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-gradient-to-br from-ink-800 to-ink-700 flex items-center justify-center text-lg font-bold text-ink-200 border border-ink-700">
                      {metaForm.name[0] || "?"}
                    </div>
                  )}
                  <div className="absolute inset-0 rounded-full bg-black/50 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <span className="text-white text-xs font-medium">点击更换</span>
                  </div>
                </label>
                <span className="text-xs text-ink-500">点击头像即可更换，自动生效</span>
              </div>
            </div>
            <div>
              <label className="block text-xs text-ink-400 mb-1">简介</label>
              <textarea
                value={metaForm.short_bio}
                onChange={(e) => setMetaForm({ ...metaForm, short_bio: e.target.value })}
                rows={2}
                className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600 resize-none"
              />
            </div>
            <div>
              <label className="block text-xs text-ink-400 mb-1">说话风格</label>
              <textarea
                value={metaForm.style}
                onChange={(e) => setMetaForm({ ...metaForm, style: e.target.value })}
                rows={2}
                className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600 resize-none"
              />
            </div>
            <button
              onClick={handleSaveMeta}
              disabled={savingMeta}
              className="w-full py-2 bg-ancient-700 hover:bg-ancient-600 disabled:opacity-50 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors"
            >
              {savingMeta && <Loader2 size={16} className="animate-spin" />}
              保存修改
            </button>
          </div>
        )}
      </div>

      <div className="grid gap-6 sm:grid-cols-2">
        <div className="space-y-4">
          <h3 className="font-bold text-ink-300 flex items-center gap-2">
            <Upload size={18} /> {isViewer ? "知识文档" : "添加知识文档 (.md / .txt)"}
          </h3>

          {isViewer ? (
            <div className="text-center py-8 text-ink-600">
              <BookOpen size={32} className="mx-auto mb-2 opacity-40" />
              <p className="text-sm">只读模式</p>
              <p className="text-xs mt-1">你可以查看已上传的文档</p>
            </div>
          ) : (
          <>
          {/* Drag-drop zone */}
          {!selectedFile ? (
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              className={`relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                dragOver
                  ? "border-ancient-500 bg-ancient-900/20"
                  : "border-ink-700/50 hover:border-ink-600/50 bg-ink-900/30"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".md,.txt,.markdown"
                onChange={handleFileInput}
                className="hidden"
              />
              <div className="flex flex-col items-center gap-2">
                <Upload size={28} className={dragOver ? "text-ancient-400" : "text-ink-600"} />
                <p className="text-sm text-ink-400">
                  拖拽文件到此处，或<span className="text-ancient-400">点击选择</span>
                </p>
                <p className="text-xs text-ink-600">仅支持 .md / .txt 格式</p>
              </div>
            </div>
          ) : (
            <div className="p-3 rounded-xl bg-ink-900/50 border border-ancient-700/30">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <FileText size={16} className="text-ancient-400 shrink-0" />
                  <span className="text-sm text-ink-200 truncate">{selectedFile.name}</span>
                </div>
                <button
                  onClick={clearFile}
                  className="p-1 rounded hover:bg-red-900/30 text-ink-500 hover:text-red-400 transition-colors"
                >
                  <Trash2 size={14} />
                </button>
              </div>
              <div className="text-xs text-ink-600">
                标题: {docTitle} · {selectedFile.size > 1024 ? `${(selectedFile.size / 1024).toFixed(1)} KB` : `${selectedFile.size} B`}
              </div>
            </div>
          )}

          {/* Optional: manual edit of extracted content */}
          {selectedFile && (
            <details className="text-xs text-ink-500">
              <summary className="cursor-pointer hover:text-ink-400">查看/编辑文本内容</summary>
              <textarea
                value={textContent}
                onChange={(e) => setTextContent(e.target.value)}
                rows={8}
                className="w-full mt-2 bg-ink-900/80 border border-ink-700/50 rounded-xl px-4 py-3 text-sm text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-ancient-600/50 font-mono resize-y"
              />
            </details>
          )}

          {/* Fallback: paste mode */}
          {!selectedFile && (
            <details className="text-xs text-ink-500">
              <summary className="cursor-pointer hover:text-ink-400">或手动粘贴文本</summary>
              <div className="mt-2 space-y-3">
                <input
                  type="text"
                  value={docFilename}
                  onChange={(e) => setDocFilename(e.target.value)}
                  placeholder="文件名（如 chuanshilu.md）"
                  className="w-full bg-ink-900/80 border border-ink-700/50 rounded-xl px-4 py-2.5 text-sm text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-ancient-600/50 font-mono"
                />
                <input
                  type="text"
                  value={docTitle}
                  onChange={(e) => setDocTitle(e.target.value)}
                  placeholder="文档标题（如：传习录）"
                  className="w-full bg-ink-900/80 border border-ink-700/50 rounded-xl px-4 py-2.5 text-sm text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-ancient-600/50"
                />
                <textarea
                  value={textContent}
                  onChange={(e) => setTextContent(e.target.value)}
                  placeholder="粘贴 .md 或 .txt 内容到这里..."
                  rows={10}
                  className="w-full bg-ink-900/80 border border-ink-700/50 rounded-xl px-4 py-3 text-sm text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-ancient-600/50 font-mono resize-y"
                />
              </div>
            </details>
          )}

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleUpload}
            disabled={uploading || !textContent.trim() || isViewer}
            className="w-full py-2.5 bg-gradient-to-r from-ancient-600 to-ancient-500 text-white rounded-xl font-medium text-sm disabled:opacity-50"
          >
            {uploading ? (
              <span className="flex items-center justify-center gap-2">
                <Loader2 size={16} className="animate-spin" /> 上传中...
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                <Upload size={16} /> {selectedFile ? `上传 ${selectedFile.name}` : "上传文档"}
              </span>
            )}
          </motion.button>
          </>
          )}
        </div>

        <div className="space-y-3">
          <h3 className="font-bold text-ink-300 flex items-center gap-2">
            <FileText size={18} /> 已上传文档 ({advisor.documents.length})
          </h3>

          {advisor.documents.length === 0 ? (
            <div className="text-center py-12 text-ink-600">
              <BookOpen size={32} className="mx-auto mb-2 opacity-40" />
              <p className="text-sm">暂无文档</p>
              <p className="text-xs mt-1">在左侧粘贴文本并上传</p>
            </div>
          ) : (
            advisor.documents.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center gap-3 p-3 rounded-xl bg-ink-900/50 border border-ink-800/50"
              >
                <FileText size={16} className="text-ink-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm text-ink-200 truncate">
                      {doc.title || doc.filename}
                    </p>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      doc.content_type === "text/markdown"
                        ? "bg-purple-900/30 text-purple-400"
                        : "bg-ink-800 text-ink-500"
                    }`}>
                      {doc.content_type === "text/markdown" ? ".md" : ".txt"}
                    </span>
                  </div>
                  <p className="text-[10px] text-ink-600 mt-0.5">
                    <span className="font-mono">{doc.file_path || doc.filename}</span>
                  </p>
                  <p className="text-[10px] text-ink-600">
                    {doc.status === "ingested" ? (
                      <span className="text-emerald-400">已摄入</span>
                    ) : doc.status === "processing" ? (
                      <span className="text-amber-400">处理中</span>
                    ) : doc.status === "pending_reingest" ? (
                      <span className="text-amber-400">待重新消化</span>
                    ) : (
                      <span className="text-ink-600">待处理</span>
                    )}
                    {doc.chunk_count > 0 && ` · ${doc.chunk_count} 片段`}
                    {doc.updated_at && doc.updated_at !== doc.created_at && (
                      <span className="ml-2 text-ink-700">
                        更新于 {new Date(doc.updated_at).toLocaleDateString("zh-CN")}
                      </span>
                    )}
                  </p>
                </div>
                {!isViewer && (
                  <button
                    onClick={() => handleDeleteDoc(doc.id)}
                    className="p-1.5 rounded-lg hover:bg-red-900/30 text-ink-600 hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            ))
          )}

          {advisor.documents.length > 0 && (
            <div className="mt-4 p-4 rounded-xl bg-ink-900/40 border border-ink-800/40">
              <p className="text-xs text-ink-500 mb-3">
                上传完成后，点击"消化"按钮将文档索引到知识库中。
                消化的知识库状态为"已就绪"后，即可"发布"给用户使用。
              </p>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-ink-500">当前状态：</span>
                {advisor.kb_status === "ready" ? (
                  <span className="flex items-center gap-1 text-emerald-400">
                    <CheckCircle size={12} /> 已就绪
                  </span>
                ) : advisor.kb_status === "ingesting" ? (
                  <span className="flex items-center gap-1 text-amber-400">
                    <Loader2 size={12} className="animate-spin" /> 消化中
                  </span>
                ) : advisor.kb_status === "error" ? (
                  <span className="flex items-center gap-1 text-red-400">
                    <AlertCircle size={12} /> 失败
                  </span>
                ) : (
                  <span className="text-ink-600">未配置</span>
                )}
                <span className="text-ink-600">· {advisor.kb_doc_count} 条索引</span>
                {advisor.is_published && (
                  <span className="text-emerald-400">· 已发布</span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── 危险区域 ──────────────────────────────────────────────── */}
      {!isViewer && (
        <div className="mt-8 p-4 rounded-xl border border-red-800/30 bg-red-900/10">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-bold text-red-400 flex items-center gap-2">
                <Trash2 size={16} /> 危险区域
              </h4>
              <p className="text-xs text-ink-500 mt-1 max-w-lg">
                删除军师将同时清除其知识文档和向量索引。会话记录会保留，但该军师在历史会话中将显示为"已删除"。
              </p>
            </div>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="px-4 py-2 rounded-lg bg-red-600/20 border border-red-600/40 text-red-400 text-sm font-medium hover:bg-red-600/30 transition-colors flex items-center gap-1.5 shrink-0"
            >
              <Trash2 size={16} /> 删除军师
            </button>
          </div>
        </div>
      )}

      {/* ── 删除确认弹窗 ── */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={() => setShowDeleteConfirm(false)}>
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            onClick={(e) => e.stopPropagation()}
            className="bg-ink-900 border border-red-800/50 rounded-2xl p-6 w-full max-w-md mx-4 shadow-2xl"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-900/40 flex items-center justify-center">
                <Trash2 size={20} className="text-red-400" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-red-400">确认删除「{advisor?.name}」</h3>
                <p className="text-xs text-ink-500 mt-0.5">此操作不可撤销</p>
              </div>
            </div>

            <div className="space-y-3 mb-4 text-sm">
              <div className="p-3 rounded-xl bg-red-900/15 border border-red-800/20">
                <p className="text-red-400 font-medium text-xs mb-2">以下内容将被永久删除：</p>
                <ul className="space-y-1 text-xs text-ink-300">
                  <li className="flex items-center gap-1.5">
                    <span className="text-red-400">•</span> 军师「{advisor?.name}」的基本信息和配置
                  </li>
                  <li className="flex items-center gap-1.5">
                    <span className="text-red-400">•</span> {advisor?.documents?.length || 0} 个知识文档
                  </li>
                  <li className="flex items-center gap-1.5">
                    <span className="text-red-400">•</span> {advisor?.kb_doc_count || 0} 条向量索引
                  </li>
                </ul>
              </div>
              <div className="p-3 rounded-xl bg-ink-800/50 border border-ink-700/50">
                <p className="text-ink-400 font-medium text-xs mb-2">以下内容将保留不变：</p>
                <ul className="space-y-1 text-xs text-ink-400">
                  <li className="flex items-center gap-1.5">
                    <span className="text-emerald-400">•</span> 历史会话记录和聊天消息
                  </li>
                  <li className="flex items-center gap-1.5">
                    <span className="text-emerald-400">•</span> 该军师在会话中显示为"已删除"
                  </li>
                </ul>
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="flex-1 px-4 py-2.5 rounded-lg bg-ink-800 border border-ink-700 text-ink-300 text-sm hover:text-ink-200 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex-1 px-4 py-2.5 rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-sm font-bold transition-colors flex items-center justify-center gap-2"
              >
                {deleting ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                确认删除
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* ── 能力配置弹窗 ──────────────────────────────────────────── */}
      {showConfig && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center pt-10 pb-10 overflow-auto bg-black/70"
          onClick={(e) => { if (e.target === e.currentTarget) setShowConfig(false); }}
        >
          <div className="bg-[#1a1a2e] border border-ink-700 rounded-2xl w-full max-w-3xl max-h-[85vh] overflow-auto shadow-2xl">
            <div className="sticky top-0 bg-[#1a1a2e] border-b border-ink-800 px-6 py-4 flex items-center justify-between z-10">
              <div>
                <h3 className="text-lg font-bold text-ink-100">{advisor.name} · 能力配置</h3>
                <p className="text-xs text-ink-500 mt-0.5">
                  思维框架 · 语言风格 · 认知操作系统
                  {editingConfig && <span className="text-amber-400 ml-2">编辑中</span>}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {editingConfig ? (
                  <>
                    <button onClick={saveConfig} disabled={savingConfig}
                      className="px-3 py-1.5 rounded-lg bg-emerald-600/30 border border-emerald-600/50 text-emerald-400 text-xs font-medium hover:bg-emerald-600/40 disabled:opacity-50 flex items-center gap-1">
                      {savingConfig ? <Loader2 size={12} className="animate-spin" /> : null}保存
                    </button>
                    <button onClick={() => setEditingConfig(false)}
                      className="px-3 py-1.5 rounded-lg bg-ink-800 border border-ink-700 text-ink-400 text-xs hover:text-ink-200">
                      取消
                    </button>
                  </>
                ) : !isViewer ? (
                  <button onClick={enterConfigEdit}
                    className="px-3 py-1.5 rounded-lg bg-ink-800 border border-ink-700 text-ink-300 text-xs hover:text-ink-200 hover:border-ink-600 transition-colors">
                    编辑配置
                  </button>
                ) : null}
                <button
                  onClick={() => setShowConfig(false)}
                  className="p-2 rounded-lg hover:bg-ink-800 text-ink-400 hover:text-ink-200 transition-colors"
                >
                  ✕
                </button>
              </div>
            </div>

            <div className="p-6 space-y-6">
              {/* ── 消息提示 ── */}
              {error && (
                <div className="bg-red-900/30 border border-red-700/50 text-red-400 text-sm rounded-xl px-4 py-3 whitespace-pre-line">
                  {error}
                </div>
              )}
              {successMsg && (
                <div className="bg-emerald-900/30 border border-emerald-700/50 text-emerald-400 text-sm rounded-xl px-4 py-3">
                  {successMsg}
                </div>
              )}

              {/* ── AI 操作按钮 ── */}
              {!isViewer && (
              <div className="flex gap-3">
                <button
                  onClick={handleEnrich}
                  disabled={enriching}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600/20 border border-blue-600/40 text-blue-400 text-sm font-medium hover:bg-blue-600/30 disabled:opacity-50 transition-colors"
                >
                  {enriching ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
                  AI 充实人格配置
                </button>
                <button
                  onClick={handleGenerateSkill}
                  disabled={generatingSkill}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-purple-600/20 border border-purple-600/40 text-purple-400 text-sm font-medium hover:bg-purple-600/30 disabled:opacity-50 transition-colors"
                >
                  {generatingSkill ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
                  AI 生成认知操作系统
                </button>
              </div>
              )}

              {/* ── 思维框架 ── */}
              <Section title="思维框架" icon="🧠">
                {editingConfig ? (
                  <div className="space-y-3">
                    <EditField label="分析方式" value={editConfig.thinking_framework?.analysis || ""}
                      onChange={(v) => setEditConfig(prev => ({ ...prev, thinking_framework: { ...prev.thinking_framework, analysis: v } }))} />
                    <EditField label="决策模式" value={editConfig.thinking_framework?.decision || ""}
                      onChange={(v) => setEditConfig(prev => ({ ...prev, thinking_framework: { ...prev.thinking_framework, decision: v } }))} />
                    <EditField label="预见习惯" value={editConfig.thinking_framework?.foresight || ""}
                      onChange={(v) => setEditConfig(prev => ({ ...prev, thinking_framework: { ...prev.thinking_framework, foresight: v } }))} />
                    <EditField label="方法论" value={editConfig.thinking_framework?.methodology || ""}
                      onChange={(v) => setEditConfig(prev => ({ ...prev, thinking_framework: { ...prev.thinking_framework, methodology: v } }))} />
                  </div>
                ) : advisor.thinking_framework?.analysis ? (
                  <div className="space-y-2">
                    <KV label="分析方式" value={advisor.thinking_framework.analysis} />
                    <KV label="决策模式" value={advisor.thinking_framework.decision} />
                    <KV label="预见习惯" value={advisor.thinking_framework.foresight} />
                    <KV label="方法论" value={advisor.thinking_framework.methodology} />
                  </div>
                ) : (
                  <EmptyHint text="尚未配置，点击上方「AI 充实人格配置」自动生成" />
                )}
              </Section>

              {/* ── 语言风格 ── */}
              <Section title="语言风格" icon="🗣">
                {editingConfig ? (
                  <div className="space-y-3">
                    <EditField label="语气" value={editConfig.voice?.tone || ""}
                      onChange={(v) => setEditConfig(prev => ({ ...prev, voice: { ...prev.voice, tone: v } }))} />
                    <EditField label="表达方式" value={editConfig.voice?.style || ""}
                      onChange={(v) => setEditConfig(prev => ({ ...prev, voice: { ...prev.voice, style: v } }))} />
                    <EditField label="篇幅偏好" value={editConfig.voice?.length || "中等"}
                      onChange={(v) => setEditConfig(prev => ({ ...prev, voice: { ...prev.voice, length: v } }))} />
                    <EditField label="开场方式" value={editConfig.voice?.opening || ""}
                      onChange={(v) => setEditConfig(prev => ({ ...prev, voice: { ...prev.voice, opening: v } }))} />
                  </div>
                ) : advisor.voice?.tone ? (
                  <div className="space-y-2">
                    <KV label="语气" value={advisor.voice.tone} />
                    <KV label="表达方式" value={advisor.voice.style} />
                    <KV label="篇幅偏好" value={advisor.voice.length} />
                    <KV label="开场方式" value={advisor.voice.opening} />
                  </div>
                ) : (
                  <EmptyHint text="尚未配置" />
                )}
              </Section>

              {/* ── 核心信条 ── */}
              <Section title="核心信条" icon="📜">
                {editingConfig ? (
                  <div className="space-y-2">
                    {(editConfig.core_beliefs || []).map((b: string, i: number) => (
                      <div key={i} className="flex items-center gap-2">
                        <span className="text-ancient-400 text-xs w-4">{i + 1}.</span>
                        <input
                          value={b}
                          onChange={(e) => {
                            const n = [...(editConfig.core_beliefs || [])];
                            n[i] = e.target.value;
                            setEditConfig(prev => ({ ...prev, core_beliefs: n }));
                          }}
                          className="flex-1 bg-ink-800 border border-ink-700 rounded-lg px-3 py-1.5 text-sm text-ink-100 focus:outline-none focus:border-ancient-600"
                        />
                        <button onClick={() => {
                          const n = (editConfig.core_beliefs || []).filter((_: any, j: number) => j !== i);
                          setEditConfig(prev => ({ ...prev, core_beliefs: n }));
                        }} className="text-ink-600 hover:text-red-400 text-xs">✕</button>
                      </div>
                    ))}
                    <button onClick={() => {
                      setEditConfig(prev => ({ ...prev, core_beliefs: [...(prev.core_beliefs || []), ""] }));
                    }} className="text-xs text-ancient-400 hover:text-ancient-300">
                      + 添加信条
                    </button>
                  </div>
                ) : advisor.core_beliefs && advisor.core_beliefs.length > 0 ? (
                  <ul className="space-y-1.5">
                    {advisor.core_beliefs.map((b, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-ink-200">
                        <span className="text-ancient-400 mt-0.5 shrink-0">▸</span>
                        {b}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyHint text="尚未配置" />
                )}
              </Section>

              {/* ── 知识边界 ── */}
              <Section title="知识边界" icon="🌐">
                {editingConfig ? (
                  <div className="space-y-3">
                    <div>
                      <span className="text-xs text-emerald-400 font-medium block mb-1.5">擅长领域</span>
                      <div className="space-y-1.5">
                        {(editConfig.knowledge_domain?.known || []).map((k: string, i: number) => (
                          <div key={i} className="flex items-center gap-2">
                            <input value={k} onChange={(e) => {
                              const n = [...(editConfig.knowledge_domain?.known || [])];
                              n[i] = e.target.value;
                              setEditConfig(prev => ({ ...prev, knowledge_domain: { ...prev.knowledge_domain, known: n } }));
                            }} className="flex-1 bg-ink-800 border border-ink-700 rounded-lg px-3 py-1.5 text-sm text-ink-100 focus:outline-none focus:border-emerald-600" />
                            <button onClick={() => {
                              const n = (editConfig.knowledge_domain?.known || []).filter((_: any, j: number) => j !== i);
                              setEditConfig(prev => ({ ...prev, knowledge_domain: { ...prev.knowledge_domain, known: n } }));
                            }} className="text-ink-600 hover:text-red-400 text-xs">✕</button>
                          </div>
                        ))}
                        <button onClick={() => {
                          setEditConfig(prev => ({ ...prev, knowledge_domain: { ...prev.knowledge_domain, known: [...(prev.knowledge_domain?.known || []), ""] } }));
                        }} className="text-xs text-emerald-400 hover:text-emerald-300">+ 添加</button>
                      </div>
                    </div>
                    <div>
                      <span className="text-xs text-red-400 font-medium block mb-1.5">不熟悉领域</span>
                      <div className="space-y-1.5">
                        {(editConfig.knowledge_domain?.unknown || []).map((k: string, i: number) => (
                          <div key={i} className="flex items-center gap-2">
                            <input value={k} onChange={(e) => {
                              const n = [...(editConfig.knowledge_domain?.unknown || [])];
                              n[i] = e.target.value;
                              setEditConfig(prev => ({ ...prev, knowledge_domain: { ...prev.knowledge_domain, unknown: n } }));
                            }} className="flex-1 bg-ink-800 border border-ink-700 rounded-lg px-3 py-1.5 text-sm text-ink-100 focus:outline-none focus:border-red-600" />
                            <button onClick={() => {
                              const n = (editConfig.knowledge_domain?.unknown || []).filter((_: any, j: number) => j !== i);
                              setEditConfig(prev => ({ ...prev, knowledge_domain: { ...prev.knowledge_domain, unknown: n } }));
                            }} className="text-ink-600 hover:text-red-400 text-xs">✕</button>
                          </div>
                        ))}
                        <button onClick={() => {
                          setEditConfig(prev => ({ ...prev, knowledge_domain: { ...prev.knowledge_domain, unknown: [...(prev.knowledge_domain?.unknown || []), ""] } }));
                        }} className="text-xs text-red-400 hover:text-red-300">+ 添加</button>
                      </div>
                    </div>
                    <EditField label="对未知的态度" value={editConfig.knowledge_domain?.attitude_to_unknown || ""}
                      onChange={(v) => setEditConfig(prev => ({ ...prev, knowledge_domain: { ...prev.knowledge_domain, attitude_to_unknown: v } }))} />
                  </div>
                ) : advisor.knowledge_domain?.known?.length ? (
                  <div className="space-y-3">
                    <div>
                      <span className="text-xs text-emerald-400 font-medium">擅长领域</span>
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {(advisor.knowledge_domain.known || []).map((k, i) => (
                          <span key={i} className="px-2 py-0.5 rounded-md bg-emerald-900/30 text-emerald-400 text-xs border border-emerald-800/30">
                            {k}
                          </span>
                        ))}
                      </div>
                    </div>
                    {advisor.knowledge_domain.unknown && advisor.knowledge_domain.unknown.length > 0 && (
                      <div>
                        <span className="text-xs text-red-400 font-medium">不熟悉领域</span>
                        <div className="flex flex-wrap gap-1.5 mt-1.5">
                          {advisor.knowledge_domain.unknown.map((k, i) => (
                            <span key={i} className="px-2 py-0.5 rounded-md bg-red-900/20 text-red-400 text-xs border border-red-800/30">
                              {k}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {advisor.knowledge_domain.attitude_to_unknown && (
                      <KV label="对未知的态度" value={advisor.knowledge_domain.attitude_to_unknown} />
                    )}
                  </div>
                ) : (
                  <EmptyHint text="尚未配置" />
                )}
              </Section>

              {/* ── 代表著作 ── */}
              <Section title="代表著作" icon="📚">
                {editingConfig ? (
                  <div className="space-y-2">
                    {(editConfig.canonical_works || []).map((w: any, i: number) => (
                      <div key={i} className="flex items-center gap-2">
                        <input value={w.title || ""} onChange={(e) => {
                          const n = [...(editConfig.canonical_works || [])];
                          n[i] = { ...n[i], title: e.target.value };
                          setEditConfig(prev => ({ ...prev, canonical_works: n }));
                        }} placeholder="书名/篇名" className="flex-1 bg-ink-800 border border-ink-700 rounded-lg px-3 py-1.5 text-sm text-ink-100 focus:outline-none focus:border-ancient-600" />
                        <input value={w.source || ""} onChange={(e) => {
                          const n = [...(editConfig.canonical_works || [])];
                          n[i] = { ...n[i], source: e.target.value };
                          setEditConfig(prev => ({ ...prev, canonical_works: n }));
                        }} placeholder="出处" className="w-32 bg-ink-800 border border-ink-700 rounded-lg px-3 py-1.5 text-sm text-ink-100 focus:outline-none focus:border-ancient-600" />
                        <button onClick={() => {
                          const n = (editConfig.canonical_works || []).filter((_: any, j: number) => j !== i);
                          setEditConfig(prev => ({ ...prev, canonical_works: n }));
                        }} className="text-ink-600 hover:text-red-400 text-xs">✕</button>
                      </div>
                    ))}
                    <button onClick={() => {
                      setEditConfig(prev => ({ ...prev, canonical_works: [...(prev.canonical_works || []), { title: "", source: "" }] }));
                    }} className="text-xs text-ancient-400 hover:text-ancient-300">+ 添加著作</button>
                  </div>
                ) : advisor.canonical_works && advisor.canonical_works.length > 0 ? (
                  <ul className="space-y-2">
                    {advisor.canonical_works.map((w, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm">
                        <span className="text-ancient-400 mt-0.5 shrink-0">▸</span>
                        <div>
                          <span className="text-ink-200">{w.title}</span>
                          <span className="text-ink-600 ml-2 text-xs">{w.source}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyHint text="尚未配置" />
                )}
              </Section>

              {/* ── 认知操作系统 (Skill) ── */}
              <Section title="认知操作系统" icon="⚙️">
                {!skillFormReady ? (
                  <EmptyHint text="加载中..." />
                ) : (
                  <div className="space-y-5">
                    {/* Admin-only raw JSON toggle */}
                    {isAdmin && (
                      <div className="flex items-center gap-2">
                        {editingSkillJson ? (
                          <div className="flex-1 space-y-3">
                            <textarea
                              value={skillJsonText}
                              onChange={(e) => setSkillJsonText(e.target.value)}
                              rows={16}
                              className="w-full bg-ink-950 border border-ink-700 rounded-xl px-4 py-3 text-xs text-ink-100 font-mono focus:outline-none focus:border-purple-600 resize-y"
                              spellCheck={false}
                            />
                            <div className="flex gap-2">
                              <button onClick={saveSkillJson} disabled={savingConfig}
                                className="px-4 py-1.5 rounded-lg bg-purple-600/30 border border-purple-600/50 text-purple-400 text-xs font-medium hover:bg-purple-600/40 disabled:opacity-50">
                                {savingConfig ? <Loader2 size={12} className="animate-spin inline mr-1" /> : null}保存 JSON
                              </button>
                              <button onClick={() => setEditingSkillJson(false)}
                                className="px-4 py-1.5 rounded-lg bg-ink-800 text-ink-400 text-xs hover:text-ink-200">取消</button>
                            </div>
                          </div>
                        ) : (
                          <button
                            onClick={() => { setSkillJsonText(JSON.stringify(advisor?.skill_config || {}, null, 2)); setEditingSkillJson(true); }}
                            className="px-3 py-1.5 rounded-lg bg-ink-800 border border-ink-700 text-ink-500 text-xs hover:text-ink-300 transition-colors"
                          >
                            编辑原始 JSON
                          </button>
                        )}
                        {!editingSkillJson && (
                          <button onClick={saveSkillStructured} disabled={savingSkill || isViewer}
                            className="px-4 py-1.5 rounded-lg bg-emerald-600/20 border border-emerald-600/40 text-emerald-400 text-xs font-medium hover:bg-emerald-600/30 disabled:opacity-40 flex items-center gap-1">
                            {savingSkill ? <Loader2 size={12} className="animate-spin" /> : null}保存配置
                          </button>
                        )}
                      </div>
                    )}

                    {/* ── 心智模型 ── */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-amber-400 font-medium">
                          心智模型 ({skillForm.mental_models?.length || 0})
                        </span>
                        {!isViewer && (
                          <button onClick={() => {
                            setSkillForm((prev: any) => ({ ...prev, mental_models: [...(prev.mental_models || []), { name: "", summary: "", application: "", limitation: "" }] }));
                          }} className="text-xs text-ancient-400 hover:text-ancient-300">+ 添加</button>
                        )}
                      </div>
                      <div className="space-y-2">
                        {(skillForm.mental_models || []).map((m: any, i: number) => (
                          <div key={i} className="p-3 rounded-xl bg-ink-900/50 border border-ink-800/50">
                            <div className="flex items-center justify-between mb-1.5">
                              {isViewer ? (
                                <h5 className="text-sm font-bold text-ink-100">{m.name || "（未命名）"}</h5>
                              ) : (
                                <input value={m.name || ""} placeholder="模型名称"
                                  onChange={(e) => { const n = [...skillForm.mental_models]; n[i] = { ...n[i], name: e.target.value }; setSkillForm((prev: any) => ({ ...prev, mental_models: n })); }}
                                  className="flex-1 bg-transparent border-b border-ink-700 text-sm font-bold text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-500" />
                              )}
                              {!isViewer && (
                                <button onClick={() => {
                                  setSkillForm((prev: any) => ({ ...prev, mental_models: prev.mental_models.filter((_: any, j: number) => j !== i) }));
                                }} className="text-ink-600 hover:text-red-400 text-xs ml-2">✕</button>
                              )}
                            </div>
                            {isViewer ? (
                              <>
                                {m.summary && <p className="text-xs text-ink-400 mt-0.5">{m.summary}</p>}
                                {m.application && <p className="text-xs text-emerald-400 mt-1"><span className="text-ink-600">应用：</span>{m.application}</p>}
                                {m.limitation && <p className="text-xs text-red-400 mt-0.5"><span className="text-ink-600">局限：</span>{m.limitation}</p>}
                              </>
                            ) : (
                              <div className="space-y-1.5 mt-2">
                                <input value={m.summary || ""} placeholder="一句话描述这个思维模式"
                                  onChange={(e) => { const n = [...skillForm.mental_models]; n[i] = { ...n[i], summary: e.target.value }; setSkillForm((prev: any) => ({ ...prev, mental_models: n })); }}
                                  className="w-full bg-ink-950/50 border border-ink-800 rounded px-2 py-1 text-xs text-ink-200 placeholder-ink-600 focus:outline-none focus:border-ink-700" />
                                <input value={m.application || ""} placeholder="如何应用？"
                                  onChange={(e) => { const n = [...skillForm.mental_models]; n[i] = { ...n[i], application: e.target.value }; setSkillForm((prev: any) => ({ ...prev, mental_models: n })); }}
                                  className="w-full bg-ink-950/50 border border-ink-800 rounded px-2 py-1 text-xs text-emerald-300 placeholder-ink-600 focus:outline-none focus:border-ink-700" />
                                <input value={m.limitation || ""} placeholder="局限是什么？"
                                  onChange={(e) => { const n = [...skillForm.mental_models]; n[i] = { ...n[i], limitation: e.target.value }; setSkillForm((prev: any) => ({ ...prev, mental_models: n })); }}
                                  className="w-full bg-ink-950/50 border border-ink-800 rounded px-2 py-1 text-xs text-red-300 placeholder-ink-600 focus:outline-none focus:border-ink-700" />
                              </div>
                            )}
                          </div>
                        ))}
                        {(!skillForm.mental_models || skillForm.mental_models.length === 0) && (
                          <p className="text-xs text-ink-600 italic py-2">如：第一性原理、二阶思维、系统思考...</p>
                        )}
                      </div>
                    </div>

                    {/* ── 决策启发式 ── */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-amber-400 font-medium">
                          决策启发式 ({skillForm.heuristics?.length || 0})
                        </span>
                        {!isViewer && (
                          <button onClick={() => {
                            setSkillForm((prev: any) => ({ ...prev, heuristics: [...(prev.heuristics || []), { name: "", trigger: "", action: "" }] }));
                          }} className="text-xs text-ancient-400 hover:text-ancient-300">+ 添加</button>
                        )}
                      </div>
                      <div className="space-y-1.5">
                        {(skillForm.heuristics || []).map((h: any, i: number) => (
                          <div key={i} className="flex items-center gap-2 text-sm group">
                            {isViewer ? (
                              <>
                                <span className="text-ancient-400">▸ </span>
                                <span className="font-medium text-ink-200">{h.name || "未命名"}</span>
                                <span className="text-ink-500">：{h.trigger} → {h.action}</span>
                              </>
                            ) : (
                              <div className="flex-1 flex items-center gap-2 flex-wrap">
                                <input value={h.name || ""} placeholder="名称"
                                  onChange={(e) => { const n = [...skillForm.heuristics]; n[i] = { ...n[i], name: e.target.value }; setSkillForm((prev: any) => ({ ...prev, heuristics: n })); }}
                                  className="w-24 bg-ink-950/50 border border-ink-800 rounded px-2 py-1 text-xs text-ink-100 placeholder-ink-600 focus:outline-none focus:border-amber-600/50" />
                                <span className="text-ink-600 text-xs">触发</span>
                                <input value={h.trigger || ""} placeholder="场景"
                                  onChange={(e) => { const n = [...skillForm.heuristics]; n[i] = { ...n[i], trigger: e.target.value }; setSkillForm((prev: any) => ({ ...prev, heuristics: n })); }}
                                  className="flex-1 min-w-[80px] bg-ink-950/50 border border-ink-800 rounded px-2 py-1 text-xs text-ink-200 placeholder-ink-600 focus:outline-none focus:border-amber-600/50" />
                                <span className="text-ink-600 text-xs">→</span>
                                <input value={h.action || ""} placeholder="行动"
                                  onChange={(e) => { const n = [...skillForm.heuristics]; n[i] = { ...n[i], action: e.target.value }; setSkillForm((prev: any) => ({ ...prev, heuristics: n })); }}
                                  className="flex-1 min-w-[80px] bg-ink-950/50 border border-ink-800 rounded px-2 py-1 text-xs text-ink-200 placeholder-ink-600 focus:outline-none focus:border-amber-600/50" />
                              </div>
                            )}
                            {!isViewer && (
                              <button onClick={() => {
                                setSkillForm((prev: any) => ({ ...prev, heuristics: prev.heuristics.filter((_: any, j: number) => j !== i) }));
                              }} className="text-ink-600 hover:text-red-400 text-xs opacity-0 group-hover:opacity-100 transition-opacity">✕</button>
                            )}
                          </div>
                        ))}
                        {(!skillForm.heuristics || skillForm.heuristics.length === 0) && (
                          <p className="text-xs text-ink-600 italic py-2">如：遇到不确定时先做小规模测试、情绪激动时延迟24小时再做决定...</p>
                        )}
                      </div>
                    </div>

                    {/* ── 表达风格 ── */}
                    <div>
                      <span className="text-xs text-amber-400 font-medium block mb-2">表达风格</span>
                      <div className="grid grid-cols-2 gap-2">
                        {["tone", "rhythm", "certainty"].map((field) => (
                          <div key={field}>
                            <span className="text-[10px] text-ink-500">{field === "tone" ? "语气" : field === "rhythm" ? "节奏" : "确定性"}</span>
                            {isViewer ? (
                              <p className="text-sm text-ink-200 mt-0.5">{skillForm.expression?.[field] || "—"}</p>
                            ) : (
                              <input value={skillForm.expression?.[field] || ""} placeholder={field === "tone" ? "如：沉稳、犀利" : field === "rhythm" ? "如：短句为主" : "如：结论明确"}
                                onChange={(e) => setSkillForm((prev: any) => ({ ...prev, expression: { ...prev.expression, [field]: e.target.value } }))}
                                className="w-full mt-0.5 bg-ink-950/50 border border-ink-800 rounded px-2 py-1 text-xs text-ink-200 placeholder-ink-600 focus:outline-none focus:border-ink-700" />
                            )}
                          </div>
                        ))}
                      </div>
                      <div className="mt-2">
                        <span className="text-[10px] text-ink-500">常用句式（回车添加）</span>
                        {isViewer ? (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {(skillForm.expression?.sentence_patterns || []).map((p: string, i: number) => (
                              <code key={i} className="px-2 py-0.5 rounded bg-ink-800 text-ink-300 text-xs font-mono">{p}</code>
                            ))}
                          </div>
                        ) : (
                          <textarea
                            value={(skillForm.expression?.sentence_patterns || []).join("\n")}
                            onChange={(e) => setSkillForm((prev: any) => ({ ...prev, expression: { ...prev.expression, sentence_patterns: e.target.value.split("\n").filter(Boolean) } }))}
                            rows={3}
                            placeholder="一行一个句式，如：&#10;我认为...&#10;从长远来看...&#10;关键在于..."
                            className="w-full mt-1 bg-ink-950/50 border border-ink-800 rounded-lg px-3 py-2 text-xs text-ink-200 placeholder-ink-600 focus:outline-none focus:border-ink-700 font-mono resize-y"
                          />
                        )}
                      </div>
                    </div>

                    {/* ── 反例黑名单 ── */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-red-400 font-medium">
                          反例黑名单 ({skillForm.anti_patterns?.length || 0})
                        </span>
                        {!isViewer && (
                          <button onClick={() => {
                            setSkillForm((prev: any) => ({ ...prev, anti_patterns: [...(prev.anti_patterns || []), { pattern: "", fix: "" }] }));
                          }} className="text-xs text-ancient-400 hover:text-ancient-300">+ 添加</button>
                        )}
                      </div>
                      <div className="space-y-1.5">
                        {(skillForm.anti_patterns || []).map((ap: any, i: number) => (
                          <div key={i} className="flex items-center gap-2 text-sm group">
                            {isViewer ? (
                              <>
                                <span className="text-red-400">❌ {ap.pattern || "未指定"}</span>
                                {ap.fix && <span className="text-emerald-400">→ ✅ {ap.fix}</span>}
                              </>
                            ) : (
                              <div className="flex-1 flex items-center gap-2 flex-wrap">
                                <span className="text-red-400 text-xs shrink-0">❌</span>
                                <input value={ap.pattern || ""} placeholder="不该做的事"
                                  onChange={(e) => { const n = [...skillForm.anti_patterns]; n[i] = { ...n[i], pattern: e.target.value }; setSkillForm((prev: any) => ({ ...prev, anti_patterns: n })); }}
                                  className="flex-1 min-w-[100px] bg-ink-950/50 border border-ink-800 rounded px-2 py-1 text-xs text-ink-200 placeholder-ink-600 focus:outline-none focus:border-red-600/50" />
                                <span className="text-emerald-400 text-xs shrink-0">→ ✅</span>
                                <input value={ap.fix || ""} placeholder="正确做法"
                                  onChange={(e) => { const n = [...skillForm.anti_patterns]; n[i] = { ...n[i], fix: e.target.value }; setSkillForm((prev: any) => ({ ...prev, anti_patterns: n })); }}
                                  className="flex-1 min-w-[80px] bg-ink-950/50 border border-ink-800 rounded px-2 py-1 text-xs text-ink-200 placeholder-ink-600 focus:outline-none focus:border-emerald-600/50" />
                              </div>
                            )}
                            {!isViewer && (
                              <button onClick={() => {
                                setSkillForm((prev: any) => ({ ...prev, anti_patterns: prev.anti_patterns.filter((_: any, j: number) => j !== i) }));
                              }} className="text-ink-600 hover:text-red-400 text-xs opacity-0 group-hover:opacity-100 transition-opacity">✕</button>
                            )}
                          </div>
                        ))}
                        {(!skillForm.anti_patterns || skillForm.anti_patterns.length === 0) && (
                          <p className="text-xs text-ink-600 italic py-2">如：不做没有数据支撑的判断、不替别人做决定...</p>
                        )}
                      </div>
                    </div>

                    {/* ── 诚实边界 ── */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-ink-400 font-medium">
                          诚实边界 ({skillForm.limitations?.length || 0})
                        </span>
                        {!isViewer && (
                          <button onClick={() => {
                            setSkillForm((prev: any) => ({ ...prev, limitations: [...(prev.limitations || []), ""] }));
                          }} className="text-xs text-ancient-400 hover:text-ancient-300">+ 添加</button>
                        )}
                      </div>
                      <div className="space-y-1">
                        {(skillForm.limitations || []).map((l: string, i: number) => (
                          <div key={i} className="flex items-center gap-2 group">
                            <span className="text-ink-600 text-xs">·</span>
                            {isViewer ? (
                              <span className="text-xs text-ink-400">{l || "（空）"}</span>
                            ) : (
                              <input value={l} placeholder="我不擅长的领域..."
                                onChange={(e) => { const n = [...skillForm.limitations]; n[i] = e.target.value; setSkillForm((prev: any) => ({ ...prev, limitations: n })); }}
                                className="flex-1 bg-ink-950/50 border border-ink-800 rounded px-2 py-1 text-xs text-ink-200 placeholder-ink-600 focus:outline-none focus:border-ink-700" />
                            )}
                            {!isViewer && (
                              <button onClick={() => {
                                setSkillForm((prev: any) => ({ ...prev, limitations: prev.limitations.filter((_: any, j: number) => j !== i) }));
                              }} className="text-ink-600 hover:text-red-400 text-xs opacity-0 group-hover:opacity-100 transition-opacity">✕</button>
                            )}
                          </div>
                        ))}
                        {(!skillForm.limitations || skillForm.limitations.length === 0) && (
                          <p className="text-xs text-ink-600 italic py-2">如：不了解2025年之后的事件、不擅长技术实现细节...</p>
                        )}
                      </div>
                    </div>

                    {/* Save button for non-admin users */}
                    {!isAdmin && !isViewer && (
                      <button onClick={saveSkillStructured} disabled={savingSkill}
                        className="w-full py-2 rounded-lg bg-emerald-600/20 border border-emerald-600/40 text-emerald-400 text-sm font-medium hover:bg-emerald-600/30 disabled:opacity-40 flex items-center justify-center gap-2">
                        {savingSkill ? <Loader2 size={14} className="animate-spin" /> : null}保存认知配置
                      </button>
                    )}
                  </div>
                )}
              </Section>

              {/* ── 原始 JSON ── */}
              <details className="text-xs">
                <summary className="cursor-pointer text-ink-500 hover:text-ink-400 py-1">
                  查看原始 JSON 数据
                </summary>
                <pre className="mt-2 p-3 rounded-xl bg-ink-950 border border-ink-800 overflow-auto max-h-80 text-ink-400 text-[11px] leading-relaxed">
                  {JSON.stringify(
                    {
                      thinking_framework: advisor.thinking_framework,
                      voice: advisor.voice,
                      core_beliefs: advisor.core_beliefs,
                      canonical_works: advisor.canonical_works,
                      knowledge_domain: advisor.knowledge_domain,
                      skill_config: advisor.skill_config,
                    },
                    null,
                    2
                  )}
                </pre>
              </details>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── 辅助组件 ── */

function Section({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <div className="p-4 rounded-xl bg-ink-900/40 border border-ink-800/50">
      <h4 className="text-sm font-bold text-ink-200 mb-3 flex items-center gap-2">
        <span>{icon}</span> {title}
      </h4>
      {children}
    </div>
  );
}

function KV({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div>
      <span className="text-[10px] text-ink-500">{label}</span>
      <p className="text-sm text-ink-200 mt-0.5">{value}</p>
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <p className="text-xs text-ink-600 italic py-3">{text}</p>
  );
}

function EditField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <span className="text-[10px] text-ink-500">{label}</span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={2}
        className="w-full mt-0.5 bg-ink-800 border border-ink-700 rounded-lg px-3 py-1.5 text-sm text-ink-100 focus:outline-none focus:border-ancient-600 resize-none"
      />
    </div>
  );
}
