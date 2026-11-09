const TOKEN_KEY = "lira.token";
const USER_KEY = "lira.user";

export type User = { id: number; email: string; name: string; role: string; display_name?: string };

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function getUser(): User | null {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}
export function saveSession(token: string, user: User) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}
export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401 && !path.includes("/auth/login")) {
    clearSession();
    location.href = "/login";
    throw new ApiError("登录已失效", 401);
  }
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`;
    try {
      const data = await res.json();
      msg = data?.detail ?? data?.error?.message ?? msg;
      if (Array.isArray(msg)) msg = msg.map((m: any) => m.msg).join("；");
    } catch {
      /* ignore */
    }
    throw new ApiError(String(msg), res.status);
  }
  return (await res.json()) as T;
}

const get = <T,>(p: string) => request<T>(p);
const post = <T,>(p: string, body?: unknown) =>
  request<T>(p, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const patch = <T,>(p: string, body: unknown) =>
  request<T>(p, { method: "PATCH", body: JSON.stringify(body) });

export type MetricDef = {
  name: string;
  label: string;
  unit: "currency" | "ratio" | "count";
  group: string;
  formula: string;
  ratio: boolean;
};
export type MetricCompare = {
  metric: string;
  label: string;
  unit: string;
  ratio: boolean;
  current: number;
  previous: number;
  delta: number;
  pct: number;
  has_baseline: boolean;
  days: number;
};
export type Insight = {
  id?: number;
  headline: string;
  drivers: { factor: string; impact: number; share: number }[];
  confidence: number;
  evidence: string[];
  actions: { title: string; expected: string }[];
  model?: string;
  created_at?: string;
};
export type RunStep = {
  idx: number;
  agent_key: string;
  agent_name?: string;
  thought: string;
  tool: string;
  args: Record<string, unknown>;
  observation: Record<string, unknown>;
  latency_ms: number;
  tokens: number;
};
export type Run = {
  id: number;
  kind: string;
  title: string;
  status: string;
  trigger: string;
  model: string;
  started_at: string;
  finished_at: string | null;
  latency_ms: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  result: { insight?: Insight; facts?: Record<string, unknown>; error?: string | null };
  steps: RunStep[];
  headline?: string;
};

export const api = {
  login: (email: string, password: string) =>
    post<{ token: string; user: User }>("/api/auth/login", { email, password }),
  me: () => get<User>("/api/auth/me"),
  changePassword: (old_password: string, new_password: string) =>
    post<{ ok: boolean }>("/api/auth/password", { old_password, new_password }),

  catalogue: () => get<{ version: string; metrics: MetricDef[]; groups: string[] }>("/api/dashboard/catalogue"),
  overview: (days: number) => get<{ days: number; metrics: Record<string, MetricCompare> }>(`/api/dashboard/overview?days=${days}`),
  series: (metric: string, days: number) =>
    get<{ metric: string; points: { date: string; value: number | null }[] }>(`/api/dashboard/series?metric=${metric}&days=${days}`),
  rankings: (metric: string, days: number, asc: boolean, limit = 8) =>
    get<{ items: any[] }>(`/api/dashboard/rankings?metric=${metric}&days=${days}&asc=${asc}&limit=${limit}`),
  categories: (days: number) => get<{ items: any[] }>(`/api/dashboard/categories?days=${days}`),
  anomalies: (days: number) => get<{ items: any[] }>(`/api/dashboard/anomalies?days=${days}`),
  insight: (scope = "dashboard") => get<{ insight: Insight | null }>(`/api/dashboard/insight?scope=${scope}`),
  refreshInsight: () => post<{ run_id: number; latency_ms: number; insight: Insight | null; steps: RunStep[] }>("/api/dashboard/insight/refresh"),

  runs: (limit = 20) => get<{ items: Run[] }>(`/api/work/runs?limit=${limit}`),
  createRun: (question: string, kind = "diagnosis") => post<Run>("/api/work/runs", { question, kind }),
  run: (id: number) => get<Run>(`/api/work/runs/${id}`),

  agents: () => get<{ items: any[] }>("/api/agents"),
  toggleAgent: (key: string, enabled: boolean) => patch<{ key: string; enabled: boolean }>(`/api/agents/${key}`, { enabled }),
  tools: () => get<{ items: any[] }>("/api/agents/tools/all"),
  kb: () => get<{ items: { id: number; slug: string; title: string; source: string; chunks: number }[] }>("/api/agents/kb"),
  reindex: () => post<{ chunks: number }>("/api/agents/kb/reindex"),
  evalCases: () => get<{ items: any[] }>("/api/agents/evals/cases"),
  evalHistory: (limit = 8) => get<{ items: any[] }>(`/api/agents/evals/history?limit=${limit}`),
  runEval: () => post<any>("/api/agents/evals/run"),

  settings: () => get<any>("/api/settings"),
  addModel: (body: any) => post<{ id: number }>("/api/settings/models", body),
  setDefaultModel: (id: number) => post<{ ok: boolean }>("/api/settings/models/default", { id }),
  users: () => get<{ items: any[]; max: number }>("/api/settings/users"),
  createUser: (body: { email: string; display_name: string; password: string; role: string }) =>
    post<{ id: number }>("/api/settings/users", body),
  patchUser: (id: number, body: { status?: string; role?: string }) =>
    patch<{ ok: boolean }>(`/api/settings/users/${id}`, body),
  resetPassword: (id: number, new_password: string) =>
    post<{ ok: boolean }>(`/api/settings/users/${id}/password`, { new_password }),
  audit: () => get<{ items: any[] }>("/api/settings/audit"),

  connectors: () => get<{ items: any[]; kinds: string[] }>("/api/settings/connectors"),
  addConnector: (body: { kind: string; name: string; endpoint: string; config?: any }) =>
    post<{ id: number }>("/api/settings/connectors", body),
  toggleConnector: (id: number, enabled: boolean) =>
    patch<{ id: number; enabled: boolean }>(`/api/settings/connectors/${id}`, { enabled }),
  deleteConnector: (id: number) => request<{ ok: boolean }>(`/api/settings/connectors/${id}`, { method: "DELETE" }),
  testConnector: (id: number) =>
    post<{ ok: boolean; message: string; ms: number }>(`/api/settings/connectors/${id}/test`),
  syncConnector: (id: number, rows: any[]) =>
    post<any>(`/api/settings/connectors/${id}/sync`, { rows }),
};

/* ---------- 格式化 ---------- */
export function money(v: number | null | undefined, compact = true) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  if (compact) {
    if (abs >= 1e8) return `${(v / 1e8).toFixed(2)} 亿`;
    if (abs >= 1e4) return `${(v / 1e4).toFixed(2)} 万`;
  }
  return `¥${v.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}
export function pct(v: number | null | undefined, digits = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}
export function count(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}
export function fmtMetric(m: MetricCompare | MetricDef | undefined, v: number | null | undefined) {
  if (!m) return "—";
  if (m.ratio) return pct(v);
  if (m.unit === "count") return count(v);
  return money(v);
}
