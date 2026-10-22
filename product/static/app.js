const $ = (id) => document.getElementById(id);
const fmt = (n) => n === null || n === undefined
  ? "—"
  : Number(n).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n) => n === null || n === undefined ? "—" : (Number(n) * 100).toFixed(1) + "%";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[c]));
const cls = (n) => n < 0 ? "neg" : n > 0 ? "pos" : "";

let period = { start: null, end: null };
let lastOverview = null;
let lastLoss = null;
let lastAds = null;
let currentUpload = null;
let importUpload = null;
let pin = sessionStorage.getItem("lira_pin") || "";

function qs(extra = {}) {
  const params = new URLSearchParams();
  if (period.start) params.set("start", period.start);
  if (period.end) params.set("end", period.end);
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== null && value !== undefined) params.set(key, value);
  });
  const text = params.toString();
  return text ? `?${text}` : "";
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (pin) headers["X-Lira-Pin"] = pin;
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  if (response.status === 401) {
    showPinGate();
    throw new Error("需要访问 PIN");
  }
  let body = null;
  if (text) {
    try { body = JSON.parse(text); } catch { body = text; }
  }
  if (!response.ok) {
    const message = body && body.error && body.error.message
      ? body.error.message
      : (typeof body === "string" ? body : response.statusText);
    throw new Error(message);
  }
  return body;
}

const get = (path) => api(path);
const postJson = (path, body) => api(path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const upload = (path, file) => {
  const form = new FormData();
  form.append("file", file);
  return api(path, { method: "POST", body: form });
};

async function fetchBlob(path) {
  const headers = pin ? { "X-Lira-Pin": pin } : {};
  const response = await fetch(path, { headers });
  if (!response.ok) throw new Error(`下载失败（HTTP ${response.status}）`);
  return response.blob();
}

function showError(message) {
  const el = $("error");
  el.hidden = false;
  el.textContent = message;
}

function showPinGate() {
  $("pin-gate").hidden = false;
  $("pin-input").focus();
}

function hidePinGate() {
  $("pin-gate").hidden = true;
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === name);
  });
  ["today", "loss", "ads", "ask", "data"].forEach((key) => {
    const view = $(`view-${key}`);
    if (view) view.hidden = key !== name;
  });
  if (name === "ask") $("ask-input").focus();
}

function stat(label, value, sub, badge = "") {
  return `<div class="card stat">
    <div class="label">${esc(label)}</div>
    <div class="big">${value} ${badge}</div>
    <div class="sub">${esc(sub)}</div>
  </div>`;
}

function changeBadge(comparison) {
  if (!comparison || !comparison.comparable) {
    return `<span class="small muted">无可比</span>`;
  }
  const value = Number(comparison.change);
  const up = value >= 0;
  return `<span class="change ${up ? "up" : "down"}">${up ? "+" : ""}${(value * 100).toFixed(1)}%</span>`;
}

function comparisonFor(data, metric) {
  return (data.comparisons || []).find((item) => item.metric === metric);
}

function renderOverview(o) {
  lastOverview = o;
  period = { start: o.period.start, end: o.period.end };
  $("start-date").value = o.period.start;
  $("end-date").value = o.period.end;
  $("period-note").textContent =
    `${o.period.start} ~ ${o.period.end} · 快照 #${o.snapshot_id}`;
  $("warning").innerHTML = (o.warnings || [])
    .map((w) => `<div class="warn">${esc(w)}</div>`)
    .join("");
  $("stats").innerHTML = [
    stat("贡献毛利（已知成本）", `¥${fmt(o.contribution_margin)}`, `总收入 ¥${fmt(o.net_revenue)}`, changeBadge(comparisonFor(o, "contribution_margin"))),
    stat("净收入", `¥${fmt(o.net_revenue)}`, "实付减退款", changeBadge(comparisonFor(o, "net_revenue"))),
    stat("订单数", String(o.order_count ?? "—"), `销售件数 ${o.units_sold ?? "—"}`, changeBadge(comparisonFor(o, "order_count"))),
    stat("客单价", `¥${fmt(o.aov)}`, "净收入 / 订单数", changeBadge(comparisonFor(o, "aov"))),
    stat("成本覆盖", pct(o.cost_coverage), "低于 80% 时利润为估算"),
    stat("亏损商品", String(o.loss_sku_count), "已知成本且贡献毛利为负"),
    stat("广告浪费", `¥${fmt(o.ad_waste_total)}`, "估算值"),
    stat("数据快照", `#${o.snapshot_id}`, `口径版本 ${o.metric_version}`),
  ].join("");
  renderComparisons(o);
  renderActions(o.actions);
  renderBridge(o.profit_bridge);
  renderCategories(o.categories || []);
  $("data-summary").innerHTML = [
    stat("成本覆盖", pct(o.cost_coverage), "导入成本后立即更新"),
    stat("亏损商品", String(o.loss_sku_count), "已知成本且贡献毛利为负"),
    stat("广告浪费", `¥${fmt(o.ad_waste_total)}`, "估算值"),
    stat("总收入", `¥${fmt(o.net_revenue)}`, "本期"),
  ].join("");
  $("data-warnings").innerHTML = (o.warnings || [])
    .map((w) => `<div class="warn">${esc(w)}</div>`)
    .join("");
  $("bridge-note").textContent = `已知成本部分 · 覆盖 ${pct(o.cost_coverage)}`;
}

