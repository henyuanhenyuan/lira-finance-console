import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth";

const NAV = [
  { to: "/work", label: "智能财务分析", glyph: "◐" },
  { to: "/agents", label: "Agent 模型", glyph: "◇" },
  { to: "/settings", label: "设置", glyph: "⚙" },
];

const TITLES: Record<string, { title: string; sub: string }> = {
  "/work": { title: "智能财务分析", sub: "Intelligent Financial Analysis" },
  "/agents": { title: "Agent 模型", sub: "Multi-Agent Orchestration" },
  "/settings": { title: "设置", sub: "Model Routing & Governance" },
};

export default function Shell() {
  const { user, logout } = useAuth();
  const loc = useLocation();
  const meta = TITLES[loc.pathname] ?? TITLES["/work"];

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand">
          <div className="brand-mark" />
          <div className="brand-text stack">
            <span className="brand-name">Lira</span>
            <span className="brand-sub">Financial Agent</span>
          </div>
        </div>

        <nav className="nav">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/work"}
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            >
              <span className="glyph">{n.glyph}</span>
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>

        <div style={{ flex: 1 }} />

        <div className="stack gap-10">
          <div className="divider" />
          <div className="user-chip">
            <div className="avatar">{(user?.name ?? "L").slice(0, 1)}</div>
            <div className="stack" style={{ lineHeight: 1.2 }}>
              <span style={{ fontSize: 12.5, fontWeight: 600 }}>{user?.name}</span>
              <span className="muted" style={{ fontSize: 10.5 }}>{user?.role}</span>
            </div>
          </div>
          <button className="btn ghost sm" onClick={logout}>退出登录</button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <span className="eyebrow">{meta.sub}</span>
            <h1 className="h1">{meta.title}</h1>
          </div>
          <div className="topbar-actions">
            <span className="badge mint"><i className="dot" /> 引擎在线</span>
            <span className="badge cyan">PostgreSQL · pgvector</span>
            <NavLink to="/screen" className="btn sm primary" style={{ textDecoration: "none" }}>
              切换可视化大屏
            </NavLink>
          </div>
        </header>
        <Outlet />
      </main>
    </div>
  );
}
