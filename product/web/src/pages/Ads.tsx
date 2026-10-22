import { Button, Space, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";

import { getAds } from "../api";
import {
  ErrorBlock,
  LoadingBlock,
  Section,
  downloadCsv,
  money,
} from "../components";
import { usePeriod } from "../period";
import type { AdItem } from "../types";

const columns: ColumnsType<AdItem> = [
  { title: "计划", dataIndex: "campaign", key: "campaign" },
  { title: "SKU", dataIndex: "sku", key: "sku" },
  {
    title: "花费",
    dataIndex: "spend",
    key: "spend",
    align: "right",
    render: (value: number) => money(value),
  },
  {
    title: "成交",
    dataIndex: "attributed_revenue",
    key: "attributed_revenue",
    align: "right",
    render: (value: number) => money(value),
  },
  {
    title: "ROI",
    dataIndex: "roi",
    key: "roi",
    align: "right",
    render: (value: number | null) => (value === null ? "—" : value.toFixed(2)),
  },
  {
    title: "盈亏平衡 ROI",
    dataIndex: "breakeven_roi",
    key: "breakeven_roi",
    align: "right",
    render: (value: number | null) => (value === null ? "—" : value.toFixed(2)),
  },
  {
    title: "估算浪费",
    dataIndex: "waste",
    key: "waste",
    align: "right",
    render: (value: number) => <span className="neg">{money(value)}</span>,
  },
  {
    title: "建议",
    dataIndex: "suggestion",
    key: "suggestion",
    render: (value: string) => <Tag>{value}</Tag>,
  },
];

export function Ads() {
  const { range } = usePeriod();
  const ads = useQuery({ queryKey: ["ads", range], queryFn: () => getAds(range) });

  if (ads.isLoading) return <LoadingBlock text="正在读取广告浪费…" />;
  if (ads.isError) return <ErrorBlock message={(ads.error as Error).message} />;
  const data = ads.data;
  if (!data) return null;

  const exportCsv = () =>
    downloadCsv(
      "ad-waste.csv",
      ["计划", "SKU", "花费", "成交", "ROI", "盈亏平衡ROI", "估算浪费", "建议"],
      data.items.map((item) => [
        item.campaign,
        item.sku,
        item.spend,
        item.attributed_revenue,
        item.roi,
        item.breakeven_roi,
        item.waste,
        item.suggestion,
      ]),
    );

  return (
    <div className="space-y-6">
      <Section
        title={`广告浪费 · 估算 ${money(data.total_waste)}`}
        extra={
          <Space>
            <span className="faint text-xs">口径：花费超过广告前利润的部分</span>
            <Button onClick={exportCsv}>导出 CSV</Button>
          </Space>
        }
      >
        <Table
          size="small"
          rowKey={(row) => `${row.campaign}-${row.sku}`}
          pagination={false}
          columns={columns}
          dataSource={data.items}
          locale={{ emptyText: "这一期没有发现广告浪费" }}
        />
      </Section>

      <Space className="faint text-xs">
        <span>{data.period.start} ~ {data.period.end}</span>
        <span>快照 #{data.snapshot_id} · 口径 {data.metric_version}</span>
      </Space>
    </div>
  );
}