function renderComparisons(o) {
  const rows = o.comparisons || [];
  const anomalies = o.anomalies || [];
  const table = rows.length
    ? `<div style="overflow-x:auto"><table>
        <thead><tr><th>指标</th><th class="num">本期</th><th class="num">上一期</th><th class="num">变化</th></tr></thead>
        <tbody>${rows.map((item) => `<tr>
          <td>${esc(item.label)}</td>
          <td class="num">${item.unit === "count" ? item.current : `¥${fmt(item.current)}`}</td>
          <td class="num">${item.unit === "count" ? (item.previous ?? "—") : `¥${fmt(item.previous)}`}</td>
          <td class="num">${item.comparable ? changeBadge(item) : `<span class="small muted">${esc(item.unit === "count" ? "无可比" : "无可比")}</span>`}</td>
        </tr>`).join("")}</tbody></table></div>`
    : `<p class="muted">没有可比较的上一期。</p>`;
  const anomalyHtml = anomalies.length
    ? anomalies.map((item) => `<div class="anomaly ${item.direction === "上升" ? "up" : "down"}">
        <strong>${esc(item.label)} ${esc(item.direction)} ${(Math.abs(Number(item.change)) * 100).toFixed(1)}%</strong>
        <span class="small muted"> ${item.previous} → ${item.current}</span>
      </div>`).join("")
    : `<p class="small muted">没有超过 20% 阈值的波动。</p>`;
  $("comparisons").innerHTML = `${table}<h3 style="margin-top:14px">异常</h3>${anomalyHtml}`;
}

function actionCard(a) {
  const labels = { loss: "亏损", ad: "广告", refund: "退款", data: "数据" };
  return `<div class="card action ${esc(a.kind)}">
    <div>
      <span class="pill ${esc(a.kind)}">${labels[a.kind] || esc(a.kind)}</span>
      <span class="small muted">置信 ${esc(a.confidence)}</span>
    </div>
    <h3>${esc(a.title)}</h3>
    <p class="reason">${esc(a.reason)}</p>
    <p class="impact">影响 ¥${fmt(a.impact)} / 月</p>
    <div class="row">
      <button class="btn primary" data-ack="${esc(a.id)}" data-status="adopted">采纳</button>
      <button class="btn" data-ack="${esc(a.id)}" data-status="ignored">忽略</button>
    </div>
  </div>`;
}

function renderActions(actions) {
  if (!actions || actions.length === 0) {
    $("actions").innerHTML = `<div class="card"><p class="muted">这一期没有发现需要处理的异常。</p></div>`;
    return;
  }
  $("actions").innerHTML = actions.map(actionCard).join("");
  bindAcks();
}

function bindAcks() {
  document.querySelectorAll("[data-ack]").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await postJson(`/api/v1/actions/${encodeURIComponent(btn.dataset.ack)}/ack`, {
          status: btn.dataset.status,
        });
        const card = btn.closest(".action");
        card.querySelectorAll("button").forEach((b) => { b.disabled = true; });
        card.querySelector(".impact").textContent =
          btn.dataset.status === "adopted" ? "已采纳" : "已忽略";
      } catch (error) {
        btn.disabled = false;
        showError("记录失败：" + error.message);
      }
    });
  });
}

function bridgeHtml(rows) {
  const max = Math.max(1, ...rows.map((r) => Math.abs(Number(r.value) || 0)));
  return rows.map((r) => {
    const value = Number(r.value) || 0;
    const width = Math.min(100, Math.abs(value) / max * 100);
    const color = value < 0 ? "var(--bad)" : "var(--brand)";
    return `<div class="bridge-row">
      <span>${esc(r.label)}</span>
      <div class="bar"><span style="width:${width}%;background:${color}"></span></div>
      <span class="num ${cls(value)}">¥${fmt(value)}</span>
    </div>`;
  }).join("");
}

function renderBridge(rows) {
  $("bridge").innerHTML = bridgeHtml(rows);
}

function renderCategories(items) {
  if (!items || items.length === 0) {
    $("categories").innerHTML = `<p class="muted">这一期没有类目数据。</p>`;
    return;
  }
  $("categories").innerHTML = `<div style="overflow-x:auto"><table>
    <thead><tr><th>类目</th><th class="num">净收入</th><th class="num">占比</th><th class="num">贡献毛利</th><th class="num">订单</th></tr></thead>
    <tbody>${items.map((item) => `<tr>
      <td>${esc(item.category)}</td>
      <td class="num">¥${fmt(item.net_revenue)}</td>
      <td class="num">${pct(item.share)}</td>
      <td class="num ${cls(item.contribution_margin)}">¥${fmt(item.contribution_margin)}</td>
      <td class="num">${item.orders}</td>
    </tr>`).join("")}</tbody></table></div>`;
}

