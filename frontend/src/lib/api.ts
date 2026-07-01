import { Advisor, Council, SessionDetail } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("junshituan_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function ensureAuth(): Promise<void> {
  const token = localStorage.getItem("junshituan_token");
  if (!token) {
    // Auto-register anonymous user
    const anonId = "anon_" + Math.random().toString(36).slice(2, 10);
    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: anonId,
        password: anonId,
        display_name: "访客",
      }),
    });
    if (res.ok) {
      const data = await res.json();
      localStorage.setItem("junshituan_token", data.access_token);
    }
  }
}

export async function fetchAdvisors(): Promise<Advisor[]> {
  const res = await fetch(`${API_BASE}/api/advisors`);
  if (!res.ok) throw new Error("Failed to fetch advisors");
  return res.json();
}

export async function createCouncil(
  advisorIds: string[],
  title?: string
): Promise<Council> {
  await ensureAuth();
  const res = await fetch(`${API_BASE}/api/council`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ advisor_ids: advisorIds, title: title || "" }),
  });
  if (!res.ok) throw new Error("Failed to create council");
  return res.json();
}

export async function fetchSessions(): Promise<SessionDetail[]> {
  await ensureAuth();
  const res = await fetch(`${API_BASE}/api/council/sessions`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchSessionDetail(
  sessionId: string
): Promise<SessionDetail | null> {
  await ensureAuth();
  const res = await fetch(`${API_BASE}/api/council/sessions/${sessionId}`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) return null;
  return res.json();
}

export async function* askCouncil(
  sessionId: string,
  question: string
): AsyncGenerator<{ advisorId: string; advisorName?: string; content: string; done: boolean; metadata?: Record<string, any> }> {
  await ensureAuth();
  const res = await fetch(`${API_BASE}/api/council/sessions/${sessionId}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ question }),
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
        const data = JSON.parse(line.slice(6));
        yield data;
      }
    }
  }
}
