import { useState } from "react";
import { useAuth } from "../lib/auth";

const FEATS = [
  { g: "◈", t: "多智能体实时分析", d: "监督者调度 4 个专职 Agent，指标、异动、口径、建议四路并行" },
  { g: "◇", t: "结论可溯源", d: "每条结论绑定 SKU 与知识库证据，数字全部来自 SQL 口径" },
  { g: "⌁", t: "评测闭环", d: "任务成功率、工具准确率、引用命中率、幻觉率全量可量化" },
];

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("admin@lira.local");
  const [password, setPassword] = useState("lira2026");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(email.trim(), password);
    } catch (e: any) {
      setErr(e?.message ?? "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-shell">
      <div className="login-visual">
        <div className="brand">
          <div className="brand-mark" />
          <div className="stack">
            <span className="brand-name">Lira</span>
            <span className="brand-sub">Financial Agent Console</span>
          </div>
        </div>

        <div className="login-copy fade-in">
          <h1 className="login-title">
            让财务分析<br />
            <em>自己得出结论</em>
          </h1>
          <p className="soft" style={{ marginTop: 16, fontSize: 15, maxWidth: 460 }}>
            不是问答工具。多智能体嵌入每一个视图，实时读取真实订单与成本口径，
            直接给出归因、置信度与可执行动作。
          </p>

          <div className="login-feats">
            {FEATS.map((f) => (
              <div className="feat" key={f.t}>
                <div className="fi">{f.g}</div>
                <div className="stack">
                  <span style={{ fontSize: 13.5, fontWeight: 600 }}>{f.t}</span>
                  <span className="muted" style={{ fontSize: 12.5 }}>{f.d}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="row gap-10 muted" style={{ fontSize: 11.5 }}>
          <span className="badge mint"><i className="dot" /> FastAPI</span>
          <span className="badge violet"><i className="dot" /> LangGraph</span>
          <span className="badge cyan"><i className="dot" /> pgvector</span>
          <span className="badge amber"><i className="dot" /> MCP</span>
        </div>
      </div>

      <div className="login-card-wrap">
        <div className="orb" aria-hidden />
        <div className="orb small" aria-hidden />
        <div className="glass tilt login-card pad-lg fade-in" style={{ position: "relative", zIndex: 2 }}>
          <div className="stack gap-4">
            <span className="eyebrow">Sign in</span>
            <h2 className="h2">登录控制台</h2>
          </div>

          <form className="stack gap-12 mt-24" onSubmit={submit}>
            <div className="field">
              <label>账号</label>
              <input className="input" value={email} onChange={(e) => setEmail(e.target.value)}
                     placeholder="you@company.com" autoComplete="username" />
            </div>
            <div className="field">
              <label>密码</label>
              <input className="input" type="password" value={password}
                     onChange={(e) => setPassword(e.target.value)} placeholder="••••••••"
                     autoComplete="current-password" />
            </div>

            {err && <div className="badge rose" style={{ whiteSpace: "normal", padding: "9px 12px" }}>{err}</div>}

            <button className="btn primary mt-4" type="submit" disabled={busy}>
              {busy ? "验证中…" : "进入控制台"}
            </button>
          </form>

          <div className="divider mt-24" />
          <div className="row between mt-12 muted" style={{ fontSize: 11.5 }}>
            <span className="mono">v2.0</span>
          </div>
        </div>
      </div>
    </div>
  );
}
