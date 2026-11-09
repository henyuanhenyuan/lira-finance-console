import { useState } from "react";
import { Empty, ErrorBox, Loading, Panel, useAsync } from "../components/ui";
import { api, pct } from "../lib/api";

type Tab = "agents" | "tools" | "kb" | "eval";

const TABS: { k: Tab; label: string; sub: string }[] = [
  { k: "agents", label: "智能体", sub: "Supervisor + 4" },
  { k: "tools", label: "MCP 工具", sub: "7 个只读工具" },
  { k: "kb", label: "知识库", sub: "pgvector 检索" },
  { k: "eval", label: "评测", sub: "6 项指标" },
];

const ROLE_TONE: Record<string, string> = {
  Supervisor: "badge violet",
  MetricAnalyst: "badge cyan",
  AnomalyHunter: "badge amber",
  RagLibrarian: "badge mint",
  Advisor: "badge rose",
};

export default function Agents() {
  const [tab, setTab] = useState<Tab>("agents");
  const [evals, setEvals] = useState<any>(null);
  const [evalBusy, setEvalBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const agents = useAsync(() => api.agents(), []);
  const tools = useAsync(() => api.tools(), []);
  const kb = useAsync(() => api.kb(), []);
  const history = useAsync(() => api.evalHistory(8), []);
  const cases = useAsync(() => api.evalCases(), []);

  async function toggle(key: string, enabled: boolean) {
    await api.toggleAgent(key, enabled);
    agents.reload();
  }

  async function reindex() {
    await api.reindex();
    kb.reload();
  }

  async function runEval() {
    setEvalBusy(true);
    setErr(null);
    try {
      const res = await api.runEval();
      setEvals(res);
      history.reload();
    } catch (e: any) {
      setErr(e?.message ?? "评测失败");
    } finally {
      setEvalBusy(false);
    }
  }

  const latest = evals ?? history.data?.items?.[0] ?? null;
  const detail = evals?.detail ?? null;

  return (
    <div className="stack gap-16 fade-in">
      <div className="seg">
        {TABS.map((t) => (
          <button key={t.k} className={tab === t.k ? "on" : ""} onClick={() => setTab(t.k)}>
            {t.label}
            <span className="seg-sub">{t.sub}</span>
          </button>
        ))}
      </div>

      {tab === "agents" && (
        <div className="stack gap-16">
          <Panel title="智能体注册表" sub="LangGraph 编排 · 主模型 qwen-plus"
                 right={<span className="badge mint"><i className="dot" /> 已注册 {agents.data?.items.length ?? 0} 个</span>}>
            {agents.loading && !agents.data ? <Loading /> : agents.error ? <ErrorBox message={agents.error} /> : (
              <div className="grid g2" style={{ gap: 14 }}>
                {(agents.data?.items ?? []).map((a: any) => (
                  <div className="kpi tilt" key={a.key} style={{ gap: 8 }}>
                    <div className="row between">
                      <div className="row gap-8">
                        <span className={ROLE_TONE[a.role] ?? "badge"} style={{ fontSize: 10 }}>{a.role}</span>
                        <span style={{ fontSize: 14, fontWeight: 600 }}>{a.name}</span>
                      </div>
                      <button className={`btn sm ${a.enabled ? "ghost" : "primary"}`}
                              onClick={() => toggle(a.key, !a.enabled)}>
                        {a.enabled ? "已启用" : "已停用"}
                      </button>
                    </div>
                    <span className="muted" style={{ fontSize: 12 }}>{a.description}</span>
                    <div className="row wrap gap-6 mt-4">
                      {(a.tools ?? []).length === 0
                        ? <span className="muted" style={{ fontSize: 10.5 }}>无直接工具 · 仅调度</span>
                        : a.tools.map((t: string) => (
                          <span className="evidence" key={t}>{t}</span>
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="编排拓扑" sub="Supervisor 按问题类型按需调度">
            <div className="row wrap gap-10" style={{ alignItems: "center" }}>
              <span className="badge violet" style={{ padding: "8px 14px" }}>Supervisor 调度中枢</span>
              <span className="muted">→</span>
              {[
                ["MetricAnalyst", "指标取数", "cyan"],
                ["AnomalyHunter", "异动检测", "amber"],
                ["RagLibrarian", "口径检索", "mint"],
              ].map(([n, d, tone]) => (
                <div key={n} className="stack gap-4" style={{ alignItems: "center" }}>
                  <span className={`badge ${tone}`} style={{ padding: "8px 14px" }}>{n}</span>
                  <span className="muted" style={{ fontSize: 10.5 }}>{d}</span>
                </div>
              ))}
              <span className="muted">→</span>
              <span className="badge rose" style={{ padding: "8px 14px" }}>Advisor 结论合成</span>
            </div>
          </Panel>
        </div>
      )}

      {tab === "tools" && (
        <Panel title="MCP 工具库" sub="stdio 传输 · JSON Schema 校验 · 只读约束"
               right={<span className="badge violet">MCP Server</span>}>
          {tools.loading && !tools.data ? <Loading /> : tools.error ? <ErrorBox message={tools.error} /> : (
            <div className="grid g2" style={{ gap: 12 }}>
              {(tools.data?.items ?? []).map((t: any) => (
                <div className="kpi" key={t.key} style={{ gap: 6 }}>
                  <div className="row between">
                    <span className="mono" style={{ fontSize: 13, color: "var(--cyan)" }}>{t.key}</span>
                    <span className="badge" style={{ fontSize: 10 }}>{t.calls} 次调用</span>
                  </div>
                  <span className="muted" style={{ fontSize: 12 }}>{t.description}</span>
                  <div className="row between mt-4">
                    <span className="muted mono" style={{ fontSize: 10 }}>
                      {Object.keys(t.input_schema?.properties ?? {}).join(" · ") || "无参数"}
                    </span>
                    <span className="muted mono" style={{ fontSize: 10 }}>{Number(t.avg_latency).toFixed(0)} ms</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      {tab === "kb" && (
        <Panel title="财务知识库" sub="pgvector HNSW · 向量 + 全文混合检索"
               right={<button className="btn sm ghost" onClick={reindex}>重建索引</button>}>
          {kb.loading && !kb.data ? <Loading /> : kb.error ? <ErrorBox message={kb.error} /> : (
            <div className="stack gap-8">
              {(kb.data?.items ?? []).map((d) => (
                <div className="driver" key={d.id} style={{ gridTemplateColumns: "1fr auto" }}>
                  <div className="stack" style={{ lineHeight: 1.3 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{d.title}</span>
                    <span className="muted mono" style={{ fontSize: 10.5 }}>{d.source} · {d.slug}</span>
                  </div>
                  <span className="badge cyan" style={{ fontSize: 10 }}>{d.chunks} chunks</span>
                </div>
              ))}
              {(kb.data?.items ?? []).length === 0 && <Empty text="知识库为空" />}
            </div>
          )}
        </Panel>
      )}

      {tab === "eval" && (
        <div className="stack gap-16">
          <Panel title="评测面板" sub="任务成功率 / 工具准确率 / 引用命中 / 幻觉率 / P95 / 成本"
                 right={
                   <button className="btn primary sm" onClick={runEval} disabled={evalBusy}>
                     {evalBusy ? "评测中…" : "运行评测"}
                   </button>
                 }>
            {err && <div className="mb-12"><ErrorBox message={err} /></div>}
            {!latest ? (
              <Empty text="还没有评测记录，点击「运行评测」执行全部用例。" />
            ) : (
              <div className="grid g6" style={{ gap: 12 }}>
                {[
                  ["任务成功率", latest.success_rate, "#4ef2c0"],
                  ["工具准确率", latest.tool_accuracy, "#5be1ff"],
                  ["引用命中率", latest.citation_hit, "#9b7bff"],
                ].map(([label, v, tone]) => (
                  <div className="kpi" key={label as string} style={{ alignItems: "center", gap: 4 }}>
                    <span className="kpi-label">{label as string}</span>
                    <span className="kpi-value" style={{ fontSize: 22 }}>{pct(v as number)}</span>
                    <div className="meter" style={{ width: "100%" }}><i style={{ width: `${(v as number) * 100}%`, background: tone as string }} /></div>
                  </div>
                ))}
                <div className="kpi" style={{ alignItems: "center", gap: 4 }}>
                  <span className="kpi-label">幻觉率</span>
                  <span className="kpi-value" style={{ fontSize: 22, color: (latest.hallucination_rate ?? 0) > 0.1 ? "var(--rose)" : "var(--mint)" }}>
                    {pct(latest.hallucination_rate)}
                  </span>
                  <span className="muted" style={{ fontSize: 10 }}>越低越好</span>
                </div>
                <div className="kpi" style={{ alignItems: "center", gap: 4 }}>
                  <span className="kpi-label">P95 延迟</span>
                  <span className="kpi-value" style={{ fontSize: 22 }}>{latest.p95_latency_ms ?? 0} ms</span>
                </div>
                <div className="kpi" style={{ alignItems: "center", gap: 4 }}>
                  <span className="kpi-label">单次成本</span>
                  <span className="kpi-value" style={{ fontSize: 22 }}>${(latest.avg_cost ?? 0).toFixed(5)}</span>
                </div>
              </div>
            )}
          </Panel>

          {detail && (
            <Panel title="用例明细" sub={`${detail.length} 条`}>
              <div className="table-wrap" style={{ maxHeight: 420 }}>
                <table className="table">
                  <thead><tr><th>用例</th><th>问题</th><th>工具</th><th>结果</th></tr></thead>
                  <tbody>
                    {detail.map((d: any) => (
                      <tr key={d.key}>
                        <td className="mono" style={{ fontSize: 11 }}>{d.key}</td>
                        <td style={{ fontSize: 12 }}>{d.question}</td>
                        <td className="mono" style={{ fontSize: 10.5 }}>{d.tools.join(", ") || "—"}</td>
                        <td>
                          <span className={`badge ${d.pass ? "mint" : "rose"}`} style={{ fontSize: 10 }}>
                            {d.pass ? "通过" : "未通过"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}

          <div className="split-2">
            <Panel title="历史评测" sub="版本对比">
              {history.loading && !history.data ? <Loading /> : (
                <div className="stack gap-8">
                  {(history.data?.items ?? []).map((h: any) => (
                    <div className="driver" key={h.id}>
                      <span style={{ fontSize: 12.5 }}>
                        <span className="badge cyan" style={{ fontSize: 10, marginRight: 8 }}>#{h.id}</span>
                        {h.model}
                      </span>
                      <span className="mono" style={{ fontSize: 12 }}>{pct(h.success_rate)} · {h.passed}/{h.total}</span>
                      <div className="bar"><i style={{ width: `${h.success_rate * 100}%` }} /></div>
                    </div>
                  ))}
                  {(history.data?.items ?? []).length === 0 && <Empty text="暂无历史" />}
                </div>
              )}
            </Panel>

            <Panel title="评测集分布" sub="标注用例">
              {cases.loading && !cases.data ? <Loading /> : (
                <div className="grid g2" style={{ gap: 10 }}>
                  {Object.entries(
                    (cases.data?.items ?? []).reduce((acc: Record<string, number>, c: any) => {
                      acc[c.category] = (acc[c.category] ?? 0) + 1;
                      return acc;
                    }, {}),
                  ).map(([k, v]) => (
                    <div className="kpi" key={k} style={{ gap: 2 }}>
                      <span className="kpi-label">{k}</span>
                      <span className="kpi-value" style={{ fontSize: 20 }}>{v}</span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
