import type {
  AdResponse,
  AliasData,
  AskResult,
  Catalogue,
  ConnectorData,
  CostConfirmResult,
  CostPreview,
  DataHealth,
  DatasetRegistry,
  HistoryData,
  ImportConfirmResult,
  ImportDataset,
  ImportPreview,
  ImportStatus,
  LossResponse,
  OpsStatus,
  Overview,
  SkuDetail,
  TimeRange,
  TrendResponse,
} from "./types";

let pin = sessionStorage.getItem("lira_pin") ?? "";
let pinHandler: (() => void) | null = null;

export class PinRequiredError extends Error {
  constructor() {
    super("需要访问 PIN");
    this.name = "PinRequiredError";
  }
}

export function setPin(value: string) {
  pin = value;
  sessionStorage.setItem("lira_pin", value);
}

export function hasPin() {
  return pin.length > 0;
}

export function setPinHandler(handler: () => void) {
  pinHandler = handler;
}

export function query(period: TimeRange | null, extra: Record<string, string | number | undefined> = {}) {
  const params = new URLSearchParams();
  if (period) {
    params.set("start", period.start);
    params.set("end", period.end);
  }
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const text = params.toString();
  return text ? `?${text}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (pin) headers.set("X-Lira-Pin", pin);
  const response = await fetch(path, { ...init, headers });
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (response.status === 401) {
    pinHandler?.();
    throw new PinRequiredError();
  }
  if (!response.ok) {
    const message =
      body && typeof body === "object" && "error" in body
        ? String((body as { error?: { message?: string } }).error?.message ?? response.statusText)
        : typeof body === "string"
          ? body
          : response.statusText;
    throw new Error(message);
  }
  return body as T;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const getOverview = (period: TimeRange | null) =>
  get<Overview>(`/api/v1/overview${query(period)}`);
export const getLoss = (period: TimeRange | null) =>
  get<LossResponse>(`/api/v1/loss-skus${query(period)}`);
export const getAds = (period: TimeRange | null) =>
  get<AdResponse>(`/api/v1/ad-waste${query(period)}`);
export const getTrend = (period: TimeRange | null) =>
  get<TrendResponse>(`/api/v1/trend${query(period, { granularity: "day" })}`);
export const getSku = (sku: string, period: TimeRange | null) =>
  get<SkuDetail>(`/api/v1/skus/${encodeURIComponent(sku)}${query(period)}`);
export const getHealth = () => get<DataHealth>("/api/v1/data-health");
export const getImportStatus = () => get<ImportStatus>("/api/v1/import/status");
export const getAliases = () => get<AliasData>("/api/v1/sku-aliases");
export const getConnectors = () => get<ConnectorData>("/api/v1/connectors");
export const getHistory = () => get<HistoryData>("/api/v1/history?limit=30");
export const getCatalogue = () => get<Catalogue>("/api/v1/semantic/catalogue");
export const getOps = () => get<OpsStatus>("/api/v1/ops/status");
export const getDatasets = () => get<DatasetRegistry>("/api/v1/datasets");
export const getEvidence = (id: number) => get<Record<string, unknown>>(`/api/v1/evidence/${id}`);

export const sync = () => post<Record<string, unknown>>("/api/v1/sync", {});
export const scanInbox = () => post<Record<string, unknown>>("/api/v1/import/scan", {});
export const resetSample = () => request<Record<string, unknown>>("/api/demo/reset", { method: "POST" });
export const ackAction = (id: string, status: string) =>
  post<{ status: string }>(`/api/v1/actions/${encodeURIComponent(id)}/ack`, { status });
export const ask = (question: string, period: TimeRange | null) =>
  post<AskResult>("/api/v1/ask", {
    question,
    start: period?.start ?? null,
    end: period?.end ?? null,
  });

export const upsertAlias = (platformSku: string, merchantSku: string) =>
  post<{ status: string }>("/api/v1/sku-aliases", {
    platform_sku: platformSku,
    merchant_sku: merchantSku,
  });
export const deleteAlias = (platformSku: string) =>
  request<{ status: string }>(`/api/v1/sku-aliases/${encodeURIComponent(platformSku)}`, {
    method: "DELETE",
  });

export const configureConnector = (name: "taobao" | "erp", payload: Record<string, string>) =>
  post<ConnectorData>(`/api/v1/connectors/${name}/configure`, payload);
export const testConnector = (name: "taobao" | "erp") =>
  post<{ ok: boolean; message: string }>(`/api/v1/connectors/${name}/test`, {});
export const clearConnector = (name: "taobao" | "erp") =>
  request<ConnectorData>(`/api/v1/connectors/${name}`, { method: "DELETE" });

export async function uploadCost(file: File): Promise<CostPreview> {
  const form = new FormData();
  form.append("file", file);
  return request<CostPreview>("/api/v1/costs/preview", { method: "POST", body: form });
}
export const confirmCost = (uploadId: string, mapping: Record<string, string | null>) =>
  post<CostConfirmResult>("/api/v1/costs/confirm", { upload_id: uploadId, mapping });

export async function uploadImport(dataset: ImportDataset, file: File): Promise<ImportPreview> {
  const form = new FormData();
  form.append("file", file);
  return request<ImportPreview>(
    `/api/v1/import/preview${query(null, { dataset })}`,
    { method: "POST", body: form },
  );
}
export const confirmImport = (
  dataset: ImportDataset,
  uploadId: string,
  mapping: Record<string, string | null>,
  replace: boolean,
) =>
  post<ImportConfirmResult>("/api/v1/import/confirm", {
    dataset,
    upload_id: uploadId,
    mapping,
    replace,
  });

export const backup = () => post<{ file: string; bytes: number }>("/api/v1/ops/backup", {});

export async function fetchDiagnostics(): Promise<Blob> {
  const headers = new Headers();
  if (pin) headers.set("X-Lira-Pin", pin);
  const response = await fetch("/api/v1/ops/diagnostics", { headers });
  if (response.status === 401) {
    pinHandler?.();
    throw new PinRequiredError();
  }
  if (!response.ok) throw new Error(`诊断包下载失败（HTTP ${response.status}）`);
  return response.blob();
}
