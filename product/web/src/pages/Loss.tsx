import { useState } from "react";
import { Button, Drawer, Space, Statistic, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";

import { getLoss, getSku } from "../api";
import {
  ActionCard,
  Bridge,
  ErrorBlock,
  LoadingBlock,
  Section,
  StatCard,
  count,
  downloadCsv,
  money,
  pct,
} from "../components";
import { usePeriod } from "../period";
import type { LossItem } from "../types";

const columns: ColumnsType<LossItem> = [
  {
    title: "商品",
    dataIndex: "sku",
    key: "sku",
    render: (_, row) => (
      <div>
        <strong>{row.sku}</strong>
        <div className="faint text-xs">
          {row.title}
          {row.merchant_sku && row.merchant_sku !== row.sku
            ? ` · 款号 ${row.merchant_sku}`
            : ""}
        </div>
      </div>
    ),
  },
  { title: "类目", dataIndex: "category", key: "category", render: (v: string | null) => v ?? "—" },
  {
    title: "净收入",
    dataIndex: "net_revenue",
    key: "net_revenue",
    align: "right",
    render: (v: number | null) => money(v),
  },
  {
    title: "退款率",
    dataIndex: "refund_rate",
    key: "refund_rate",
    align: "right",
    render: (v: number | null) => pct(v),
  },
  {
    title: "成本覆盖",
    dataIndex: "cost_coverage",
    key: "cost_coverage",
    align: "right",
    render: (v: number | null) => pct(v),
  },
  {
    title: "贡献毛利",
    dataIndex: "contribution_margin",
    key: "contribution_margin",
    align: "right",
    render: (v: number | null) => <span className="neg">{money(v)}</span>,
  },
  {
    title: "每单亏",
    dataIndex: "loss_per_order",
    key: "loss_per_order",
    align: "right",
    render: (v: number | null) => <span className="neg">{money(v)}</span>,
  },
  {
    title: "广告",
    dataIndex: "ad_spend",
    key: "ad_spend",
    align: "right",
    render: (v: number | null) => money(v),
  },
];

export function Loss() {
  const { range } = usePeriod();
  const [selected, setSelected] = useState<string | null>(null);
  const loss = useQuery({
    queryKey: ["loss", range],
    queryFn: () => getLoss(range),
  });
  const detail = useQuery({
    queryKey: ["sku", selected, range],
    queryFn: () => getSku(selected!, range),
    enabled: selected !== null,
  });

  if (loss.isLoading) return <LoadingBlock text="正在读取亏损商品…" />;
  if (loss.isError) return <ErrorBlock message={(loss.error as Error).message} />;
  const data = loss.data;
  if (!data) return null;

  const exportCsv = () =>
    downloadCsv(
      "loss-skus.csv",
      ["SKU", "标题", "类目", "净收入", "退款率", "成本覆盖", "贡献毛利", "每单亏", "广告"],
      data.items.map((item) => [
        item.sku,
        item.title,
        item.category,
        item.net_revenue,
        item.refund_rate,
        item.cost_coverage,
        item.contribution_margin,
        item.loss_per_order,
        item.ad_spend,
      ]),
    );

  return (
    <div className="space-y-6">
      <Section
        title={`亏损商品 · ${data.items.length} 个`}
        extra={
          <Space>
            <span className="faint text-xs">点击一行查看利润桥与证据</span>
            <Button onClick={exportCsv}>导出 CSV</Button>
          </Space>
        }
      >
        <Table
          size="small"
          rowKey="sku"
          pagination={false}
          columns={columns}
          dataSource={data.items}
          onRow={(row) => ({
            onClick: () => setSelected(row.sku),
            style: { cursor: "pointer" },
          })}
          locale={{ emptyText: "这一期没有已知成本的亏损 SKU" }}
        />
      </Section>

      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        width={720}
        title={detail.data ? `${detail.data.sku} ${detail.data.title}` : selected}
        className="drawer-body"
      >
        {detail.isLoading ? <LoadingBlock text="正在读取 SKU…" /> : null}
        {detail.isError ? <ErrorBlock message={(detail.error as Error).message} /> : null}
        {detail.data ? (
          <div className="space-y-4">
            <Space wrap>
              <Tag>{detail.data.category ?? "未分类"}</Tag>
              <Tag>{detail.data.supplier ?? "未知供应商"}</Tag>
              <Tag color="blue">快照 #{detail.data.snapshot_id}</Tag>
              <Tag>口径 {detail.data.metric_version}</Tag>
            </Space>

            <div className="grid grid-cols-2 gap-3">
              <StatCard label="贡献毛利" value={money(detail.data.contribution_margin)} />
              <StatCard label="每单亏" value={money(detail.data.loss_per_order)} />
              <StatCard label="退款率" value={pct(detail.data.refund_rate)} />
              <StatCard label="广告" value={money(detail.data.ad_spend)} />
            </div>

            <div>
              <Typography.Title level={5}>利润桥</Typography.Title>
              <Bridge rows={detail.data.profit_bridge} />
            </div>

            <Section title="证据">
              <Space size="large" wrap>
                <Statistic title="订单行" value={detail.data.evidence.orders} />
                <Statistic title="退款" value={detail.data.evidence.refunds} />
                <Statistic title="广告" value={detail.data.evidence.ads} />
                <Statistic title="成本" value={detail.data.evidence.costs} />
              </Space>
            </Section>

            <div>
              <Typography.Title level={5}>建议</Typography.Title>
              <div className="space-y-3">
                {detail.data.actions.map((action) => (
                  <ActionCard key={action.id} action={action} />
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </Drawer>

      <Space className="faint text-xs">
        <span>{data.period.start} ~ {data.period.end}</span>
        <span>共 {count(data.items.length)} 个亏损 SKU</span>
      </Space>
    </div>
  );
}