function trendSvg(data) {
  const rows = data.rows || [];
  if (rows.length === 0) return `<p class="muted">这一期没有趋势数据。</p>`;
  const width = 820, height = 220, pad = 34;
  const values = [];
  rows.forEach((row) => {
    if (row.net_revenue !== null) values.push(Number(row.net_revenue));
    if (row.contribution_margin !== null) values.push(Number(row.contribution_margin));
  });
  if (values.length === 0) return `<p class="muted">这一期没有趋势数据。</p>`;
  let max = Math.max(...values, 1);
  let min = Math.min(...values, 0);
  if (max === min) { max += 1; min -= 1; }
  const x = (i) => pad + (rows.length === 1 ? (width - 2 * pad) / 2 : i * (width - 2 * pad) / (rows.length - 1));
  const y = (value) => height - pad - ((value - min) / (max - min)) * (height - 2 * pad);
  const line = (key, color) => `<polyline fill="none" stroke="${color}" stroke-width="2" points="${
    rows.map((row, i) => `${x(i)},${y(Number(row[key] || 0))}`).join(" ")
  }"/>`;
  const zero = min < 0 && max > 0 ? `<line x1="${pad}" y1="${y(0)}" x2="${width - pad}" y2="${y(0)}" stroke="#cbd5e1" stroke-dasharray="4 4"/>` : "";
  return `<svg viewBox="0 0 ${width} ${height}" class="trend" role="img" aria-label="趋势">
    ${zero}
    <line x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" stroke="#e8ecf1"/>
    ${line("net_revenue", "#2f6bff")}
    ${line("contribution_margin", "#7c3aed")}
    <text x="${pad}" y="${height - 8}" class="axis">${esc(rows[0].bucket)}</text>
    <text x="${width - pad}" y="${height - 8}" text-anchor="end" class="axis">${esc(rows[rows.length - 1].bucket)}</text>
  </svg>
  <div class="legend"><span class="dot blue"></span>净收入 <span class="dot violet"></span>贡献毛利</div>`;
}

function renderLoss(data) {
  lastLoss = data;
  const items = data.items || [];
  if (items.length === 0) {
    $("loss").innerHTML = `<p class="muted">这一期没有已知成本的亏损 SKU。</p>`;
    return;
  }
  $("loss").innerHTML = `<p class="small muted">点击一行查看利润桥、证据和建议。</p>
    <div style="overflow-x:auto"><table>
    <thead><tr>
      <th>商品</th><th>类目</th><th class="num">实付</th><th class="num">退款率</th>
      <th class="num">成本覆盖</th><th class="num">贡献毛利</th><th class="num">每单亏</th><th class="num">广告</th>
    </tr></thead>
    <tbody>${items.map((i) => `<tr class="clickable" data-sku="${esc(i.sku)}">
      <td><strong>${esc(i.sku)}</strong><div class="small muted">${esc(i.title || "")}${
        i.merchant_sku && i.merchant_sku !== i.sku ? ` · 款号 ${esc(i.merchant_sku)}` : ""
      }</div></td>
      <td>${esc(i.category || "—")}</td>
      <td class="num">¥${fmt(i.net_revenue)}</td>
      <td class="num">${pct(i.refund_rate)}</td>
      <td class="num">${pct(i.cost_coverage)}</td>
      <td class="num neg">¥${fmt(i.contribution_margin)}</td>
      <td class="num neg">¥${fmt(i.loss_per_order)}</td>
      <td class="num">¥${fmt(i.ad_spend)}</td>
    </tr>`).join("")}</tbody></table></div>`;
  document.querySelectorAll("#loss tr[data-sku]").forEach((row) => {
    row.addEventListener("click", () => openSku(row.dataset.sku));
  });
}

function renderAds(data) {
  lastAds = data;
  const items = data.items || [];
  if (items.length === 0) {
    $("ads").innerHTML = `<p class="muted">这一期没有发现广告浪费。</p>`;
    return;
  }
  $("ads").innerHTML = `<div style="overflow-x:auto"><table>
    <thead><tr>
      <th>计划</th><th>SKU</th><th class="num">花费</th><th class="num">成交</th>
      <th class="num">ROI</th><th class="num">盈亏平衡 ROI</th><th class="num">估算浪费</th><th>建议</th>
    </tr></thead>
    <tbody>${items.map((i) => `<tr>
      <td>${esc(i.campaign)}</td>
      <td>${esc(i.sku)}</td>
      <td class="num">¥${fmt(i.spend)}</td>
      <td class="num">¥${fmt(i.attributed_revenue)}</td>
      <td class="num">${i.roi === null ? "—" : Number(i.roi).toFixed(2)}</td>
      <td class="num">${i.breakeven_roi === null ? "—" : Number(i.breakeven_roi).toFixed(2)}</td>
      <td class="num neg">¥${fmt(i.waste)}</td>
      <td>${esc(i.suggestion)}</td>
    </tr>`).join("")}</tbody>
  </table></div>
  <p class="small muted" style="margin:10px 0 0">合计估算浪费 ¥${fmt(data.total_waste)}。</p>`;
}

