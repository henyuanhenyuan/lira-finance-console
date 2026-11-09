import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Chart, { chartBase } from "../components/Chart";
import { useAsync } from "../components/ui";
import { api, money, pct, type MetricCompare } from "../lib/api";

const KPI_KEYS = ["net_revenue", "margin_rate", "order_count", "aov", "ad_roi", "refund_rate"];

function useCountUp(value: number, duration = 900) {
  const [v, setV] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / duration);
      const eased = 1 - Math.pow(1 - k, 3);
      setV(a + (value - a) * eased);
      if (k < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return v;
}

export default function Screen() {
  const nav = useNavigate();
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const { data, reload } = useAsync(async () => {
    const [ov, gm, anom, rank, cats, ins] = await Promise.all([
      api.overview(7),
      api.series("gross_margin", 30),
      api.anomalies(7),
      api.rankings("gross_margin", 7, true, 6),
      api.categories(30),
      api.insight("dashboard"),
    ]);
    return {
      metrics: ov.metrics,
      series: gm.points,
      anomalies: anom.items,
      losers: rank.items,
      categories: cats.items,
      insight: ins.insight,
    };
  }, []);

  useEffect(() => {
    const t = setInterval(() => reload(), 60_000);
    return () => clearInterval(t);
  }, [reload]);

  const trend = useMemo(() => {
    if (!data) return chartBase;
    const pts = data.series;
    return {
      ...chartBase,
      grid: { left: 6, right: 10, top: 14, bottom: 4, containLabel: true },
      xAxis: {
        type: "category", boundaryGap: false, data: pts.map((p) => p.date.slice(5)),
        axisLine: { lineStyle: { color: "rgba(91,225,255,.25)" } },
        axisLabel: { color: "#6f7d9c", fontSize: 9.5, interval: 4 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value", splitNumber: 4,
        splitLine: { lineStyle: { color: "rgba(91,225,255,.07)" } },
        axisLabel: { color: "#6f7d9c", fontSize: 9.5, formatter: (v: number) => (v / 1e4).toFixed(0) + "万" },
      },
      series: [{
        type: "line", smooth: 0.4, symbol: "none",
        data: pts.map((p) => p.value),
        lineStyle: { width: 2.8, color: "#5be1ff", shadowColor: "rgba(91,225,255,.9)", shadowBlur: 22 },
        areaStyle: {
          color: {
            type: "linear", x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: "rgba(91,225,255,.42)" }, { offset: 1, color: "rgba(91,225,255,0)" }],
          },
        },
        markLine: {
          silent: true, symbol: "none",
          lineStyle: { color: "rgba(155,123,255,.55)", type: "dashed" },
          data: [{ type: "average", label: { formatter: "均值", color: "#9b7bff", fontSize: 9.5 } }],
        },
      }],
    } as any;
  }, [data]);

  const catOption = useMemo(() => {
    if (!data) return chartBase;
    const items = [...data.categories].sort((a, b) => b.gross_margin - a.gross_margin).slice(0, 5);
    return {
      ...chartBase,
      grid: { left: 0, right: 8, top: 6, bottom: 2, containLabel: true },
      xAxis: {
        type: "category", data: items.map((i) => i.category),
        axisLine: { lineStyle: { color: "rgba(91,225,255,.2)" } },
        axisLabel: { color: "#8b97b8", fontSize: 9.5 }, axisTick: { show: false },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "rgba(91,225,255,.07)" } }, axisLabel: { show: false } },
      series: [{
        type: "bar", barWidth: 20, data: items.map((i) => i.gross_margin),
        itemStyle: {
          borderRadius: [5, 5, 0, 0],
          color: {
            type: "linear", x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: "#4ef2c0" }, { offset: 1, color: "rgba(78,242,192,.08)" }],
          },
        },
      }],
    } as any;
  }, [data]);

  const m: Record<string, MetricCompare> = data?.metrics ?? {};
  const gm = m.gross_margin;
  const heroValue = useCountUp(gm?.current ?? 0);
  const marginRate = useCountUp((m.margin_rate?.current ?? 0) * 100);
  const orderCount = useCountUp(m.order_count?.current ?? 0);

  const clock = now.toLocaleTimeString("zh-CN", { hour12: false });
  const date = now.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
  const week = "周" + "日一二三四五六"[now.getDay()];

  return (
    <div className="screen">
      <div className="sc-scan" />
      <div className="screen-head">
        <div className="row gap-12">
          <div className="brand-mark" />
          <div className="stack" style={{ lineHeight: 1.35 }}>
            <span className="badge cyan" style={{ fontSize: 9.5 }}>LIRA FINANCIAL OS</span>
            <span className="muted" style={{ fontSize: 10, letterSpacing: ".22em" }}>
              多智能体 · 实时财务分析
            </span>
          </div>
        </div>
        <div className="screen-actions">
          <span className="badge mint"><i className="dot" /> 引擎在线</span>
          <span className="badge violet">{pct(data?.insight?.confidence ?? 0, 0)} 置信度</span>
          <span className="screen-clock">{date} {week} {clock}</span>
          <button className="btn sm ghost" onClick={() => reload()}>刷新</button>
          <button className="btn sm primary" onClick={() => nav("/work")}>返回智能财务分析</button>
        </div>
      </div>

      <div className="screen-frame">
        <div className="sc-banner">
          <div className="wing" />
          <div className="plate">
            <div className="stack" style={{ alignItems: "center" }}>
              <h1>财务智能中枢</h1>
              <span className="sub">Real-time Financial Command Center</span>
            </div>
          </div>
          <div className="wing right" />
        </div>

        <div className="screen-grid" style={{ gridTemplateRows: "minmax(0,1fr)" }}>
          {/* 左列 */}
          <div className="stack gap-12" style={{ minHeight: 0 }}>
            <div className="sc-panel" style={{ flex: "1 1 0", minHeight: 0 }}>
              <div className="row between">
                <div className="sc-title">核心指标</div>
                <span className="muted" style={{ fontSize: 9.5, letterSpacing: ".14em" }}>近 7 天</span>
              </div>
              <div className="sc-kpis mt-12" style={{ gridTemplateRows: "repeat(2, 1fr)" }}>
                {KPI_KEYS.map((k) => {
                  const mm = m[k];
                  if (!mm) return null;
                  const reliable = mm.has_baseline && Math.abs(mm.pct) <= 3;
                  const bad = reliable && ((k === "refund_rate" || k === "acos") ? mm.pct > 0 : mm.pct < 0);
                  const bar = reliable ? Math.min(100, Math.abs(mm.pct) * 220) : 4;
                  return (
                    <div className="sc-kpi" key={k}>
                      <span>{mm.label}</span>
                      <b style={{ color: "#e9efff" }}>
                        {mm.ratio ? pct(mm.current) : mm.unit === "count" ? mm.current.toFixed(0) : money(mm.current)}
                      </b>
                      <span style={{ color: !reliable ? "#93a1c0" : mm.pct > 0 ? "#4ef2c0" : "#ff7a9c", fontSize: 9.5 }}>
                        {!reliable ? "—" : `${mm.pct > 0 ? "▲" : "▼"} ${Math.abs(mm.pct * 100).toFixed(1)}%`}
                      </span>
                      <div className="sc-bar"><i style={{ width: `${Math.max(6, bar)}%`, opacity: bad ? .9 : .7 }} /></div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="sc-panel" style={{ flex: "1 1 0", minHeight: 0 }}>
              <div className="sc-title">类目毛利贡献</div>
              <Chart option={catOption} height={150} />
            </div>
          </div>

          {/* 中列 */}
          <div className="sc-panel stack" style={{ minHeight: 0, justifyContent: "space-between" }}>
            <div className="sc-ring-bg" />
            <div className="sc-hero" style={{ paddingTop: 4 }}>
              <span className="sc-hero-label">近 7 天贡献毛利</span>
              <span className="sc-hero-num">{money(heroValue)}</span>
              <span className="sc-hero-delta" style={{ color: (gm?.pct ?? 0) >= 0 ? "#4ef2c0" : "#ff7a9c" }}>
                环比 {(gm?.pct ?? 0) >= 0 ? "▲" : "▼"} {Math.abs((gm?.pct ?? 0) * 100).toFixed(1)}%
              </span>
              <div className="sc-tagline mt-8">
                毛利率 {marginRate.toFixed(1)}% · 订单 {orderCount.toFixed(0)}
              </div>
            </div>
            <div style={{ flex: 1, minHeight: 120, position: "relative", marginTop: 4 }}>
              <div style={{ position: "absolute", inset: 0 }}>
                <Chart option={trend} height="100%" />
              </div>
            </div>
          </div>

          {/* 右列 */}
          <div className="stack gap-12" style={{ minHeight: 0 }}>
            <div className="sc-panel" style={{ flex: "1 1 34%", minHeight: 0 }}>
              <div className="sc-title">异动监控</div>
              <div className="sc-list mt-12">
                {(data?.anomalies ?? []).slice(0, 4).map((a: any, i: number) => (
                  <div className="sc-row" key={a.sku_id}>
                    <span className="rk">{i + 1}</span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.title}</span>
                    <span style={{ color: a.current < 0 ? "#ff7a9c" : "#4ef2c0" }}>{money(a.current)}</span>
                  </div>
                ))}
                {(data?.anomalies ?? []).length === 0 && <span className="muted" style={{ fontSize: 11.5 }}>无显著异动</span>}
              </div>
            </div>

            <div className="sc-panel" style={{ flex: "1 1 30%", minHeight: 0 }}>
              <div className="sc-title">亏损 SKU</div>
              <div className="sc-list mt-12">
                {(data?.losers ?? []).slice(0, 4).map((r: any, i: number) => (
                  <div className="sc-row" key={r.sku_id}>
                    <span className="rk">{i + 1}</span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.title}</span>
                    <span style={{ color: "#ff7a9c" }}>{money(r.gross_margin)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="sc-panel" style={{ flex: "1 1 36%", minHeight: 0 }}>
              <div className="sc-title">AI 研判</div>
              <div className="stack gap-6 mt-12">
                <span style={{ fontSize: 11.5, lineHeight: 1.5 }}>
                  {data?.insight?.headline ?? "多智能体正在分析…"}
                </span>
                {(data?.insight?.actions ?? []).slice(0, 2).map((a, i) => (
                  <span className="muted" key={i} style={{ fontSize: 10.5 }}>· {a.title}</span>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="sc-marquee">
          <span className="tag">AI 研判</span>
          <div className="roll">
            <div className="roll-inner">
              {[0, 1].map((i) => (
                <span key={i}>
                  {data?.insight?.headline ?? "多智能体正在分析本周经营数据…"}
                  {data?.insight?.actions?.length
                    ? "　｜　建议：" + data.insight.actions.map((a) => a.title).join("；")
                    : ""}
                </span>
              ))}
            </div>
          </div>
          <span className="badge violet">置信度 {pct(data?.insight?.confidence ?? 0, 0)}</span>
        </div>
      </div>
    </div>
  );
}
