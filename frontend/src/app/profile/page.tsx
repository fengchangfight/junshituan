"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { getToken, changePassword, fetchUsers, quickCreateUser, deleteUserById } from "@/lib/api";
import { ArrowLeft, Loader2, Camera, UserPlus, Trash2, Shield } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function ProfilePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [displayName, setDisplayName] = useState("");
  const [avatar, setAvatar] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("");
  const [hasPassword, setHasPassword] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);

  // Admin user management
  const [users, setUsers] = useState<Array<{id: string; username: string; display_name: string; role: string; created_at: string}>>([]);
  const [showUsers, setShowUsers] = useState(false);
  const [creatingUser, setCreatingUser] = useState(false);
  const [createdInfo, setCreatedInfo] = useState<{username: string; password: string} | null>(null);
  const isSuperAdmin = role === "super_admin";

  const loadUsers = () => {
    if (!isSuperAdmin) return;
    fetchUsers().then(setUsers).catch(() => {});
  };

  useEffect(() => { loadUsers(); }, [role]);

  const handleQuickCreate = async () => {
    setCreatingUser(true); setError("");
    try {
      const info = await quickCreateUser();
      setCreatedInfo(info);
      loadUsers();
    } catch (e: any) { setError(e.message); }
    finally { setCreatingUser(false); }
  };

  const handleDeleteUser = async (userId: string, username: string) => {
    if (!confirm(`确定删除用户 ${username}？此操作不可撤销。`)) return;
    try { await deleteUserById(userId); loadUsers(); }
    catch (e: any) { setError(e.message); }
  };

  const [curPwd, setCurPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const token = typeof window !== "undefined" ? localStorage.getItem("junshituan_token") : "";

  useEffect(() => {
    fetch(`${API_BASE}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json())
      .then((d) => {
        setDisplayName(d.display_name || "");
        setAvatar(d.avatar_url || "");
        setUsername(d.username || "");
        setRole(d.role || "");
        setHasPassword(d.has_password !== false);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

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
        setAvatar(canvas.toDataURL("image/jpeg", 0.75));
      };
      img.src = ev.target?.result as string;
    };
    reader.readAsDataURL(file);
  };

  const handleSaveProfile = async () => {
    setSaving(true); setError(""); setSuccess("");
    try {
      await fetch(`${API_BASE}/api/auth/profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ display_name: displayName, avatar_url: avatar }),
      });
      setSuccess("个人信息已保存");
    } catch (e: any) {
      setError(e.message || "保存失败");
    } finally { setSaving(false); }
  };

  const handleSavePwd = async () => {
    if (!newPwd || newPwd.length < 6) { setError("新密码至少6位"); return; }
    if (newPwd !== confirmPwd) { setError("两次输入的密码不一致"); return; }
    setSaving(true); setError(""); setSuccess("");
    try {
      await changePassword(curPwd, newPwd);
      setSuccess("密码已更新");
      setCurPwd(""); setNewPwd(""); setConfirmPwd("");
    } catch (e: any) {
      setError(e.message);
    } finally { setSaving(false); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-ink-500" size={24} />
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto px-4 py-8">
      <button onClick={() => router.back()} className="flex items-center gap-2 text-ink-400 hover:text-ink-200 mb-6">
        <ArrowLeft size={18} /> 返回
      </button>

      <h2 className="text-xl font-display text-ink-200 mb-6">个人资料</h2>

      {error && <div className="mb-4 p-3 bg-red-900/20 border border-red-800/30 rounded-xl text-red-400 text-xs">{error}</div>}
      {success && <div className="mb-4 p-3 bg-emerald-900/20 border border-emerald-800/30 rounded-xl text-emerald-400 text-xs">{success}</div>}

      {/* Avatar */}
      <div className="flex flex-col items-center mb-6">
        <div className="relative group cursor-pointer" onClick={() => fileRef.current?.click()}>
          {avatar ? (
            <img src={avatar} className="w-20 h-20 rounded-full object-cover border-2 border-ink-700" />
          ) : (
            <div className="w-20 h-20 rounded-full bg-gradient-to-br from-ancient-600 to-ancient-800 flex items-center justify-center text-white text-2xl font-bold border-2 border-ink-700">
              {(displayName || username)[0]?.toUpperCase() || "?"}
            </div>
          )}
          <div className="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
            <Camera size={20} className="text-white" />
          </div>
        </div>
        <input ref={fileRef} type="file" accept="image/*" onChange={handleAvatarFile} className="hidden" />
        <p className="text-xs text-ink-500 mt-2">点击头像更换</p>
      </div>

      {/* Profile form */}
      <div className="space-y-4 mb-8 p-4 rounded-xl bg-ink-900/40 border border-ink-800/40">
        <div>
          <label className="text-xs text-ink-400 mb-1 block">手机号</label>
          <input type="text" value={username} disabled
            className="w-full bg-ink-800/50 border border-ink-700/50 rounded-lg px-3 py-2 text-sm text-ink-400 cursor-not-allowed" />
          <p className="text-[10px] text-ink-600 mt-0.5">手机号注册后不可修改</p>
        </div>
        <div>
          <label className="text-xs text-ink-400 mb-1 block">显示名称</label>
          <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)}
            placeholder="设置你的昵称"
            className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600" />
        </div>
        <button onClick={handleSaveProfile} disabled={saving}
          className="w-full py-2.5 bg-ancient-700 hover:bg-ancient-600 disabled:opacity-50 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors">
          {saving ? <Loader2 size={16} className="animate-spin" /> : null}
          保存资料
        </button>
      </div>

      {/* Password */}
      <h3 className="text-sm font-bold text-ink-300 mb-3">修改密码</h3>
      <div className="space-y-3 p-4 rounded-xl bg-ink-900/40 border border-ink-800/40">
        <div>
          <label className="text-xs text-ink-400 mb-1 block">原密码</label>
          <input type="password" value={curPwd} onChange={(e) => setCurPwd(e.target.value)}
            placeholder={hasPassword ? "输入原密码" : "未设置密码"}
            disabled={!hasPassword}
            className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600 disabled:opacity-40 disabled:cursor-not-allowed" />
        </div>
        <div>
          <label className="text-xs text-ink-400 mb-1 block">新密码（至少6位）</label>
          <input type="password" value={newPwd} onChange={(e) => setNewPwd(e.target.value)}
            placeholder="输入新密码"
            className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600" />
        </div>
        <div>
          <label className="text-xs text-ink-400 mb-1 block">确认新密码</label>
          <input type="password" value={confirmPwd} onChange={(e) => setConfirmPwd(e.target.value)}
            placeholder="再次输入新密码"
            className="w-full bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder-ink-600 focus:outline-none focus:border-ancient-600" />
        </div>
        <button onClick={handleSavePwd} disabled={saving || !newPwd || !confirmPwd}
          className="w-full py-2.5 bg-ancient-700 hover:bg-ancient-600 disabled:opacity-50 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors">
          {saving ? <Loader2 size={16} className="animate-spin" /> : null}
          更新密码
        </button>
      </div>

      {/* ── User Management (super admin only) ── */}
      {isSuperAdmin && (
        <div className="mt-8 p-4 rounded-xl bg-ink-900/40 border border-amber-800/30">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-amber-400 flex items-center gap-1.5">
              <Shield size={14} /> 用户管理
            </h3>
            <div className="flex items-center gap-2">
              {createdInfo && (
                <span className="text-[10px] text-emerald-400 bg-emerald-900/20 px-2 py-0.5 rounded">
                  已创建：{createdInfo.username} / {createdInfo.password}
                </span>
              )}
              <button onClick={handleQuickCreate} disabled={creatingUser}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-amber-600/20 border border-amber-600/40 text-amber-400 text-xs hover:bg-amber-600/30 disabled:opacity-50 transition-colors">
                {creatingUser ? <Loader2 size={12} className="animate-spin" /> : <UserPlus size={12} />}
                快速添加
              </button>
              <button onClick={() => { setShowUsers(!showUsers); loadUsers(); }}
                className="text-xs text-ink-500 hover:text-ink-300 transition-colors">
                {showUsers ? "收起" : `展开 (${users.length})`}
              </button>
            </div>
          </div>
          <p className="text-[10px] text-ink-500 mb-2">随机用户名 + 统一密码 demo123，用于快速添加测试账号。</p>
          {showUsers && (
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {users.map((u) => (
                <div key={u.id} className="flex items-center justify-between py-1.5 px-2 rounded-lg hover:bg-ink-800/30 text-xs">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-ink-300 truncate">{u.display_name || u.username}</span>
                    <span className="text-ink-600 text-[10px]">{u.role}</span>
                  </div>
                  <button onClick={() => handleDeleteUser(u.id, u.username)}
                    className="p-1 rounded text-ink-600 hover:text-red-400 hover:bg-red-900/20 transition-colors">
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