function renderHealth(data) {
  const sources = (data.sources || []).map((s) => `<div class="health-item">
    <div class="name">${esc(s.name)}</div>
    <div class="meta">最新 ${esc(s.latest || "—")}</div>
    <div class="meta">${Number(s.rows).toLocaleString("zh-CN")} 行 · ${esc(s.status)}</div>
  </div>`).join("");
  const missing = (data.missing_skus || []).length
    ? `<div class="missing">缺少成本：${data.missing_skus.map(esc).join("、")}</div>`
    : "";
  const warnings = (data.warnings || [])
    .map((w) => `<div class="warn" style="margin-top:12px">${esc(w)}</div>`)
    .join("");
  $("health").innerHTML = `<div class="health-grid">${sources}</div>${missing}${warnings}
    <p class="small muted" style="margin:10px 0 0">成本覆盖 ${pct(data.coverage)} · 快照 #${data.snapshot_id} · 最近同步 ${esc(data.last_sync || "—")}</p>`;
}

function renderImportStatus(data) {
  const pending = data.pending || [];
  $("sync-status").innerHTML = `
    <div class="health-grid">
      ${statusItem("导出文件夹", "监听中", data.inbox)}
      ${statusItem("扫描模式", data.watcher === "event+poll" ? "文件事件 + 定时兜底" : "定时轮询", `${data.interval_s}s`)}
      ${statusItem("待处理", String(pending.length), pending.join("、") || "没有新文件")}
      ${statusItem("本地模型", data.model?.available ? "可用" : "未启用", data.model?.model || "")}
    </div>
    <p class="small muted">最近导入：${data.last
      ? `${esc(data.last.dataset)} · ${esc(data.last.filename)} · ${data.last.imported} 行 · ${esc(data.last.status)}`
      : "还没有"}</p>`;
}

function renderConnectors(data) {
  const quota = data.quota || { per_minute: 0, remaining: {} };
  $("connector-status").innerHTML = `
    <div class="health-grid">
      ${statusItem("导出文件夹", data.folder?.configured ? "已启用" : "未启用", data.folder?.inbox || "")}
      ${statusItem("淘宝开放平台", data.taobao?.configured ? "已配置" : "未配置", data.taobao?.message || "")}
      ${statusItem("ERP", data.erp?.configured ? "已配置" : "未配置", data.erp?.message || "")}
      ${statusItem("配额", `${quota.per_minute || "—"}/分钟`, `淘宝剩余 ${quota.remaining?.taobao ?? "—"}`)}
    </div>
    <p class="small muted" style="margin:10px 0 0">${esc(data.pii?.policy || "")}</p>`;
}

function statusItem(name, value, sub) {
  return `<div class="health-item">
    <div class="name">${esc(name)}</div>
    <div class="meta">${esc(value)}</div>
    <div class="meta">${esc(sub || "")}</div>
  </div>`;
}

function renderAliases(data) {
  const aliases = data.aliases || [];
  const unresolved = data.unresolved || [];
  $("alias-unresolved").innerHTML = unresolved.length
    ? unresolved.map((sku) => `<div class="alias-row">
        <code>${esc(sku)}</code>
        <input data-alias-sku="${esc(sku)}" placeholder="商家款号，例如 A001">
        <button class="btn" data-alias-save="${esc(sku)}">保存</button>
      </div>`).join("")
    : `<p class="small muted">所有订单 SKU 都已匹配到成本。</p>`;
  $("alias-list").innerHTML = aliases.length
    ? aliases.map((a) => `<div class="alias-row">
        <code>${esc(a.platform_sku)}</code><span>→</span><code>${esc(a.merchant_sku)}</code>
        <button class="btn" data-alias-delete="${esc(a.platform_sku)}">删除</button>
      </div>`).join("")
    : `<p class="small muted">还没有别名。</p>`;
  bindAliases();
}

function bindAliases() {
  document.querySelectorAll("[data-alias-save]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const platform = btn.dataset.aliasSave;
      const input = btn.parentElement.querySelector("input");
      const merchant = input.value.trim();
      if (!merchant) { showError("先填商家款号。"); return; }
      try {
        await postJson("/api/v1/sku-aliases", { platform_sku: platform, merchant_sku: merchant });
        await load();
      } catch (error) { showError("保存失败：" + error.message); }
    });
  });
  document.querySelectorAll("[data-alias-delete]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api(`/api/v1/sku-aliases/${encodeURIComponent(btn.dataset.aliasDelete)}`, { method: "DELETE" });
        await load();
      } catch (error) { showError("删除失败：" + error.message); }
    });
  });
}

