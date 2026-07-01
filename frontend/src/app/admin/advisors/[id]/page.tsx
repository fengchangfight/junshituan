"use client";

import { useState, useEffect } from "react";
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
  documents: Doc[];
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

  const [editingMeta, setEditingMeta] = useState(false);
  const [savingMeta, setSavingMeta] = useState(false);
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
    fetch(`${API_BASE}/api/admin/advisors/${personaId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data: AdvisorDetail) => {
        setAdvisor(data);
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

  const validateFilename = (name: string): boolean => {
    const ext = name.split(".").pop()?.toLowerCase() || "";
    return ext === "md" || ext === "txt" || ext === "markdown";
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

  const handleIngest = async () => {
    setIngesting(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/api/admin/advisors/ingest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ persona_id: personaId }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "消化失败");
      }

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
          <h2 className="text-2xl font-display text-ink-100">{advisor.name}</h2>
          <p className="text-sm text-ink-500 mt-1">
            {advisor.era} · {advisor.title} · {advisor.category}
          </p>
          <p className="text-xs text-ink-600 mt-1 max-w-md">{advisor.short_bio}</p>
        </div>
        <div className="flex gap-2 shrink-0">
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={handleIngest}
            disabled={ingesting || advisor.documents.length === 0}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-600/20 border border-amber-600/40 text-amber-400 text-sm font-medium hover:bg-amber-600/30 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {ingesting ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            消化
          </motion.button>

          {advisor.is_published ? (
            <motion.button
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => handlePublish(false)}
              disabled={publishing}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-red-600/20 border border-red-600/40 text-red-400 text-sm font-medium hover:bg-red-600/30 disabled:opacity-40"
            >
              取消发布
            </motion.button>
          ) : (
            <motion.button
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => handlePublish(true)}
              disabled={publishing || advisor.kb_status !== "ready"}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-600/20 border border-emerald-600/40 text-emerald-400 text-sm font-medium hover:bg-emerald-600/30 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Send size={16} />
              发布
            </motion.button>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-400 text-sm rounded-xl px-4 py-3 mb-4">
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
            <div>
              <h4 className="text-sm font-bold text-ink-200">{advisor.name}</h4>
              <p className="text-xs text-ink-500">军师信息</p>
            </div>
          </div>
          <button
            onClick={() => { setEditingMeta(!editingMeta); setError(""); setSuccessMsg(""); }}
            className="text-xs text-ink-400 hover:text-ink-300 transition-colors"
          >
            {editingMeta ? "取消" : "编辑信息"}
          </button>
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
              <label className="block text-xs text-ink-400 mb-1">头像 URL</label>
              <input
                value={metaForm.avatar}
                onChange={(e) => setMetaForm({ ...metaForm, avatar: e.target.value })}
                placeholder="例如: /avatars/sun-zi.png 或 https://..."
                className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600"
              />
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
            <Upload size={18} /> 添加知识文档 (.md / .txt)
          </h3>

          <div>
            <label className="text-xs text-ink-500 mb-1 block">文件名（唯一标识）</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={docFilename}
                onChange={(e) => setDocFilename(e.target.value)}
                placeholder="chuanshilu.md"
                className="flex-1 bg-ink-900/80 border border-ink-700/50 rounded-xl px-4 py-2.5 text-sm text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-ancient-600/50 font-mono"
              />
            </div>
            <p className="text-[10px] text-ink-600 mt-1">
              同名文件上传会覆盖旧版本，ID不变，触发重新消化
            </p>
          </div>

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
            rows={12}
            className="w-full bg-ink-900/80 border border-ink-700/50 rounded-xl px-4 py-3 text-sm text-ink-100 placeholder:text-ink-600 focus:outline-none focus:border-ancient-600/50 font-mono resize-y"
          />

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleUpload}
            disabled={uploading || !textContent.trim()}
            className="w-full py-2.5 bg-gradient-to-r from-ancient-600 to-ancient-500 text-white rounded-xl font-medium text-sm disabled:opacity-50"
          >
            {uploading ? (
              <span className="flex items-center justify-center gap-2">
                <Loader2 size={16} className="animate-spin" /> 上传中...
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                <Upload size={16} /> 上传文档
              </span>
            )}
          </motion.button>
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
                <button
                  onClick={() => handleDeleteDoc(doc.id)}
                  className="p-1.5 rounded-lg hover:bg-red-900/30 text-ink-600 hover:text-red-400 transition-colors"
                >
                  <Trash2 size={14} />
                </button>
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
    </div>
  );
}
