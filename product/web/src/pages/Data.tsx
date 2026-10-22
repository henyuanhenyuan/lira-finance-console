import { useState } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Collapse,
  Descriptions,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  backup,
  clearConnector,
  configureConnector,
  confirmCost,
  confirmImport,
  deleteAlias,
  fetchDiagnostics,
  getAliases,
  getCatalogue,
  getConnectors,
  getDatasets,
  getEvidence,
  getHealth,
  getHistory,
  getImportStatus,
  getOps,
  getOverview,
  resetSample,
  scanInbox,
  testConnector,
  uploadCost,
  uploadImport,
  upsertAlias,
} from "../api";
import {
  ErrorBlock,
  JsonBlock,
  LoadingBlock,
  Section,
  StatCard,
  StatusItem,
  count,
  money,
  pct,
} from "../components";
import { usePeriod } from "../period";
import type {
  CostPreview,
  DatasetInfo,
  HistoryRun,
  ImportDataset,
  ImportPreview,
} from "../types";

const datasetOptions = [
  { value: "orders", label: "订单" },
  { value: "refunds", label: "退款" },
  { value: "ads", label: "广告" },
];

const sourceColumns: ColumnsType<{ name: string; latest: string | null; rows: number; status: string }> = [
  { title: "数据源", dataIndex: "name" },
  { title: "最新", dataIndex: "latest", render: (value: string | null) => value ?? "—" },
  { title: "行数", dataIndex: "rows", align: "right", render: (value: number) => count(value) },
  { title: "状态", dataIndex: "status", render: (value: string) => <Tag color={value === "ok" ? "green" : "default"}>{value}</Tag> },
];

const datasetColumns: ColumnsType<DatasetInfo> = [
  { title: "数据集", dataIndex: "dataset" },
  { title: "来源", dataIndex: "source" },
  { title: "行数", dataIndex: "rows", align: "right", render: (value: number) => count(value) },
  { title: "最新", dataIndex: "latest" },
  { title: "导入时间", dataIndex: "imported_at" },
];