function renderCatalogue(data) {
  const metrics = (data.metrics || []).map((m) => `<tr>
    <td><strong>${esc(m.label)}</strong><div class="small muted">${esc(m.name)}</div></td>
    <td>${esc(m.description)}</td>
    <td>${esc(m.unit)}</td>
  </tr>`).join("");
  const dimensions = (data.dimensions || []).map((d) =>
    `<span class="chip">${esc(d.label)} <code>${esc(d.name)}</code></span>`
  ).join("");
  $("catalogue").innerHTML = `<p class="small muted">口径版本 ${esc(data.version)}</p>
    <div style="overflow-x:auto"><table><thead><tr><th>指标</th><th>定义</th><th>单位</th></tr></thead>
    <tbody>${metrics}</tbody></table></div>
    <h3 style="margin-top:14px">维度</h3><div class="chips">${dimensions}</div>`;
}

function renderHistory(data) {
  const runs = (data.runs || []).map((run) => `<tr>
    <td class="num">${run.id}</td>
    <td>${esc(run.kind)}</td>
    <td>${esc(run.question || "经营总览")}</td>
    <td class="num">#${run.snapshot_id}</td>
    <td class="small muted">${esc(run.created_at || "")}</td>
    <td><button class="btn" data-evidence="${run.id}">证据</button></td>
  </tr>`).join("");
  const actions = (data.actions || []).map((action) => `<tr>
    <td>${esc(action.action_id)}</td>
    <td>${esc(action.status)}</td>
    <td class="small muted">${esc(action.updated_at || "")}</td>
  </tr>`).join("");
  $("history").innerHTML = `
    <h3>分析记录</h3>
    <div style="overflow-x:auto"><table><thead><tr><th>#</th><th>类型</th><th>问题</th><th>快照</th><th>时间</th><th></th></tr></thead>
    <tbody>${runs || `<tr><td colspan="6" class="muted">还没有记录</td></tr>`}</tbody></table></div>
    <h3 style="margin-top:14px">采纳/忽略</h3>
    <div style="overflow-x:auto"><table><thead><tr><th>动作</th><th>状态</th><th>时间</th></tr></thead>
    <tbody>${actions || `<tr><td colspan="3" class="muted">还没有动作</td></tr>`}</tbody></table></div>
    <div id="history-evidence" style="margin-top:12px"></div>`;
  document.querySelectorAll("[data-evidence]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const data = await get(`/api/v1/evidence/${btn.dataset.evidence}`);
        $("history-evidence").innerHTML =
          `<h3>证据</h3><pre class="small">${esc(JSON.stringify(data, null, 2))}</pre>`;
      } catch (error) { showError("读取证据失败：" + error.message); }
    });
  });
}

function renderOps(data) {
  const backups = (data.backups || []).map((b) =>
    `${esc(b.file)}（${Math.round(b.bytes / 1024)} KB）`
  ).join("<br>") || "还没有备份";
  $("ops-status").innerHTML = `
    <div class="health-grid">
      ${statusItem("版本", data.version, `口径 ${lastOverview?.metric_version || "—"}`)}
      ${statusItem("快照", `#${data.snapshot_id}`, "当前数据版本")}
      ${statusItem("数据库", `${Math.round((data.db_bytes || 0) / 1024)} KB`, `分析记录 ${data.analysis_runs} 条`)}
      ${statusItem("备份", data.backup_key === "env" ? "环境密钥" : "本机密钥", "加密 zip.enc")}
    </div>
    <p class="small muted" style="margin:10px 0 0">最近同步：${esc(data.last_sync || "—")}</p>
    <p class="small muted">最近备份：<br>${backups}</p>`;
  bindOps();
}

function bindOps() {
  const backup = $("backup-btn");
  if (backup && backup.dataset.bound !== "1") {
    backup.dataset.bound = "1";
    backup.addEventListener("click", async () => {
      try {
        const data = await postJson("/api/v1/ops/backup", {});
        $("ops-msg").textContent = `已备份：${data.file}（${Math.round(data.bytes / 1024)} KB）`;
        await load();
      } catch (error) { showError("备份失败：" + error.message); }
    });
  }
  const diagnostics = $("diagnostics-btn");
  if (diagnostics && diagnostics.dataset.bound !== "1") {
    diagnostics.dataset.bound = "1";
    diagnostics.addEventListener("click", async () => {
      try {
        const blob = await fetchBlob("/api/v1/ops/diagnostics");
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = "lira-diagnostics.zip";
        link.click();
        URL.revokeObjectURL(link.href);
      } catch (error) { showError("诊断包失败：" + error.message); }
    });
  }
}

function renderCostPreview(data) {
  $("cost-preview-area").hidden = false;
  $("cost-meta").textContent = `${data.filename} · ${data.row_count} 行 · ${data.headers.length} 列`;
  const targets = [
    ["sku", "商品编码", true],
    ["effective_from", "生效日期", true],
    ["unit_cost", "采购单价", true],
    ["shipping_cost", "运费", false],
    ["packaging_cost", "包材", false],
  ];
  $("cost-mapping").innerHTML = targets.map(([key, label, required]) => {
    const selected = data.suggested[key] || "";
    const options = [`<option value="">（不使用）</option>`]
      .concat(data.headers.map((header) =>
        `<option value="${esc(header)}"${header === selected ? " selected" : ""}>${esc(header)}</option>`
      )).join("");
    return `<div class="map-item"><label>${label}${required ? ' <span class="neg">*</span>' : ""}</label>
      <select data-map="${key}">${options}</select></div>`;
  }).join("");
  $("cost-table").innerHTML = previewTable(data);
}

function previewTable(data) {
  const head = data.headers.map((h) => `<th>${esc(h)}</th>`).join("");
  const body = data.preview.map((row) =>
    `<tr>${row.map((cell) => `<td>${esc(cell)}</td>`).join("")}</tr>`
  ).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>
    <p class="small muted" style="margin:8px 0 0">仅预览前 ${data.preview.length} 行。</p>`;
}

