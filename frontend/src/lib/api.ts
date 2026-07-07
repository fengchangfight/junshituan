import { Advisor, Council, SessionDetail } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("junshituan_token");
}

export function setToken(token: string) {
  localStorage.setItem("junshituan_token", token);
}

export function removeToken() {
  localStorage.removeItem("junshituan_token");
}

export function getUserInfo(): { username: string; isAdmin: boolean; role: string } | null {
  const token = getToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      removeToken();
      return null;
    }
    const role = payload.role || "user";
    const isAdmin = role === "super_admin" || role === "admin" || role === "viewer";
    return { username: payload.username || "", isAdmin, role };
  } catch {
    return null;
  }
}

function getAuthHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ── Auth ────────────────────────────────────────────────────────────

export async function login(username: string, password: string) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "登录失败");
  }
  const data = await res.json();
  setToken(data.access_token);
  return data;
}

export async function sendCode(phone: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/send-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "发送失败");
  }
}

export async function loginPhone(phone: string, code: string) {
  const res = await fetch(`${API_BASE}/api/auth/login-phone`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, code }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "验证失败");
  }
  const data = await res.json();
  setToken(data.access_token);
  return data;
}

export async function changePassword(currentPassword: string, newPassword: string) {
  const res = await fetch(`${API_BASE}/api/auth/change-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "修改失败");
  }
}

export async function register(username: string, password: string, displayName?: string) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, display_name: displayName || username }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "注册失败");
  }
  const data = await res.json();
  setToken(data.access_token);
  return data;
}

// ── Advisors ────────────────────────────────────────────────────────

export async function fetchAdvisors(): Promise<Advisor[]> {
  const res = await fetch(`${API_BASE}/api/advisors`, {
    cache: "no-store",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch advisors");
  return res.json();
}

// ── Council / Sessions ──────────────────────────────────────────────

export async function createCouncil(
  advisorIds: string[],
  title?: string
): Promise<Council> {
  const res = await fetch(`${API_BASE}/api/council`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ advisor_ids: advisorIds, title: title || "" }),
  });
  if (!res.ok) throw new Error("请先登录");
  return res.json();
}

export async function fetchSessions(): Promise<SessionDetail[]> {
  const res = await fetch(`${API_BASE}/api/council/sessions`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchSessionDetail(
  sessionId: string
): Promise<SessionDetail | null> {
  const res = await fetch(`${API_BASE}/api/council/sessions/${sessionId}`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) return null;
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/council/sessions/${sessionId}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error("删除失败");
}

export async function renameSession(sessionId: string, title: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/council/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("重命名失败");
}

export async function addAdvisorsToSession(
  sessionId: string,
  advisorIds: string[]
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/council/sessions/${sessionId}/advisors`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({ advisor_ids: advisorIds }),
  });
  if (!res.ok) throw new Error("添加失败");
}

export async function* askCouncil(
  sessionId: string,
  question: string,
  targetAdvisorIds?: string[],
  useWebSearch?: boolean,
): AsyncGenerator<{ advisor_id: string; advisor_name?: string; content: string; done: boolean; metadata?: Record<string, any> }> {
  const body: Record<string, unknown> = { question, use_web_search: useWebSearch ?? true };
  if (targetAdvisorIds && targetAdvisorIds.length > 0) body.target_advisor_ids = targetAdvisorIds;
  const res = await fetch(`${API_BASE}/api/council/sessions/${sessionId}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(body),
  });

  if (!res.ok || !res.body) throw new Error("Failed to ask council");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          yield JSON.parse(line.slice(6));
        } catch {
          // Skip malformed SSE data lines (heartbeats, partial chunks)
        }
      }
    }
  }
}
