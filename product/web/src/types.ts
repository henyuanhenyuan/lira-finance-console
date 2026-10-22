export interface TimeRange {
  start: string;
  end: string;
}

export interface Comparison {
  metric: string;
  label: string;
  current: number | null;
  previous: number | null;
  change: number | null;
  comparable: boolean;
  unit: string;
}

export interface Anomaly {
  metric: string;
  label: string;
  current: number;
  previous: number;
  change: number;
  direction: string;
}

export interface Action {
  id: string;
  kind: string;
  title: string;
  reason: string;
  impact: number;
  confidence: string;
}

export interface Category {
  category: string;
  net_revenue: number | null;
  contribution_margin: number | null;
  orders: number;
  share: number | null;
}

export interface BridgeRow {
  label: string;
  value: number | null;
}

export interface Overview {
  period: TimeRange;
  previous_period: TimeRange;
  snapshot_id: number;
  metric_version: string;
  net_revenue: number;
  known_net_revenue: number;
  contribution_margin: number | null;
  cost_coverage: number | null;
  order_count: number;
  units_sold: number;
  aov: number | null;
  loss_sku_count: number;
  ad_waste_total: number;
  comparisons: Comparison[];
  anomalies: Anomaly[];
  categories: Category[];
  profit_bridge: BridgeRow[];
  actions: Action[];
  warnings: string[];
  freshness: Record<string, string | null>;
  evidence: Record<string, unknown>;
}

export interface LossItem {
  sku: string;
  title: string;
  category: string | null;
  supplier: string | null;
  merchant_sku: string | null;
  net_revenue: number | null;
  refund_rate: number | null;
  cost_coverage: number | null;
  contribution_margin: number | null;
  loss_per_order: number | null;
  ad_spend: number | null;
}

export interface LossResponse {
  period: TimeRange;
  snapshot_id: number;
  metric_version: string;
  items: LossItem[];
}

export interface AdItem {
  sku: string;
  title: string;
  campaign: string;
  spend: number;
  attributed_revenue: number;
  roi: number | null;
  breakeven_roi: number | null;
  waste: number;
  suggestion: string;
}

export interface AdResponse {
  period: TimeRange;
  snapshot_id: number;
  metric_version: string;
  total_waste: number;
  items: AdItem[];
}

export interface TrendRow {
  bucket: string;
  net_revenue: number;
  contribution_margin: number | null;
}

export interface TrendResponse {
  granularity: string;
  period: TimeRange;
  snapshot_id: number;
  metric_version: string;
  rows: TrendRow[];
}

export interface SkuDetail {
  period: TimeRange;
  snapshot_id: number;
  metric_version: string;
  sku: string;
  title: string;
  category: string | null;
  supplier: string | null;
  merchant_sku: string | null;
  net_revenue: number | null;
  refund_rate: number | null;
  cost_coverage: number | null;
  contribution_margin: number | null;
  loss_per_order: number | null;
  ad_spend: number | null;
  profit_bridge: BridgeRow[];
  actions: Action[];
  evidence: {
    orders: number;
    refunds: number;
    ads: number;
    costs: number;
  };
}

export interface HealthSource {
  name: string;
  latest: string | null;
  rows: number;
  status: string;
}

export interface DataHealth {
  period: TimeRange;
  snapshot_id: number;
  metric_version: string;
  coverage: number | null;
  missing_skus: string[];
  sources: HealthSource[];
  last_sync: string | null;
  warnings: string[];
}

export interface ImportLast {
  at: string;
  dataset: string;
  filename: string;
  imported: number;
  skipped: number;
  status: string;
}

export interface ImportStatus {
  inbox: string;
  pending: string[];
  processed: number;
  failed: number;
  last: ImportLast | null;
  interval_s: number;
  watcher: string;
  model: { url: string; model: string; available: boolean };
}

export interface AliasData {
  aliases: { platform_sku: string; merchant_sku: string }[];
  unresolved: string[];
}

export interface ConnectorData {
  folder: { configured: boolean; inbox: string; mode: string };
  taobao: { configured: boolean; message: string };
  erp: { configured: boolean; message: string };
  pii: { policy: string };
  quota: { per_minute: number; remaining: Record<string, number> };
}

export interface HistoryRun {
  id: number;
  snapshot_id: number;
  kind: string;
  question: string;
  intent: string;
  created_at: string;
}

export interface HistoryAction {
  action_id: string;
  status: string;
  note: string;
  updated_at: string;
}

export interface HistoryData {
  runs: HistoryRun[];
  actions: HistoryAction[];
}

export interface CatalogueMetric {
  name: string;
  label: string;
  description: string;
  unit: string;
}

export interface CatalogueDimension {
  name: string;
  label: string;
  description: string;
}

export interface Catalogue {
  version: string;
  metrics: CatalogueMetric[];
  dimensions: CatalogueDimension[];
}

export interface BackupInfo {
  file: string;
  bytes: number;
}

export interface OpsStatus {
  version: string;
  snapshot_id: number;
  counts: Record<string, number>;
  analysis_runs: number;
  last_sync: string | null;
  db_bytes: number;
  backups: BackupInfo[];
  backup_key: string;
}

export interface AskResult {
  question: string;
  answer: string;
  intent: string;
  generated: boolean;
  reason: string;
  evidence: Record<string, unknown>;
}

export interface DatasetInfo {
  dataset: string;
  source: string;
  rows: number;
  latest: string;
  imported_at: string;
  note: string;
}

export interface DatasetRegistry {
  datasets: DatasetInfo[];
}

export type ImportDataset = "orders" | "refunds" | "ads";

export interface ImportTarget {
  key: string;
  label: string;
  required: boolean;
}

export interface ImportPreview {
  dataset: ImportDataset;
  upload_id: string;
  filename: string;
  headers: string[];
  row_count: number;
  preview: string[][];
  suggested: Record<string, string | null>;
  targets: ImportTarget[];
}

export interface CostPreview {
  upload_id: string;
  filename: string;
  headers: string[];
  row_count: number;
  preview: string[][];
  suggested: Record<string, string | null>;
}

export interface CostConfirmResult {
  imported: number;
  skipped: number;
  duplicates: number;
  errors: string[];
  cost_coverage: number | null;
  missing_skus: string[];
}

export interface ImportConfirmResult {
  dataset: ImportDataset;
  imported: number;
  skipped: number;
  duplicates: number;
  errors: string[];
  cost_coverage: number | null;
}