function renderImportPreview(data) {
  importUpload = data.upload_id;
  $("import-preview-area").hidden = false;
  $("import-meta").textContent = `${data.filename} · ${data.row_count} 行 · ${data.dataset}`;
  $("import-mapping").innerHTML = (data.targets || []).map((target) => {
    const selected = data.suggested[target.key] || "";
    const options = [`<option value="">（不使用）</option>`]
      .concat(data.headers.map((header) =>
        `<option value="${esc(header)}"${header === selected ? " selected" : ""}>${esc(header)}</option>`
      )).join("");
    return `<div class="map-item"><label>${esc(target.label)}${target.required ? ' <span class="neg">*</span>' : ""}</label>
      <select data-import-map="${esc(target.key)}">${options}</select></div>`;
  }).join("");
  $("import-table").innerHTML = previewTable(data);
}

async function openSku(sku) {
  try {
    const data = await get(`/api/v1/skus/${encodeURIComponent(sku)}${qs()}`);
    $("drawer-content").innerHTML = `
      <h2>${esc(data.sku)} ${esc(data.title || "")}</h2>
      <p class="small muted">${esc(data.category || "—")} · ${esc(data.supplier || "—")} · 快照 #${data.snapshot_id} · 口径 ${esc(data.metric_version)}</p>
      <div class="grid stats" style="margin-top:12px">
        ${stat("贡献毛利", `¥${fmt(data.contribution_margin)}`, "本期")}
        ${stat("每单亏", `¥${fmt(data.loss_per_order)}`, "贡献毛利 / 订单")}
        ${stat("退款率", pct(data.refund_rate), "退款订单 / 订单")}
        ${stat("广告", `¥${fmt(data.ad_spend)}`, "本期")}
      </div>
      <h3 style="margin-top:16px">利润桥</h3>
      <div class="card">${bridgeHtml(data.profit_bridge)}</div>
      <h3 style="margin-top:16px">证据</h3>
      <p class="small muted">订单行 ${data.evidence.orders} · 退款 ${data.evidence.refunds} · 广告 ${data.evidence.ads} · 成本 ${data.evidence.costs}</p>
      <h3 style="margin-top:16px">建议</h3>
      <div class="grid actions">${(data.actions || []).map(actionCard).join("") || '<p class="muted">没有建议。</p>'}</div>`;
    $("drawer").hidden = false;
    bindAcks();
  } catch (error) {
    showError("读取 SKU 失败：" + error.message);
  }
}

