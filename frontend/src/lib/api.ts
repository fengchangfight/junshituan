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

export function getUserInfo(): { username: string } | null {
  const token = getToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      removeToken();
      return null;
    }
    return { username: payload.username || "" };
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
  const res = await fetch(`${API_BASE}/api/advisors?_t=${Date.now()}`, { cache: "no-store" });
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
  targetAdvisorId?: string
): AsyncGenerator<{ advisor_id: string; advisor_name?: string; content: string; done: boolean; metadata?: Record<string, any> }> {
  const body: Record<string, string> = { question };
  if (targetAdvisorId) body.target_advisor_id = targetAdvisorId;
  const res = await fetch(`${API_BASE}/api/council/sessions/${sessionId}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(body),
  });

  console.log("[askCouncil] fetch response ok, starting SSE reader...");
  if (!res.ok || !res.body) throw new Error("Failed to ask council");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    console.log("[askCouncil] reader.read() chunk:", { done, size: value?.length || 0 });
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6));
        console.log("[askCouncil] SSE event:", data.advisor_id, "content_len:", data.content?.length || 0, "done:", data.done);
        yield data;
      }
    }
  }
  console.log("[askCouncil] SSE stream ended");
}
