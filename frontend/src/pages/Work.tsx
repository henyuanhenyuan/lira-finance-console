import { useEffect, useMemo, useRef, useState } from "react";
import Chart, { chartBase } from "../components/Chart";
import InsightCard from "../components/InsightCard";
import QAWidget from "../components/QAWidget";
import { Delta, Empty, ErrorBox, Loading, MetricTile, Panel, useAsync } from "../components/ui";
import { api, fmtMetric, money, pct, type Run } from "../lib/api";

const HERO = ["gross_margin", "net_revenue", "margin_rate", "order_count", "ad_roi", "refund_rate"];
const INVERT = new Set(["refund_rate", "acos", "loss_sku_ratio", "ad_share"]);

const PRESETS = [
  "为什么本周贡献毛利下滑？哪些 SKU 在亏钱？",
  "广告 ROI 最低的 SKU 是哪些，应该怎么处理？",
  "退款率异常的 SKU 有哪些，背后可能是质量还是描述问题？",
  "给我一份本周利润诊断小结，并说明判断所依据的口径。",
];

type Tab = "overview" | "workbench" | "ranking";

export default function Work() {
  const [tab, setTab] = useState<Tab>("overview");
  const [days, setDays] = useState(7);
  const [insight, setInsight] = useState<any>(null);
  const [latency, setLatency] = useState<number | undefined>();
  const [refreshing, setRefreshing] = useState(false);

  const overview = useAsync(async () => {
    // 单个子请求失败不应让整页崩掉：降级为空数据
    const safe = <T,>(p: Promise<T>, fallback: T): Promise<T> => p.catch(() => fallback);
    const noPoints = { metric: "", points: [] as { date: string; value: number | null }[] };
    const noItems = { items: [] as any[] };
    const noInsight = { insight: null as any };

    const [ov, cat, cats] = await Promise.all([
      api.overview(days), api.catalogue(), safe(api.categories(30), noItems),
    ]);
    const [gm, nr, anom, rank, ins] = await Promise.all([
      safe(api.series("gross_margin", 30), noPoints),
      safe(api.series("net_revenue", 30), noPoints),
      safe(api.anomalies(days), noItems),
      safe(api.rankings("gross_margin", days, true, 8), noItems),
      safe(api.insight("dashboard"), noInsight),
    ]);
    if (ins.insight) setInsight(ins.insight);
    return {
      catalogue: cat.metrics, metrics: ov.metrics,
      gm: gm.points, nr: nr.points,
      anomalies: anom.items, rankings: rank.items, categories: cats.items,
    };
  }, [days]);

  const autoRan = useRef(false);
  useEffect(() => {
    if (!overview.data || insight || autoRan.current) return;
    autoRan.current = true;
    refreshInsight();
  }, [overview.data, insight]);

  async function refreshInsight() {
    setRefreshing(true);
    try {
      const res = await api.refreshInsight();
      if (res.insight) setInsight(res.insight);
      setLatency(res.latency_ms);
    } finally {
      setRefreshing(false);
    }
  }

  const trendOption = useMemo(() => {
    if (!overview.data) return chartBase;
    const gm = overview.data.gm, nr = overview.data.nr;
    return {
      ...chartBase,
      grid: { left: 10, right: 12, top: 46, bottom: 4, containLabel: true },
      legend: {
        show: true, top: 4, right: 4,
        itemWidth: 18, itemHeight: 4, itemGap: 22, icon: "roundRect",
        textStyle: { color: "#c8d2ea", fontSize: 11.5 },
        inactiveColor: "#465270",
        data: ["贡献毛利", "净收入"],
      },
      xAxis: {
        type: "category", data: gm.map((p) => p.date.slice(5)), boundaryGap: false,
        axisLine: { lineStyle: { color: "rgba(255,255,255,.10)" } },
        axisLabel: { color: "#7d8aac", fontSize: 10 }, axisTick: { show: false },
      },
      yAxis: [
        {
          type: "value", name: "毛利", nameGap: 14, nameLocation: "end",
          nameTextStyle: { color: "#93a1c0", fontSize: 10, align: "left", padding: [0, 0, 0, -3] },
          splitLine: { lineStyle: { color: "rgba(255,255,255,.055)" } },
          axisLabel: { color: "#93a1c0", fontSize: 10, formatter: (v: number) => (v / 1e4).toFixed(1).replace(/\.0$/, "") + "万" },
        },
        {
          type: "value", name: "",
          splitLine: { show: false },
          axisLabel: { color: "#93a1c0", fontSize: 10, formatter: (v: number) => (v / 1e4).toFixed(1).replace(/\.0$/, "") + "万" },
        },
      ],
      series: [
        {
          name: "贡献毛利", type: "line", smooth: 0.35, symbol: "none", data: gm.map((p) => p.value),
          itemStyle: { color: "#5be1ff" },
          lineStyle: { width: 2.4, color: "#5be1ff", shadowColor: "rgba(91,225,255,.6)", shadowBlur: 14 },
          areaStyle: {
            color: {
              type: "linear", x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [{ offset: 0, color: "rgba(91,225,255,.28)" }, { offset: 1, color: "rgba(91,225,255,0)" }],
            },
          },
        },
        {
          name: "净收入", type: "line", yAxisIndex: 1, smooth: 0.35, symbol: "none",
          data: nr.map((p) => p.value),
          itemStyle: { color: "#9b7bff" },
          lineStyle: { width: 1.6, color: "#9b7bff", type: "dashed", opacity: 0.9 },
        },
      ],
    } as any;
  }, [overview.data]);

  const catOption = useMemo(() => {
    if (!overview.data) return chartBase;
    const items = [...overview.data.categories].sort((a, b) => a.gross_margin - b.gross_margin);
    return {
      ...chartBase,
      grid: { left: 4, right: 24, top: 8, bottom: 4, containLabel: true },
      xAxis: {
        type: "value", splitLine: { lineStyle: { color: "rgba(255,255,255,.05)" } },
        axisLabel: { color: "#7d8aac", fontSize: 10, formatter: (v: number) => (v / 1e4).toFixed(1).replace(/\.0$/, "") + "万" },
      },
      yAxis: {
        type: "category", data: items.map((i) => i.category),
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: "#b8c3e0", fontSize: 11 },
      },
      series: [{
        type: "bar", data: items.map((i) => i.gross_margin), barWidth: 14,
        itemStyle: {
          borderRadius: [0, 7, 7, 0],
          color: {
            type: "linear", x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [{ offset: 0, color: "rgba(78,242,192,.35)" }, { offset: 1, color: "#4ef2c0" }],
          },
        },
        label: { show: true, position: "right", color: "#8b97b8", fontSize: 10, formatter: (p: any) => money(p.value) },
      }],
    } as any;
  }, [overview.data]);

  return (
    <div className="stack gap-16 fade-in">
      <div className="row between wrap gap-10">
        <div className="seg">
          {([["overview", "经营总览"], ["workbench", "诊断作业"], ["ranking", "利润排行"]] as [Tab, string][]).map(
            ([k, label]) => (
              <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
                {label}
              </button>
            ),
          )}
        </div>
        <div className="seg">
          {[7, 30, 90].map((d) => (
            <button key={d} className={days === d ? "on" : ""} onClick={() => setDays(d)}>
              近 {d} 天
            </button>
          ))}
        </div>
      </div>

      {tab === "overview" && (
        <>
          {overview.loading && !overview.data ? <Loading rows={4} /> : overview.error ? (
            <ErrorBox message={overview.error} />
          ) : overview.data ? (
            <>
              <div className="grid g6">
                {HERO.map((k, i) => {
                  const m = overview.data!.metrics[k];
                  if (!m) return null;
                  const s = k === "gross_margin" ? overview.data!.gm.map((p) => p.value ?? 0)
                    : k === "net_revenue" ? overview.data!.nr.map((p) => p.value ?? 0) : undefined;
                  return (
                    <MetricTile key={k} m={m} series={s} invertGood={INVERT.has(k)}
                      accent={["#5be1ff", "#9b7bff", "#4ef2c0", "#ffc46b", "#5be1ff", "#ff7a9c"][i]} />
                  );
                })}
              </div>

              <div className="split-2">
                <Panel title="贡献毛利与净收入走势" sub="30 天" fill right={
                  <div className="row wrap gap-8">
                    <span className="badge mint"><i className="dot" /> 毛利</span>
                    <span className="badge violet"><i className="dot" /> 收入</span>
                  </div>
                }>
                  <div className="chart-fill">
                    <Chart option={trendOption} height="100%" />
                  </div>
                </Panel>
                <InsightCard insight={insight} onRefresh={refreshInsight} refreshing={refreshing} latency={latency} />
              </div>

              <div className="grid g3">
                <Panel title="异动 SKU（Z-score）" sub={`近 ${days} 天`}>
                  {overview.data.anomalies.length === 0 ? <Empty text="窗口内无显著异动" /> : (
                    <div className="stack gap-8">
                      {overview.data.anomalies.slice(0, 5).map((a: any) => (
                        <div className="driver" key={a.sku_id}>
                          <span style={{ fontSize: 12.5 }}>{a.title}
                            <span className="muted mono" style={{ fontSize: 10.5, marginLeft: 6 }}>{a.sku_id}</span>
                          </span>
                          <span className="mono" style={{ fontSize: 12, color: a.current < 0 ? "var(--rose)" : "var(--mint)" }}>
                            {money(a.current)}
                          </span>
                          <div className="bar"><i style={{ width: `${Math.min(100, Math.abs(a.z) * 26)}%` }} /></div>
                        </div>
                      ))}
                    </div>
                  )}
                </Panel>

                <Panel title="亏损 SKU 排行" sub="按贡献毛利升序">
                  <div className="table-wrap">
                    <table className="table">
                      <thead><tr><th>SKU</th><th className="num">毛利</th><th className="num">毛利率</th></tr></thead>
                      <tbody>
                        {overview.data.rankings.map((r: any) => (
                          <tr key={r.sku_id}>
                            <td>
                              <div className="stack" style={{ lineHeight: 1.25 }}>
                                <span style={{ fontSize: 12.5 }}>{r.title}</span>
                                <span className="muted mono" style={{ fontSize: 10 }}>{r.sku_id}</span>
                              </div>
                            </td>
                            <td className="num mono" style={{ color: r.gross_margin < 0 ? "var(--rose)" : "var(--mint)", fontSize: 12 }}>
                              {money(r.gross_margin)}
                            </td>
                            <td className="num mono" style={{ fontSize: 12 }}>
                              {r.margin_rate == null ? "未知" : pct(r.margin_rate)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>

                <Panel title="类目毛利贡献" sub="近 30 天" fill>
                  <div className="chart-fill" style={{ minHeight: 200 }}>
                    <Chart option={catOption} height="100%" />
                  </div>
                </Panel>
              </div>

              <Panel title="全量指标体系" sub={`${overview.data.catalogue.length} 个口径 · 近 ${days} 天`}
                     right={<span className="badge cyan">SQL 计算 · Agent 只读</span>}>
                <div className="grid g6" style={{ gap: 12 }}>
                  {overview.data.catalogue.map((def) => {
                    const m = overview.data!.metrics[def.name];
                    if (!m) return null;
                    const bad = INVERT.has(def.name) ? m.pct > 0 : m.pct < 0;
                    return (
                      <div key={def.name} className="kpi" title={def.formula}>
                        <span className="kpi-label">{def.label}</span>
                        <span className="tnum" style={{ fontSize: 17, fontWeight: 600 }}>{fmtMetric(m, m.current)}</span>
                        <div className="row between">
                          <span className="muted" style={{ fontSize: 10 }}>{def.group}</span>
                          <Delta value={m.pct} inverted={INVERT.has(def.name)} baseline={m.has_baseline} />
                        </div>
                        {bad && <span className="badge rose" style={{ alignSelf: "flex-start", fontSize: 9.5 }}>需关注</span>}
                      </div>
                    );
                  })}
                </div>
              </Panel>
            </>
          ) : null}
        </>
      )}

      {tab === "workbench" && <Workbench />}
      {tab === "ranking" && <Ranking days={days} />}

      <QAWidget />
    </div>
  );
}

/* ---------------- 诊断作业 ---------------- */
function Workbench() {
  const [question, setQuestion] = useState(PRESETS[0]);
  const [running, setRunning] = useState(false);
  const [current, setCurrent] = useState<Run | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const runs = useAsync(() => api.runs(20), []);

  async function start() {
    setRunning(true);
    setErr(null);
    try {
      setCurrent(await api.createRun(question.trim()));
      runs.reload();
    } catch (e: any) {
      setErr(e?.message ?? "分析失败");
    } finally {
      setRunning(false);
    }
  }

  async function open(id: number) {
    try { setCurrent(await api.run(id)); } catch (e: any) { setErr(e?.message); }
  }

  const insight = current?.result?.insight ?? null;

  return (
    <div className="stack gap-16">
      <Panel title="发起一次多智能体分析" sub="LangGraph Supervisor · 实时执行"
             right={<span className="badge violet">ReAct · 最多 6 步</span>}>
        <div className="row gap-10" style={{ alignItems: "stretch" }}>
          <input className="input" value={question} onChange={(e) => setQuestion(e.target.value)}
                 placeholder="描述你要诊断的经营问题…"
                 onKeyDown={(e) => e.key === "Enter" && !running && start()} />
          <button className="btn primary" onClick={start} disabled={running || question.trim().length < 2}
                  style={{ whiteSpace: "nowrap" }}>
            {running ? "分析中…" : "开始分析"}
          </button>
        </div>
        <div className="row wrap gap-6 mt-12">
          {PRESETS.map((p) => (
            <button key={p} className="btn sm ghost" onClick={() => setQuestion(p)} style={{ fontSize: 11.5, fontWeight: 500 }}>
              {p.length > 26 ? p.slice(0, 26) + "…" : p}
            </button>
          ))}
        </div>
        {err && <div className="mt-12"><ErrorBox message={err} /></div>}
      </Panel>

      <div className="split-2">
        <div className="stack gap-16">
          {current ? (
            <>
              <InsightCard insight={insight} />
              <Panel title="执行轨迹" sub={`Run #${current.id} · ${current.latency_ms} ms`}
                     right={<span className={current.status === "succeeded" ? "badge mint" : current.status === "failed" ? "badge rose" : "badge amber"}>{current.status}</span>}>
                <div className="timeline">
                  {current.steps.map((s) => (
                    <div key={s.idx} className={`tl-item ${s.tool ? "tool" : ""}`}>
                      <div className="row between">
                        <span style={{ fontSize: 13, fontWeight: 600 }}>
                          {s.agent_name ?? s.agent_key}
                          {s.tool && <span className="badge violet" style={{ marginLeft: 8, fontSize: 10 }}>{s.tool}</span>}
                        </span>
                        <span className="muted mono" style={{ fontSize: 10.5 }}>{s.latency_ms} ms</span>
                      </div>
                      {s.thought && <div className="soft" style={{ fontSize: 12.5, marginTop: 3 }}>{s.thought}</div>}
                    </div>
                  ))}
                </div>
              </Panel>
            </>
          ) : (
            <Panel title="分析结果" sub="选择或发起一次分析">
              <Empty text="尚未执行分析。输入问题后点击「开始分析」，或从右侧历史中选择。" />
            </Panel>
          )}
        </div>

        <Panel title="运行历史" sub="最近 20 次" right={<button className="btn sm ghost" onClick={() => runs.reload()}>刷新</button>}>
          {runs.loading && !runs.data ? <Loading /> : runs.error ? <ErrorBox message={runs.error} /> : (
            <div className="stack gap-8" style={{ maxHeight: 560, overflowY: "auto" }}>
              {(runs.data?.items ?? []).map((r) => (
                <button key={r.id} onClick={() => open(r.id)} className="kpi" style={{ textAlign: "left", cursor: "pointer", gap: 5 }}>
                  <div className="row between">
                    <span className="badge cyan" style={{ fontSize: 10 }}>#{r.id} · {r.kind}</span>
                    <span className="muted mono" style={{ fontSize: 10 }}>{r.latency_ms} ms</span>
                  </div>
                  <span style={{ fontSize: 12.5, lineHeight: 1.45 }}>{r.headline ?? r.title}</span>
                  <span className="muted" style={{ fontSize: 10.5 }}>{r.model || "rule-engine"} · {r.status}</span>
                </button>
              ))}
              {(runs.data?.items ?? []).length === 0 && <Empty text="还没有运行记录" />}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

/* ---------------- 利润排行 ---------------- */
function Ranking({ days }: { days: number }) {
  const [metric, setMetric] = useState("gross_margin");
  const ranking = useAsync(() => api.rankings(metric, days, metric !== "net_revenue", 15), [metric, days]);

  return (
    <Panel title="利润诊断排行" sub={`近 ${days} 天 · 按口径排序`} right={
      <div className="seg">
        {[["gross_margin", "贡献毛利"], ["margin_rate", "毛利率"], ["ad_spend", "广告花费"], ["refund_amount", "退款金额"]].map(
          ([k, label]) => (
            <button key={k} className={metric === k ? "on" : ""} onClick={() => setMetric(k)}>{label}</button>
          ),
        )}
      </div>
    }>
      {ranking.loading && !ranking.data ? <Loading /> : ranking.error ? <ErrorBox message={ranking.error} /> : (
        <div className="table-wrap" style={{ maxHeight: 520 }}>
          <table className="table">
            <thead>
              <tr>
                <th>商品</th><th>类目</th><th className="num">毛利</th><th className="num">毛利率</th>
                <th className="num">订单</th><th className="num">广告ROI</th><th className="num">退款单</th>
              </tr>
            </thead>
            <tbody>
              {(ranking.data?.items ?? []).map((r: any) => (
                <tr key={r.sku_id}>
                  <td>
                    <div className="stack" style={{ lineHeight: 1.25 }}>
                      <span style={{ fontSize: 12.5 }}>{r.title}</span>
                      <span className="muted mono" style={{ fontSize: 10 }}>{r.sku_id}</span>
                    </div>
                  </td>
                  <td><span className="badge" style={{ fontSize: 10 }}>{r.category}</span></td>
                  <td className="num mono" style={{ color: (r.gross_margin ?? 0) < 0 ? "var(--rose)" : "var(--mint)", fontSize: 12 }}>
                    {money(r.gross_margin)}
                  </td>
                  <td className="num mono" style={{ fontSize: 12 }}>{r.margin_rate == null ? "未知" : pct(r.margin_rate)}</td>
                  <td className="num mono" style={{ fontSize: 12 }}>{r.order_count}</td>
                  <td className="num mono" style={{ fontSize: 12 }}>{r.ad_roi == null ? "—" : r.ad_roi.toFixed(2)}</td>
                  <td className="num mono" style={{ fontSize: 12 }}>{r.refund_orders}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