function exportCsv(name, headers, rows) {
  const escape = (value) => `"${String(value ?? "").replace(/"/g, '""')}"`;
  const text = "﻿" + [headers, ...rows].map((row) => row.map(escape).join(",")).join("\n");
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function load() {
  $("error").hidden = true;
  try {
    const [overview, loss, ads, health, status, aliases, connectorsData, trend, history, catalogue, opsData] = await Promise.all([
      get(`/api/v1/overview${qs()}`),
      get(`/api/v1/loss-skus${qs()}`),
      get(`/api/v1/ad-waste${qs()}`),
      get("/api/v1/data-health"),
      get("/api/v1/import/status"),
      get("/api/v1/sku-aliases"),
      get("/api/v1/connectors"),
      get(`/api/v1/trend${qs({ granularity: "day" })}`),
      get("/api/v1/history?limit=20"),
      get("/api/v1/semantic/catalogue"),
      get("/api/v1/ops/status"),
    ]);
    hidePinGate();
    renderOverview(overview);
    renderLoss(loss);
    renderAds(ads);
    renderHealth(health);
    renderImportStatus(status);
    renderAliases(aliases);
    renderConnectors(connectorsData);
    $("trend").innerHTML = trendSvg(trend);
    renderHistory(history);
    renderCatalogue(catalogue);
    renderOps(opsData);
  } catch (error) {
    if (error.message !== "需要访问 PIN") showError("读取失败：" + error.message);
  }
}

function setRangeInputs(start, end) {
  $("start-date").value = start;
  $("end-date").value = end;
}

function isoDate(date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function applyPreset(kind) {
  const today = new Date();
  let start = new Date(today);
  let end = new Date(today);
  if (kind === "month") {
    start = new Date(today.getFullYear(), today.getMonth(), 1);
    end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
  } else {
    const days = Number(kind);
    start.setDate(today.getDate() - (days - 1));
  }
  period = { start: isoDate(start), end: isoDate(end) };
  setRangeInputs(period.start, period.end);
  load();
}

document.querySelectorAll("[data-tab]").forEach((button) => {
  button.addEventListener("click", () => switchTab(button.dataset.tab));
});

$("apply-range").addEventListener("click", () => {
  const start = $("start-date").value;
  const end = $("end-date").value;
  if (!start || !end) { showError("请选择起止日期。"); return; }
  period = { start, end };
  load();
});

document.querySelectorAll("[data-days]").forEach((button) => {
  button.addEventListener("click", () => applyPreset(button.dataset.days));
});

document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    $("ask-input").value = button.dataset.question;
    askQuestion();
  });
});

async function askQuestion() {
  const question = $("ask-input").value.trim();
  if (!question) return;
  $("ask-result").hidden = false;
  $("ask-result").innerHTML = `<div class="card"><p class="muted">正在分析…</p></div>`;
  try {
    const data = await postJson("/api/v1/ask", {
      question,
      start: period.start,
      end: period.end,
    });
    renderAnswer(data);
  } catch (error) {
    showError("问答失败：" + error.message);
  }
}

function renderAnswer(data) {
  $("ask-result").hidden = false;
  $("ask-result").innerHTML = `<div class="card">
    <div class="row" style="align-items:center;gap:8px">
      <span class="pill">${esc(data.intent)}</span>
      <span class="small muted">${data.generated
        ? "本地模型生成建议"
        : data.reason === "model_unavailable"
          ? "模板（本地模型未启用）"
          : "模板（模型建议未通过校验）"}</span>
    </div>
    <p style="margin:10px 0 0;white-space:pre-wrap">${esc(data.answer)}</p>
    <details style="margin-top:12px">
      <summary class="small muted">查看证据</summary>
      <pre class="small" style="overflow:auto;max-height:320px">${esc(JSON.stringify(data.evidence, null, 2))}</pre>
    </details>
  </div>`;
}

$("ask-btn").addEventListener("click", askQuestion);
$("ask-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    askQuestion();
  }
});

$("sync").addEventListener("click", async () => {
  const button = $("sync");
  button.disabled = true;
  button.textContent = "同步中…";
  try {
    await postJson("/api/v1/sync", {});
    await load();
  } catch (error) {
    showError("同步失败：" + error.message);
  } finally {
    button.disabled = false;
    button.textContent = "重新同步";
  }
});

$("scan-now").addEventListener("click", async () => {
  try {
    await postJson("/api/v1/import/scan", {});
    await load();
  } catch (error) { showError("扫描失败：" + error.message); }
});

$("reset-sample").addEventListener("click", async () => {
  try {
    await api("/api/demo/reset", { method: "POST" });
    await load();
  } catch (error) { showError("恢复样例失败：" + error.message); }
});

$("cost-preview").addEventListener("click", async () => {
  const file = $("cost-file").files[0];
  if (!file) { showError("先选择一个成本文件。"); return; }
  try {
    const data = await upload("/api/v1/costs/preview", file);
    currentUpload = data.upload_id;
    renderCostPreview(data);
    $("cost-result").hidden = true;
  } catch (error) { showError("读取失败：" + error.message); }
});

$("cost-confirm").addEventListener("click", async () => {
  if (!currentUpload) { showError("先读取文件。"); return; }
  const mapping = {};
  document.querySelectorAll("[data-map]").forEach((select) => {
    mapping[select.dataset.map] = select.value || null;
  });
  try {
    const data = await postJson("/api/v1/costs/confirm", {
      upload_id: currentUpload,
      mapping,
    });
    $("cost-result").hidden = false;
    $("cost-result").innerHTML = `<div class="ok">已导入 ${data.imported} 行；跳过 ${data.skipped} 行；重复 ${data.duplicates} 行。当前成本覆盖 ${pct(data.cost_coverage)}${data.missing_skus.length ? `；仍缺：${data.missing_skus.map(esc).join("、")}` : "；已全部覆盖"}。</div>${data.errors.length ? `<div class="warn" style="margin-top:10px">${data.errors.map(esc).join("<br>")}</div>` : ""}`;
    $("cost-preview-area").hidden = true;
    currentUpload = null;
    await load();
  } catch (error) { showError("导入失败：" + error.message); }
});

