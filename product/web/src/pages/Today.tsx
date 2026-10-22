import { Alert, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";

import { getOverview, getTrend } from "../api";
import {
  ActionCard,
  Bridge,
  ComparisonBadge,
  ErrorBlock,
  LoadingBlock,
  Section,
  StatCard,
  TrendChart,
  count,
  money,
  pct,
} from "../components";
import { usePeriod } from "../period";
import type { Category, Comparison } from "../types";

const comparisonColumns: ColumnsType<Comparison> = [
  { title: "指标", dataIndex: "label", key: "label" },
  {
    title: "本期",
    dataIndex: "current",
    key: "current",
    align: "right",
    render: (value: number | null, row) =>
      row.unit === "count" ? count(value) : money(value),
  },
  {
    title: "上一期",
    dataIndex: "previous",
    key: "previous",
    align: "right",
    render: (value: number | null, row) =>
      row.unit === "count" ? count(value) : money(value),
  },
  {
    title: "变化",
    key: "change",
    align: "right",
    render: (_, row) => (
      <ComparisonBadge change={row.change} comparable={row.comparable} />
    ),
  },
];

const categoryColumns: ColumnsType<Category> = [
  { title: "类目", dataIndex: "category", key: "category" },
  {
    title: "净收入",
    dataIndex: "net_revenue",
    key: "net_revenue",
    align: "right",
    render: (value: number | null) => money(value),
  },
  {
    title: "占比",
    dataIndex: "share",
    key: "share",
    align: "right",
    render: (value: number | null) => pct(value),
  },
  {
    title: "贡献毛利",
    dataIndex: "contribution_margin",
    key: "contribution_margin",
    align: "right",
    render: (value: number | null) => (
      <span className={(value ?? 0) < 0 ? "neg" : ""}>{money(value)}</span>
    ),
  },
  {
    title: "订单",
    dataIndex: "orders",
    key: "orders",
    align: "right",
    render: (value: number) => count(value),
  },
];

export function Today() {
  const { range } = usePeriod();
  const overview = useQuery({
    queryKey: ["overview", range],
    queryFn: () => getOverview(range),
  });
  const trend = useQuery({
    queryKey: ["trend", range],
    queryFn: () => getTrend(range),
  });

  if (overview.isLoading) return <LoadingBlock text="正在读取经营总览…" />;
  if (overview.isError) return <ErrorBlock message={(overview.error as Error).message} />;
  const data = overview.data;
  if (!data) return null;

  return (
    <div className="space-y-6">
      {data.warnings.map((warning) => (
        <Alert key={warning} type="warning" showIcon message={warning} />
      ))}

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard
          label="贡献毛利（已知成本）"
          value={money(data.contribution_margin)}
          sub={`总收入 ${money(data.net_revenue)}`}
          badge={
            <ComparisonBadge
              change={data.comparisons.find((item) => item.metric === "contribution_margin")?.change ?? null}
              comparable={
                data.comparisons.find((item) => item.metric === "contribution_margin")?.comparable ?? false
              }
            />
          }
        />
        <StatCard
          label="净收入"
          value={money(data.net_revenue)}
          sub="实付减退款"
          badge={
            <ComparisonBadge
              change={data.comparisons.find((item) => item.metric === "net_revenue")?.change ?? null}
              comparable={
                data.comparisons.find((item) => item.metric === "net_revenue")?.comparable ?? false
              }
            />
          }
        />
        <StatCard
          label="订单数"
          value={count(data.order_count)}
          sub={`销售件数 ${count(data.units_sold)}`}
          badge={
            <ComparisonBadge
              change={data.comparisons.find((item) => item.metric === "order_count")?.change ?? null}
              comparable={
                data.comparisons.find((item) => item.metric === "order_count")?.comparable ?? false
              }
            />
          }
        />
        <StatCard
          label="客单价"
          value={money(data.aov)}
          sub="净收入 / 订单数"
          badge={
            <ComparisonBadge
              change={data.comparisons.find((item) => item.metric === "aov")?.change ?? null}
              comparable={
                data.comparisons.find((item) => item.metric === "aov")?.comparable ?? false
              }
            />
          }
        />
        <StatCard label="成本覆盖" value={pct(data.cost_coverage)} sub="低于 80% 时利润为估算" />
        <StatCard label="亏损商品" value={count(data.loss_sku_count)} sub="已知成本且贡献毛利为负" />
        <StatCard label="广告浪费" value={money(data.ad_waste_total)} sub="估算值" />
        <StatCard label="数据快照" value={`#${data.snapshot_id}`} sub={`口径版本 ${data.metric_version}`} />
      </div>

      <Section title="变化与异常">
        <Table
          size="small"
          rowKey="metric"
          pagination={false}
          columns={comparisonColumns}
          dataSource={data.comparisons}
        />
        <div className="mt-4 space-y-2">
          <Typography.Text strong>异常</Typography.Text>
          {data.anomalies.length === 0 ? (
            <div className="muted text-sm">没有超过 20% 阈值的波动。</div>
          ) : (
            data.anomalies.map((item) => (
              <Alert
                key={item.metric}
                type={item.direction === "上升" ? "success" : "warning"}
                showIcon
                message={`${item.label} ${item.direction} ${(Math.abs(item.change) * 100).toFixed(1)}%`}
                description={`${item.previous} → ${item.current}`}
              />
            ))
          )}
        </div>
      </Section>

      <Section title="销售趋势">
        {trend.isLoading ? (
          <LoadingBlock />
        ) : trend.isError ? (
          <ErrorBlock message={(trend.error as Error).message} />
        ) : (
          <TrendChart rows={trend.data?.rows ?? []} />
        )}
      </Section>

      <div>
        <Typography.Title level={3} style={{ fontSize: 16, marginBottom: 12 }}>
          今天要处理的三件事
        </Typography.Title>
        {data.actions.length === 0 ? (
          <Section>
            <span className="muted">这一期没有发现需要处理的异常。</span>
          </Section>
        ) : (
          <div className="grid gap-4 lg:grid-cols-3">
            {data.actions.map((action) => (
              <ActionCard key={action.id} action={action} />
            ))}
          </div>
        )}
      </div>

      <Section
        title="利润桥"
        extra={<span className="faint text-xs">已知成本部分 · 覆盖 {pct(data.cost_coverage)}</span>}
      >
        <Bridge rows={data.profit_bridge} />
      </Section>

      <Section title="类目结构">
        <Table
          size="small"
          rowKey="category"
          pagination={false}
          columns={categoryColumns}
          dataSource={data.categories}
        />
      </Section>

      <Space className="faint text-xs">
        <span>
          {data.period.start} ~ {data.period.end}
        </span>
        <span>快照 #{data.snapshot_id}</span>
        <Tag color="blue">本地 DuckDB</Tag>
      </Space>
    </div>
  );
}