export function Data() {
  const { range } = usePeriod();
  const client = useQueryClient();
  const [notice, setNotice] = useState<{ type: "success" | "error" | "warning"; text: string } | null>(null);

  const health = useQuery({ queryKey: ["health"], queryFn: getHealth });
  const status = useQuery({ queryKey: ["import-status"], queryFn: getImportStatus });
  const aliases = useQuery({ queryKey: ["aliases"], queryFn: getAliases });
  const connectors = useQuery({ queryKey: ["connectors"], queryFn: getConnectors });
  const history = useQuery({ queryKey: ["history"], queryFn: getHistory });
  const catalogue = useQuery({ queryKey: ["catalogue"], queryFn: getCatalogue });
  const ops = useQuery({ queryKey: ["ops"], queryFn: getOps });
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: getDatasets });
  const overview = useQuery({ queryKey: ["overview", range], queryFn: () => getOverview(range) });

  const refresh = () => client.invalidateQueries();

  const scan = useMutation({ mutationFn: scanInbox, onSuccess: () => { setNotice({ type: "success", text: "扫描完成" }); refresh(); } });
  const reset = useMutation({ mutationFn: resetSample, onSuccess: () => { setNotice({ type: "success", text: "已恢复样例数据" }); refresh(); } });
  const backupMutation = useMutation({
    mutationFn: backup,
    onSuccess: (data) => { setNotice({ type: "success", text: `已备份：${data.file}（${Math.round(data.bytes / 1024)} KB）` }); refresh(); },
  });

  const [importDataset, setImportDataset] = useState<ImportDataset>("orders");
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null);
  const [importMap, setImportMap] = useState<Record<string, string | null>>({});
  const [replace, setReplace] = useState(true);
  const [importResult, setImportResult] = useState<string | null>(null);

  const [costPreview, setCostPreview] = useState<CostPreview | null>(null);
  const [costMap, setCostMap] = useState<Record<string, string | null>>({});
  const [costResult, setCostResult] = useState<string | null>(null);

  const [aliasInputs, setAliasInputs] = useState<Record<string, string>>({});
  const [runEvidence, setRunEvidence] = useState<number | null>(null);
  const evidence = useQuery({
    queryKey: ["evidence", runEvidence],
    queryFn: () => getEvidence(runEvidence!),
    enabled: runEvidence !== null,
  });

  const [tb, setTb] = useState({ app_key: "", app_secret: "", session: "" });
  const [erp, setErp] = useState({ base_url: "", token: "" });
  const [connectorMessage, setConnectorMessage] = useState<string | null>(null);

  const previewImport = async (file: File) => {
    try {
      const data = await uploadImport(importDataset, file);
      setImportPreview(data);
      setImportMap(data.suggested);
      setImportResult(null);
    } catch (error) {
      setNotice({ type: "error", text: (error as Error).message });
    }
  };

  const previewCost = async (file: File) => {
    try {
      const data = await uploadCost(file);
      setCostPreview(data);
      setCostMap(data.suggested);
      setCostResult(null);
    } catch (error) {
      setNotice({ type: "error", text: (error as Error).message });
    }
  };

  const submitImport = async () => {
    if (!importPreview) return;
    try {
      const data = await confirmImport(importDataset, importPreview.upload_id, importMap, replace);
      setImportResult(
        `已导入 ${data.imported} 行；跳过 ${data.skipped} 行；重复 ${data.duplicates} 行。当前成本覆盖 ${pct(data.cost_coverage)}。`,
      );
      setImportPreview(null);
      refresh();
    } catch (error) {
      setNotice({ type: "error", text: (error as Error).message });
    }
  };

  const submitCost = async () => {
    if (!costPreview) return;
    try {
      const data = await confirmCost(costPreview.upload_id, costMap);
      setCostResult(
        `已导入 ${data.imported} 行；跳过 ${data.skipped} 行；当前成本覆盖 ${pct(data.cost_coverage)}${data.missing_skus.length ? `；仍缺 ${data.missing_skus.join("、")}` : "；已全部覆盖"}。`,
      );
      setCostPreview(null);
      refresh();
    } catch (error) {
      setNotice({ type: "error", text: (error as Error).message });
    }
  };

  const saveAlias = async (platform: string) => {
    const merchant = (aliasInputs[platform] ?? "").trim();
    if (!merchant) {
      setNotice({ type: "warning", text: "先填商家款号。" });
      return;
    }
    try {
      await upsertAlias(platform, merchant);
      setAliasInputs((previous) => ({ ...previous, [platform]: "" }));
      refresh();
    } catch (error) {
      setNotice({ type: "error", text: (error as Error).message });
    }
  };

  const removeAlias = async (platform: string) => {
    try {
      await deleteAlias(platform);
      refresh();
    } catch (error) {
      setNotice({ type: "error", text: (error as Error).message });
    }
  };

  const configure = async (name: "taobao" | "erp") => {
    try {
      if (name === "taobao") await configureConnector("taobao", tb);
      else await configureConnector("erp", erp);
      setConnectorMessage("凭证已加密保存。");
      if (name === "taobao") setTb({ app_key: "", app_secret: "", session: "" });
      else setErp({ base_url: "", token: "" });
      refresh();
    } catch (error) {
      setNotice({ type: "error", text: (error as Error).message });
    }
  };

  const test = async (name: "taobao" | "erp") => {
    try {
      const data = await testConnector(name);
      setConnectorMessage(data.message);
    } catch (error) {
      setNotice({ type: "error", text: (error as Error).message });
    }
  };

  const clear = async (name: "taobao" | "erp") => {
    try {
      await clearConnector(name);
      setConnectorMessage("凭证已清除。");
      refresh();
    } catch (error) {
      setNotice({ type: "error", text: (error as Error).message });
    }
  };

  const downloadDiagnostics = async () => {
    try {
      const blob = await fetchDiagnostics();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "lira-diagnostics.zip";
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      setNotice({ type: "error", text: (error as Error).message });
    }
  };

  const historyColumns: ColumnsType<HistoryRun> = [
    { title: "#", dataIndex: "id", width: 60 },
    { title: "类型", dataIndex: "kind", width: 100 },
    { title: "问题", dataIndex: "question", render: (value: string) => value || "经营总览" },
    { title: "快照", dataIndex: "snapshot_id", width: 80, render: (value: number) => `#${value}` },
    { title: "时间", dataIndex: "created_at", width: 190 },
    {
      title: "",
      key: "evidence",
      width: 80,
      render: (_, row) => <Button size="small" onClick={() => setRunEvidence(row.id)}>证据</Button>,
    },
  ];

  return (
    <div className="space-y-6">
      {notice ? <Alert type={notice.type} showIcon message={notice.text} closable onClose={() => setNotice(null)} /> : null}

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label="成本覆盖" value={pct(overview.data?.cost_coverage)} sub="导入成本后立即更新" />
        <StatCard label="亏损商品" value={count(overview.data?.loss_sku_count)} sub="已知成本" />
        <StatCard label="广告浪费" value={money(overview.data?.ad_waste_total)} sub="估算值" />
        <StatCard label="总收入" value={money(overview.data?.net_revenue)} sub="本期" />
      </div>

      <Section
        title="自动同步与连接器"
        extra={
          <Space>
            <Button loading={scan.isPending} onClick={() => scan.mutate()}>立即扫描</Button>
            <Button loading={reset.isPending} onClick={() => reset.mutate()}>恢复样例</Button>
          </Space>
        }
      >
        {status.isLoading ? <LoadingBlock /> : null}
        {status.isError ? <ErrorBlock message={(status.error as Error).message} /> : null}
        {status.data ? (
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <StatusItem name="导出文件夹" value="监听中" sub={status.data.inbox} />
            <StatusItem
              name="扫描模式"
              value={status.data.watcher === "event+poll" ? "文件事件 + 定时兜底" : "定时轮询"}
              sub={`${status.data.interval_s}s`}
            />
            <StatusItem name="待处理" value={String(status.data.pending.length)} sub={status.data.pending.join("、") || "没有新文件"} />
            <StatusItem name="本地模型" value={status.data.model.available ? "可用" : "未启用"} sub={status.data.model.model} />
          </div>
        ) : null}
        <p className="muted mt-3 text-xs">
          最近导入：{status.data?.last ? `${status.data.last.dataset} · ${status.data.last.filename} · ${status.data.last.imported} 行 · ${status.data.last.status}` : "还没有"}
        </p>
      </Section>

      <Section title="连接器与凭证">
        {connectors.data ? (
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <StatusItem name="导出文件夹" value={connectors.data.folder.configured ? "已启用" : "未启用"} sub={connectors.data.folder.inbox} />
            <StatusItem name="淘宝开放平台" value={connectors.data.taobao.configured ? "已配置" : "未配置"} sub={connectors.data.taobao.message} />
            <StatusItem name="ERP" value={connectors.data.erp.configured ? "已配置" : "未配置"} sub={connectors.data.erp.message} />
            <StatusItem name="配额" value={`${connectors.data.quota.per_minute}/分钟`} sub={`淘宝剩余 ${connectors.data.quota.remaining.taobao ?? "—"}`} />
          </div>
        ) : null}
        <p className="muted mt-3 text-xs">{connectors.data?.pii.policy}</p>
        <Collapse
          className="mt-3"
          ghost
          items={[
            {
              key: "taobao",
              label: "配置淘宝开放平台凭证",
              children: (
                <div className="space-y-3">
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                    <Input placeholder="App Key" value={tb.app_key} onChange={(e) => setTb({ ...tb, app_key: e.target.value })} />
                    <Input.Password placeholder="App Secret" value={tb.app_secret} onChange={(e) => setTb({ ...tb, app_secret: e.target.value })} />
                    <Input.Password placeholder="商家 Session" value={tb.session} onChange={(e) => setTb({ ...tb, session: e.target.value })} />
                  </div>
                  <Space>
                    <Button type="primary" onClick={() => configure("taobao")}>保存</Button>
                    <Button onClick={() => test("taobao")}>测试</Button>
                    <Button onClick={() => clear("taobao")}>清除</Button>
                  </Space>
                </div>
              ),
            },
            {
              key: "erp",
              label: "配置 ERP 凭证",
              children: (
                <div className="space-y-3">
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                    <Input placeholder="ERP 地址" value={erp.base_url} onChange={(e) => setErp({ ...erp, base_url: e.target.value })} />
                    <Input.Password placeholder="Token" value={erp.token} onChange={(e) => setErp({ ...erp, token: e.target.value })} />
                  </div>
                  <Space>
                    <Button type="primary" onClick={() => configure("erp")}>保存</Button>
                    <Button onClick={() => test("erp")}>测试</Button>
                    <Button onClick={() => clear("erp")}>清除</Button>
                  </Space>
                </div>
              ),
            },
          ]}
        />
        {connectorMessage ? <Alert className="mt-3" type="info" showIcon message={connectorMessage} /> : null}
      </Section>

      <Section title="数据源">
        {health.isLoading ? <LoadingBlock /> : null}
        {health.isError ? <ErrorBlock message={(health.error as Error).message} /> : null}
        {health.data ? (
          <>
            <Table size="small" rowKey="name" pagination={false} columns={sourceColumns} dataSource={health.data.sources} />
            {health.data.missing_skus.length ? (
              <Alert className="mt-3" type="warning" showIcon message={`缺少成本：${health.data.missing_skus.join("、")}`} />
            ) : null}
            <p className="muted mt-3 text-xs">
              成本覆盖 {pct(health.data.coverage)} · 快照 #{health.data.snapshot_id} · 最近同步 {health.data.last_sync ?? "—"}
            </p>
          </>
        ) : null}
      </Section>

      <Section title="导入订单 / 退款 / 广告">
        <Space wrap>
          <Select value={importDataset} onChange={(value) => setImportDataset(value as ImportDataset)} options={datasetOptions} style={{ width: 120 }} />
          <Upload showUploadList={false} accept=".csv,.xlsx,.xlsm" beforeUpload={(file) => { void previewImport(file as File); return false; }}>
            <Button>选择文件</Button>
          </Upload>
          <Checkbox checked={replace} onChange={(e) => setReplace(e.target.checked)}>替换整个数据集</Checkbox>
        </Space>
        {importPreview ? (
          <div className="mt-4 space-y-3">
            <Typography.Text className="muted">
              {importPreview.filename} · {importPreview.row_count} 行 · {importPreview.dataset}
            </Typography.Text>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {importPreview.targets.map((target) => (
                <div key={target.key}>
                  <div className="muted mb-1 text-xs">
                    {target.label}{target.required ? <span className="neg"> *</span> : null}
                  </div>
                  <Select
                    style={{ width: "100%" }}
                    allowClear
                    placeholder="（不使用）"
                    value={importMap[target.key] ?? undefined}
                    onChange={(value) => setImportMap({ ...importMap, [target.key]: value ?? null })}
                    options={importPreview.headers.map((header) => ({ value: header, label: header }))}
                  />
                </div>
              ))}
            </div>
            <Table
              size="small"
              pagination={false}
              rowKey={(_, index) => String(index ?? 0)}
              columns={importPreview.headers.map((header) => ({ title: header, dataIndex: header, key: header }))}
              dataSource={importPreview.preview.map((row) =>
                Object.fromEntries(importPreview.headers.map((header, index) => [header, row[index]])),
              )}
              scroll={{ x: true }}
            />
            <Button type="primary" onClick={submitImport}>导入</Button>
          </div>
        ) : null}
        {importResult ? <Alert className="mt-3" type="success" showIcon message={importResult} /> : null}
      </Section>

      <Section title="SKU 映射">
        {aliases.data ? (
          <div className="space-y-3">
            {aliases.data.unresolved.length === 0 ? (
              <span className="muted text-sm">所有订单 SKU 都已匹配到成本。</span>
            ) : (
              aliases.data.unresolved.map((sku) => (
                <div key={sku} className="flex flex-wrap items-center gap-2 border-b border-[var(--color-line)] py-2">
                  <Tag>{sku}</Tag>
                  <Input
                    style={{ maxWidth: 260 }}
                    placeholder="商家款号，例如 A001"
                    value={aliasInputs[sku] ?? ""}
                    onChange={(e) => setAliasInputs({ ...aliasInputs, [sku]: e.target.value })}
                  />
                  <Button onClick={() => saveAlias(sku)}>保存</Button>
                </div>
              ))
            )}
            {aliases.data.aliases.length ? (
              <div className="pt-2">
                <Typography.Text strong>已有别名</Typography.Text>
                {aliases.data.aliases.map((alias) => (
                  <div key={alias.platform_sku} className="flex flex-wrap items-center gap-2 border-b border-[var(--color-line)] py-2">
                    <Tag>{alias.platform_sku}</Tag>
                    <span>→</span>
                    <Tag color="blue">{alias.merchant_sku}</Tag>
                    <Button size="small" onClick={() => removeAlias(alias.platform_sku)}>删除</Button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : <LoadingBlock />}
      </Section>

      <Section
        title="导入成本表"
        extra={<a href="/api/v1/costs/template" download>下载模板</a>}
      >
        <Upload showUploadList={false} accept=".csv,.xlsx,.xlsm" beforeUpload={(file) => { void previewCost(file as File); return false; }}>
          <Button>选择成本表</Button>
        </Upload>
        {costPreview ? (
          <div className="mt-4 space-y-3">
            <Typography.Text className="muted">
              {costPreview.filename} · {costPreview.row_count} 行
            </Typography.Text>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {[
                ["sku", "商品编码", true],
                ["effective_from", "生效日期", true],
                ["unit_cost", "采购单价", true],
                ["shipping_cost", "运费", false],
                ["packaging_cost", "包材", false],
              ].map(([key, label, required]) => (
                <div key={String(key)}>
                  <div className="muted mb-1 text-xs">
                    {String(label)}{required ? <span className="neg"> *</span> : null}
                  </div>
                  <Select
                    style={{ width: "100%" }}
                    allowClear
                    placeholder="（不使用）"
                    value={costMap[String(key)] ?? undefined}
                    onChange={(value) => setCostMap({ ...costMap, [String(key)]: value ?? null })}
                    options={costPreview.headers.map((header) => ({ value: header, label: header }))}
                  />
                </div>
              ))}
            </div>
            <Button type="primary" onClick={submitCost}>导入成本</Button>
          </div>
        ) : null}
        {costResult ? <Alert className="mt-3" type="success" showIcon message={costResult} /> : null}
      </Section>

      <Section title="历史与证据">
        {history.isLoading ? <LoadingBlock /> : null}
        {history.isError ? <ErrorBlock message={(history.error as Error).message} /> : null}
        {history.data ? (
          <>
            <Table size="small" rowKey="id" pagination={{ pageSize: 8 }} columns={historyColumns} dataSource={history.data.runs} />
            <div className="mt-4">
              <Typography.Text strong>采纳 / 忽略</Typography.Text>
              <Table
                className="mt-2"
                size="small"
                rowKey={(row) => `${row.action_id}-${row.updated_at}`}
                pagination={false}
                dataSource={history.data.actions}
                columns={[
                  { title: "动作", dataIndex: "action_id" },
                  { title: "状态", dataIndex: "status", render: (value: string) => <Tag>{value}</Tag> },
                  { title: "时间", dataIndex: "updated_at" },
                ]}
              />
            </div>
          </>
        ) : null}
        <Modal open={runEvidence !== null} onCancel={() => setRunEvidence(null)} footer={null} width={760} title="分析证据">
          {evidence.isLoading ? <LoadingBlock /> : null}
          {evidence.data ? <JsonBlock value={evidence.data} /> : null}
        </Modal>
      </Section>

      <Section title="指标与口径">
        {catalogue.data ? (
          <>
            <p className="muted text-xs">口径版本 {catalogue.data.version}</p>
            <Table
              size="small"
              rowKey="name"
              pagination={false}
              dataSource={catalogue.data.metrics}
              columns={[
                { title: "指标", dataIndex: "label", render: (_value, row) => <div><strong>{row.label}</strong><div className="faint text-xs">{row.name}</div></div> },
                { title: "定义", dataIndex: "description" },
                { title: "单位", dataIndex: "unit" },
              ]}
            />
            <Space wrap className="mt-3">
              {catalogue.data.dimensions.map((dimension) => (
                <Tag key={dimension.name} color="blue">{dimension.label} {dimension.name}</Tag>
              ))}
            </Space>
          </>
        ) : <LoadingBlock />}
      </Section>

      <Section
        title="运维"
        extra={
          <Space>
            <Button type="primary" loading={backupMutation.isPending} onClick={() => backupMutation.mutate()}>立即备份</Button>
            <Button onClick={downloadDiagnostics}>下载诊断包</Button>
          </Space>
        }
      >
        {ops.data ? (
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <StatusItem name="版本" value={ops.data.version} sub={`口径 ${overview.data?.metric_version ?? "—"}`} />
            <StatusItem name="快照" value={`#${ops.data.snapshot_id}`} sub="当前数据版本" />
            <StatusItem name="数据库" value={`${Math.round(ops.data.db_bytes / 1024)} KB`} sub={`分析记录 ${ops.data.analysis_runs} 条`} />
            <StatusItem name="备份" value={ops.data.backup_key === "env" ? "环境密钥" : "本机密钥"} sub={`${ops.data.backups.length} 个备份`} />
          </div>
        ) : <LoadingBlock />}
        {ops.data?.backups.length ? (
          <Descriptions className="mt-3" size="small" column={1} items={ops.data.backups.map((item) => ({ key: item.file, label: item.file, children: `${Math.round(item.bytes / 1024)} KB` }))} />
        ) : null}
      </Section>

      <Section title="数据集注册表">
        {datasets.data ? (
          <Table size="small" rowKey="dataset" pagination={false} columns={datasetColumns} dataSource={datasets.data.datasets} />
        ) : <LoadingBlock />}
      </Section>

      <p className="faint text-center text-xs">
        本地运行 · 文件只在本机解析 · 不上传
      </p>
    </div>
  );
}
