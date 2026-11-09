import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { fmtMetric, type MetricCompare } from "../lib/api";

/* ---------- 数据加载 ---------- */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fn();
      if (alive.current) setData(res);
    } catch (e: any) {
      if (alive.current) setError(e?.message ?? "加载失败");
    } finally {
      if (alive.current) setLoading(false);
    }
  }, deps);

  useEffect(() => {
    alive.current = true;
    run();
    return () => {
      alive.current = false;
    };
  }, [run]);

  return { data, loading, error, reload: run, setData };
}

/* ---------- 卡片 ---------- */
export function Panel({
  title,
  sub,
  right,
  children,
  className = "",
  flush = false,
  fill = false,
}: {
  title?: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
  fill?: boolean;
}) {
  return (
    <section
      className={`glass tilt ${flush ? "flush" : ""} ${fill ? "panel-fill" : ""} ${className}`}
    >
      {(title || right) && (
        <header className="row between wrap gap-10 pad panel-head" style={{ paddingBottom: 12 }}>
          <div className="stack">
            {sub && <span className="eyebrow">{sub}</span>}
            {title && <h3 className="h3">{title}</h3>}
          </div>
          {right}
        </header>
      )}
      <div
        className={flush ? "panel-body" : "pad panel-body"}
        style={flush ? undefined : { paddingTop: 0 }}
      >
        {children}
      </div>
    </section>
  );
}

/* ---------- 迷你折线 ---------- */
export function Sparkline({
  values,
  width = 140,
  height = 34,
  tone = "cyan",
}: {
  values: number[];
  width?: number;
  height?: number;
  tone?: "cyan" | "violet" | "mint" | "rose";
}) {
  const clean = values.filter((v) => v !== null && !Number.isNaN(v)) as number[];
  if (clean.length < 2) return <div className="spark" style={{ height }} />;
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const span = max - min || 1;
  const step = width / (clean.length - 1);
  const pts = clean.map((v, i) => [i * step, height - ((v - min) / span) * (height - 4) - 2]);
  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const id = `sg-${tone}-${Math.round(width)}-${clean.length}`;
  const colors: Record<string, [string, string]> = {
    cyan: ["#5be1ff", "rgba(91,225,255,0)"],
    violet: ["#9b7bff", "rgba(155,123,255,0)"],
    mint: ["#4ef2c0", "rgba(78,242,192,0)"],
    rose: ["#ff7a9c", "rgba(255,122,156,0)"],
  };
  const [c1] = colors[tone] ?? colors.cyan;
  return (
    <svg className="spark" viewBox={`0 0 ${width} ${height}`} width="100%" height={height} preserveAspectRatio="none">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c1} stopOpacity="0.34" />
          <stop offset="100%" stopColor={c1} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={c1} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" opacity="0.95" />
    </svg>
  );
}

/* ---------- 环比 ---------- */
export function Delta({
  value,
  inverted = false,
  baseline = true,
}: {
  value: number;
  inverted?: boolean;
  baseline?: boolean;
}) {
  // 没有上一周期数据、或基数过小导致比率失真时，不给假数字
  if (!baseline || !Number.isFinite(value) || Math.abs(value) > 3) {
    return <span className="delta flat">—</span>;
  }
  if (Math.abs(value) < 0.0005) return <span className="delta flat">持平</span>;
  const good = inverted ? value < 0 : value > 0;
  const cls = good ? "up" : "down";
  const arrow = value > 0 ? "▲" : "▼";
  return (
    <span className={`delta ${cls}`}>
      {arrow} {Math.abs(value * 100).toFixed(1)}%
    </span>
  );
}

/* ---------- KPI 磁贴 ---------- */
export function MetricTile({
  m,
  series,
  invertGood = false,
  accent = "#5be1ff",
}: {
  m: MetricCompare;
  series?: number[];
  invertGood?: boolean;
  accent?: string;
}) {
  return (
    <div className="kpi">
      <span className="glow" style={{ background: accent }} />
      <span className="kpi-label">{m.label}</span>
      <span className="kpi-value">{fmtMetric(m, m.current)}</span>
      <div className="row between">
        <span className="muted" style={{ fontSize: 11 }}>环比</span>
        <Delta value={m.pct} inverted={invertGood} baseline={m.has_baseline} />
      </div>
      {series && <Sparkline values={series} tone={invertGood ? "rose" : "cyan"} />}
    </div>
  );
}

/* ---------- 状态 ---------- */
export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack gap-10">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 44, opacity: 1 - i * 0.18 }} />
      ))}
    </div>
  );
}

export function Empty({ text = "暂无数据" }: { text?: string }) {
  return <div className="muted" style={{ padding: "22px 0", textAlign: "center", fontSize: 13 }}>{text}</div>;
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="badge rose" style={{ whiteSpace: "normal", padding: "10px 12px", display: "block" }}>
      {message}
    </div>
  );
}