$("import-preview").addEventListener("click", async () => {
  const file = $("import-file").files[0];
  const dataset = $("import-dataset").value;
  if (!file) { showError("先选择文件。"); return; }
  try {
    const data = await upload(`/api/v1/import/preview?dataset=${encodeURIComponent(dataset)}`, file);
    renderImportPreview(data);
    $("import-result").hidden = true;
  } catch (error) { showError("读取失败：" + error.message); }
});

$("import-confirm").addEventListener("click", async () => {
  if (!importUpload) { showError("先读取文件。"); return; }
  const mapping = {};
  document.querySelectorAll("[data-import-map]").forEach((select) => {
    mapping[select.dataset.importMap] = select.value || null;
  });
  try {
    const data = await postJson("/api/v1/import/confirm", {
      dataset: $("import-dataset").value,
      upload_id: importUpload,
      mapping,
      replace: $("import-replace").checked,
    });
    $("import-result").hidden = false;
    $("import-result").innerHTML = `<div class="ok">${esc(data.dataset)}：已导入 ${data.imported} 行；跳过 ${data.skipped} 行；重复 ${data.duplicates} 行。当前成本覆盖 ${pct(data.cost_coverage)}。</div>${data.errors.length ? `<div class="warn" style="margin-top:10px">${data.errors.map(esc).join("<br>")}</div>` : ""}`;
    $("import-preview-area").hidden = true;
    importUpload = null;
    await load();
  } catch (error) { showError("导入失败：" + error.message); }
});

$("tb-save").addEventListener("click", async () => {
  try {
    await postJson("/api/v1/connectors/taobao/configure", {
      app_key: $("tb-key").value,
      app_secret: $("tb-secret").value,
      session: $("tb-session").value,
    });
    $("tb-key").value = "";
    $("tb-secret").value = "";
    $("tb-session").value = "";
    $("tb-msg").textContent = "凭证已加密保存。";
    await load();
  } catch (error) { showError("保存失败：" + error.message); }
});

$("tb-test").addEventListener("click", async () => {
  try {
    const data = await postJson("/api/v1/connectors/taobao/test", {});
    $("tb-msg").textContent = data.message;
  } catch (error) { showError("测试失败：" + error.message); }
});

$("tb-clear").addEventListener("click", async () => {
  try {
    await api("/api/v1/connectors/taobao", { method: "DELETE" });
    $("tb-msg").textContent = "凭证已清除。";
    await load();
  } catch (error) { showError("清除失败：" + error.message); }
});

$("erp-save").addEventListener("click", async () => {
  try {
    await postJson("/api/v1/connectors/erp/configure", {
      base_url: $("erp-url").value,
      token: $("erp-token").value,
    });
    $("erp-url").value = "";
    $("erp-token").value = "";
    $("erp-msg").textContent = "凭证已加密保存。";
    await load();
  } catch (error) { showError("保存失败：" + error.message); }
});

$("erp-test").addEventListener("click", async () => {
  try {
    const data = await postJson("/api/v1/connectors/erp/test", {});
    $("erp-msg").textContent = data.message;
  } catch (error) { showError("测试失败：" + error.message); }
});

$("erp-clear").addEventListener("click", async () => {
  try {
    await api("/api/v1/connectors/erp", { method: "DELETE" });
    $("erp-msg").textContent = "凭证已清除。";
    await load();
  } catch (error) { showError("清除失败：" + error.message); }
});

$("drawer-close").addEventListener("click", () => { $("drawer").hidden = true; });
$("drawer").addEventListener("click", (event) => {
  if (event.target.id === "drawer") $("drawer").hidden = true;
});

$("export-loss").addEventListener("click", () => {
  if (!lastLoss) return;
  exportCsv(
    "loss-skus.csv",
    ["SKU", "标题", "类目", "净收入", "退款率", "成本覆盖", "贡献毛利", "每单亏", "广告"],
    lastLoss.items.map((i) => [i.sku, i.title, i.category, i.net_revenue, i.refund_rate, i.cost_coverage, i.contribution_margin, i.loss_per_order, i.ad_spend])
  );
});

$("export-ads").addEventListener("click", () => {
  if (!lastAds) return;
  exportCsv(
    "ad-waste.csv",
    ["计划", "SKU", "花费", "成交", "ROI", "盈亏平衡ROI", "估算浪费", "建议"],
    lastAds.items.map((i) => [i.campaign, i.sku, i.spend, i.attributed_revenue, i.roi, i.breakeven_roi, i.waste, i.suggestion])
  );
});

$("pin-submit").addEventListener("click", () => {
  pin = $("pin-input").value.trim();
  if (!pin) return;
  sessionStorage.setItem("lira_pin", pin);
  hidePinGate();
  load();
});

load();

setInterval(() => {
  get("/api/v1/import/status").then(renderImportStatus).catch(() => {});
}, 30000);
