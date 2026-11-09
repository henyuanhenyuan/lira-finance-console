import { money, type Insight } from "../lib/api";

export default function InsightCard({
  insight,
  onRefresh,
  refreshing = false,
  compact = false,
  latency,
}: {
  insight: Insight | null;
  onRefresh?: () => void;
  refreshing?: boolean;
  compact?: boolean;
  latency?: number;
}) {
  const conf = insight?.confidence ?? 0;

  return (
    <div className="insight fade-in">
      <div className="insight-head">
        <div className="row gap-8">
          <span className="badge cyan"><i className="dot" /> AI 实时研判</span>
          {insight?.model && (
            <span className="badge" style={{ fontFamily: "var(--mono)", fontSize: 10 }}>
              {insight.model}
            </span>
          )}
        </div>
        <div className="row gap-10">
          <span className="badge violet">置信度 {(conf * 100).toFixed(0)}%</span>
          {latency !== undefined && <span className="muted" style={{ fontSize: 11 }}>{latency} ms</span>}
          {onRefresh && (
            <button className="btn sm ghost" onClick={onRefresh} disabled={refreshing}>
              {refreshing ? "分析中…" : "重新研判"}
            </button>
          )}
        </div>
      </div>

      {!insight ? (
        <div className="muted" style={{ fontSize: 13, padding: "8px 0" }}>
          暂无研判结论，点击「重新研判」让多智能体跑一次实时分析。
        </div>
      ) : (
        <>
          <p className="insight-text" style={{ margin: "2px 0 14px" }}>{insight.headline}</p>

          {insight.drivers?.length > 0 && (
            <div className="stack gap-8">
              <span className="eyebrow">归因驱动</span>
              {insight.drivers.slice(0, compact ? 3 : 4).map((d, i) => (
                <div className="driver" key={i}>
                  <span style={{ fontSize: 13 }}>{d.factor}</span>
                  <span className="mono" style={{ fontSize: 12, color: d.impact < 0 ? "var(--rose)" : "var(--mint)" }}>
                    {d.impact === 0 ? "—" : money(d.impact)}
                  </span>
                  <div className="bar">
                    <i style={{ width: `${Math.min(100, Math.max(4, (d.share || 0) * 100))}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}

          {insight.actions?.length > 0 && (
            <div className="stack gap-8 mt-16">
              <span className="eyebrow">建议动作</span>
              {insight.actions.slice(0, compact ? 2 : 3).map((a, i) => (
                <div className="action" key={i}>
                  <span className="idx">{i + 1}</span>
                  <div className="stack">
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{a.title}</span>
                    <span className="muted" style={{ fontSize: 11.5 }}>预期：{a.expected}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {insight.evidence?.length > 0 && (
            <div className="row wrap gap-6 mt-16">
              <span className="eyebrow" style={{ marginRight: 4 }}>证据</span>
              {insight.evidence.slice(0, 8).map((e, i) => (
                <span className="evidence" key={i}>{e}</span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
