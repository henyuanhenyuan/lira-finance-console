import { useEffect, useRef, type ReactNode } from "react";
import { Alert, Button, Card, Space, Spin, Tag, Typography } from "antd";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as echarts from "echarts";

import { ackAction } from "./api";
import type { Action, BridgeRow, TrendRow } from "./types";

export function money(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return `¥${Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function pct(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined) return "—";
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export function count(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return Number(value).toLocaleString("zh-CN");
}

export function Section({
  title,
  extra,
  children,
  className = "",
}: {
  title?: string;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card
      className={className}
      title={title}
      extra={extra}
      styles={{ body: { padding: 18 } }}
      style={{ borderRadius: 12, borderColor: "var(--color-line)" }}
    >
      {children}
    </Card>
  );
}

export function StatCard({
  label,
  value,
  sub,
  badge,
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  badge?: ReactNode;
}) {
  return (
    <Card
      styles={{ body: { padding: 16 } }}
      style={{ borderRadius: 12, borderColor: "var(--color-line)" }}
    >
      <div className="muted text-xs">{label}</div>
      <div className="figure mt-1 flex flex-wrap items-baseline gap-2 text-2xl font-semibold">
        {value}
        {badge}
      </div>
      {sub ? <div className="faint mt-1 text-xs">{sub}</div> : null}
    </Card>
  );
}

export function ComparisonBadge({
  change,
  comparable,
}: {
  change: number | null;
  comparable: boolean;
}) {
  if (!comparable || change === null) {
    return <span className="faint text-xs">无可比</span>;
  }
  const up = change >= 0;
  return (
    <span className={`text-xs font-medium ${up ? "pos" : "neg"}`}>
      {up ? "+" : ""}
      {(change * 100).toFixed(1)}%
    </span>
  );
}

const kindLabels: Record<string, string> = {
  loss: "亏损",
  ad: "广告",
  refund: "退款",
  data: "数据",
};

export function ActionCard({ action }: { action: Action }) {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: (status: string) => ackAction(action.id, status),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["overview"] });
      client.invalidateQueries({ queryKey: ["history"] });
      client.invalidateQueries({ queryKey: ["sku"] });
    },
  });

  return (
    <Card
      className={`action ${action.kind}`}
      styles={{ body: { padding: 16 } }}
      style={{ borderRadius: 12, borderColor: "var(--color-line)" }}
    >
      <Space size={6}>
        <Tag color={action.kind === "ad" ? "purple" : action.kind === "refund" ? "orange" : "blue"}>
          {kindLabels[action.kind] ?? action.kind}
        </Tag>
        <span className="faint text-xs">置信 {action.confidence}</span>
      </Space>
      <Typography.Title level={5} style={{ margin: "8px 0 4px" }}>
        {action.title}
      </Typography.Title>
      <div className="muted min-h-[38px] text-[13px]">{action.reason}</div>
      <div className="my-2 font-medium">影响 {money(action.impact)} / 月</div>
      <Space>
        <Button
          type="primary"
          loading={mutation.isPending}
          onClick={() => mutation.mutate("adopted")}
        >
          采纳
        </Button>
        <Button
          loading={mutation.isPending}
          onClick={() => mutation.mutate("ignored")}
        >
          忽略
        </Button>
      </Space>
      {mutation.isSuccess ? (
        <div className="pos mt-2 text-xs">
          已{mutation.variables === "adopted" ? "采纳" : "忽略"}
        </div>
      ) : null}
    </Card>
  );
}

export function Bridge({ rows }: { rows: BridgeRow[] }) {
  const max = Math.max(1, ...rows.map((row) => Math.abs(Number(row.value) || 0)));
  return (
    <div>
      {rows.map((row) => {
        const value = Number(row.value) || 0;
        const width = Math.min(100, (Math.abs(value) / max) * 100);
        return (
          <div
            key={row.label}
            className="grid grid-cols-[100px_1fr_120px] items-center gap-3 py-1"
          >
            <span>{row.label}</span>
            <div className="h-2 overflow-hidden rounded bg-blue-50">
              <div
                className="h-full rounded"
                style={{
                  width: `${width}%`,
                  background: value < 0 ? "var(--color-fall)" : "var(--color-brand)",
                }}
              />
            </div>
            <span className={`figure text-right ${value < 0 ? "neg" : ""}`}>
              {money(value)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function TrendChart({ rows }: { rows: TrendRow[] }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(
      {
        grid: { left: 16, right: 16, top: 36, bottom: 24, containLabel: true },
        tooltip: {
          trigger: "axis",
          valueFormatter: (value: unknown) => money(Number(value)),
        },
        legend: { right: 0, top: 0, icon: "roundRect", itemWidth: 8, itemHeight: 8 },
        xAxis: {
          type: "category",
          data: rows.map((row) => row.bucket),
          axisLine: { lineStyle: { color: "#e8ecf1" } },
          axisTick: { show: false },
          axisLabel: { color: "#98a2b3", fontSize: 11 },
        },
        yAxis: {
          type: "value",
          splitLine: { lineStyle: { color: "#f1f4f8" } },
          axisLabel: { color: "#98a2b3", fontSize: 11 },
        },
        series: [
          {
            name: "净收入",
            type: "line",
            smooth: true,
            symbol: "circle",
            symbolSize: 5,
            data: rows.map((row) => row.net_revenue),
            lineStyle: { width: 2.5, color: "#2f6bff" },
            itemStyle: { color: "#2f6bff" },
            areaStyle: { color: "rgba(47,107,255,0.08)" },
          },
          {
            name: "贡献毛利",
            type: "line",
            smooth: true,
            symbol: "none",
            data: rows.map((row) => row.contribution_margin ?? 0),
            lineStyle: { width: 2, color: "#7c3aed" },
            itemStyle: { color: "#7c3aed" },
          },
        ],
      },
      { notMerge: true },
    );
  }, [rows]);

  return <div ref={ref} className="trend-chart" />;
}

export function JsonBlock({ value }: { value: unknown }) {
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}

export function StatusItem({
  name,
  value,
  sub,
}: {
  name: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--color-line)] p-3">
      <div className="font-medium">{name}</div>
      <div className="muted text-xs break-words">{value}</div>
      {sub ? <div className="faint text-xs break-words">{sub}</div> : null}
    </div>
  );
}

export function LoadingBlock({ text = "正在读取…" }: { text?: string }) {
  return (
    <div className="flex items-center gap-3 py-6">
      <Spin size="small" />
      <span className="muted text-sm">{text}</span>
    </div>
  );
}

export function ErrorBlock({ message }: { message: string }) {
  return <Alert type="error" showIcon message={message} style={{ marginBottom: 16 }} />;
}

export function downloadCsv(name: string, headers: string[], rows: (string | number | null)[][]) {
  const escape = (value: string | number | null) =>
    `"${String(value ?? "").replace(/"/g, '""')}"`;
  const text =
    "﻿" + [headers, ...rows].map((row) => row.map(escape).join(",")).join("\n");
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}
