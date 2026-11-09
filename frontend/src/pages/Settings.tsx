import { useRef, useState } from "react";
import { Empty, ErrorBox, Loading, Panel, useAsync } from "../components/ui";
import { api, count } from "../lib/api";

const TONE: Record<string, string> = { production: "badge mint", test: "badge amber" };

const KIND_LABEL: Record<string, string> = {
  csv: "本地 CSV",
  http: "通用 HTTP",
  taobao: "淘宝开放平台",
  erp: "ERP 接口",
};

const STATUS_TONE: Record<string, string> = {
  idle: "badge",
  ready: "badge cyan",
  synced: "badge mint",
  error: "badge rose",
};

export default function SettingsPage() {
  const snap = useAsync(() => api.settings(), []);
  const audit = useAsync(() => api.audit(), []);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  async function makeDefault(id: number) {
    setBusy(id);
    setErr(null);
    try {
      await api.setDefaultModel(id);
      snap.reload();
    } catch (e: any) {
      setErr(e?.message ?? "设置失败");
    } finally {
      setBusy(null);
    }
  }

  if (snap.loading && !snap.data) return <Loading rows={4} />;
  if (snap.error) return <ErrorBox message={snap.error} />;
  const s = snap.data!;
  const prod = s.models.filter((m: any) => m.purpose === "production");
  const test = s.models.filter((m: any) => m.purpose === "test");

  return (
    <div className="stack gap-16 fade-in">
      {err && <ErrorBox message={err} />}

      <div className="grid g6">
        {[
          ["SKU", s.stats.skus], ["订单", s.stats.orders], ["知识块", s.stats.chunks],
          ["运行", s.stats.runs], ["账号", s.stats.users], ["接入", s.stats.connectors],
        ].map(([label, v]) => (
          <div className="kpi" key={label as string}>
            <span className="kpi-label">{label as string}</span>
            <span className="kpi-value" style={{ fontSize: 22 }}>{count(v as number)}</span>
          </div>
        ))}
      </div>

      <Connectors />

      <Users max={s.max_users ?? 5} />

      <Panel title="模型路由" sub="正式走 API 级模型（qwen-plus 等）；本机 4B 仅作测试"
             right={<span className="badge violet">当前：{s.llm.model}</span>}>
        <div className="stack gap-16">
          <div>
            <div className="row between mt-4">
              <span className="eyebrow">生产模型</span>
              <span className="muted" style={{ fontSize: 11 }}>
                API Key {s.llm.configured ? "已配置" : "未配置 · 自动降级为确定性引擎"}
              </span>
            </div>
            <div className="stack gap-8 mt-8">
              {prod.map((m: any) => (
                <div className="driver" key={m.id} style={{ gridTemplateColumns: "1fr auto auto" }}>
                  <div className="stack" style={{ lineHeight: 1.3 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>
                      {m.model}
                      {m.is_default && <span className="badge cyan" style={{ marginLeft: 8, fontSize: 9.5 }}>默认</span>}
                    </span>
                    <span className="muted mono" style={{ fontSize: 10.5 }}>{m.provider} · {m.base_url || "默认端点"}</span>
                    <span className="muted" style={{ fontSize: 11 }}>{m.note}</span>
                  </div>
                  <span className={TONE[m.purpose] ?? "badge"} style={{ fontSize: 10 }}>生产</span>
                  <button className="btn sm ghost" disabled={m.is_default || busy === m.id}
                          onClick={() => makeDefault(m.id)}>
                    {m.is_default ? "使用中" : "设为默认"}
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="divider" />

          <div>
            <div className="row between">
              <span className="eyebrow">测试模型</span>
              <span className="badge amber" style={{ fontSize: 10 }}>仅测试 · 不用于生产结论</span>
            </div>
            <div className="stack gap-8 mt-8">
              {test.map((m: any) => (
                <div className="driver" key={m.id} style={{ gridTemplateColumns: "1fr auto" }}>
                  <div className="stack" style={{ lineHeight: 1.3 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{m.model}</span>
                    <span className="muted mono" style={{ fontSize: 10.5 }}>{m.provider} · {m.base_url}</span>
                    <span className="muted" style={{ fontSize: 11 }}>{m.note}</span>
                  </div>
                  <span className="badge amber" style={{ fontSize: 10 }}>测试</span>
                </div>
              ))}
              {test.length === 0 && <span className="muted" style={{ fontSize: 12 }}>未配置测试模型</span>}
            </div>
          </div>

          <div className="divider" />
          <AddModel onDone={() => snap.reload()} />
        </div>
      </Panel>

      <div className="split-2">
        <Panel title="度量口径" sub="唯一权威来源">
          <div className="stack gap-10">
            <div className="row between">
              <span className="muted" style={{ fontSize: 12 }}>口径版本</span>
              <span className="badge cyan mono">{s.metric_version}</span>
            </div>
            <div className="row between">
              <span className="muted" style={{ fontSize: 12 }}>ReAct 最大步数</span>
              <span className="mono" style={{ fontSize: 12 }}>{s.max_react_steps}</span>
            </div>
            <div className="divider" />
            <span className="eyebrow">模型计价（每 1K token，USD）</span>
            <div className="stack gap-6">
              {Object.entries(s.pricing).map(([model, p]: any) => (
                <div className="row between" key={model}>
                  <span className="mono" style={{ fontSize: 11.5 }}>{model}</span>
                  <span className="muted mono" style={{ fontSize: 11 }}>
                    入 ${p.in.toFixed(5)} · 出 ${p.out.toFixed(5)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </Panel>

        <MyAccount />
      </div>

      <Panel title="审计日志" sub="登录 / 运行 / 配置变更">
        {audit.loading && !audit.data ? <Loading rows={2} /> : (
          <div className="table-wrap" style={{ maxHeight: 300 }}>
            <table className="table">
              <thead><tr><th>时间</th><th>操作人</th><th>动作</th></tr></thead>
              <tbody>
                {(audit.data?.items ?? []).slice(0, 20).map((a: any) => (
                  <tr key={a.id}>
                    <td className="mono" style={{ fontSize: 10.5 }}>{String(a.created_at).replace("T", " ").slice(5, 19)}</td>
                    <td style={{ fontSize: 11.5 }}>{a.actor}</td>
                    <td><span className="badge violet" style={{ fontSize: 9.5 }}>{a.action}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

/* ================= 新增模型 ================= */
function AddModel({ onDone }: { onDone: () => void }) {
  const [provider, setProvider] = useState("qwen");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [purpose, setPurpose] = useState("production");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function add() {
    setBusy(true);
    setMsg(null);
    try {
      await api.addModel({ provider, model: model.trim(), base_url: baseUrl.trim(), purpose, note: note.trim() });
      setModel(""); setBaseUrl(""); setNote("");
      setMsg("已添加");
      onDone();
    } catch (e: any) {
      setMsg(e?.message ?? "添加失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack gap-10">
      <div className="row between">
        <span className="eyebrow">新增模型</span>
        {msg && <span className="badge mint" style={{ fontSize: 10 }}>{msg}</span>}
      </div>
      <div className="row gap-8 wrap" style={{ alignItems: "flex-end" }}>
        <div className="field" style={{ width: 110 }}>
          <label>供应商</label>
          <input className="input" value={provider} onChange={(e) => setProvider(e.target.value)} />
        </div>
        <div className="field" style={{ width: 150 }}>
          <label>模型</label>
          <input className="input" value={model} onChange={(e) => setModel(e.target.value)} placeholder="qwen-plus" />
        </div>
        <div className="field" style={{ flex: 1, minWidth: 200 }}>
          <label>接口地址</label>
          <input className="input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
                 placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
        </div>
        <div className="field" style={{ width: 110 }}>
          <label>用途</label>
          <select className="input" value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            <option value="production">生产</option>
            <option value="test">测试</option>
          </select>
        </div>
        <button className="btn primary" onClick={add} disabled={busy || !model.trim()}>
          {busy ? "添加中…" : "添加"}
        </button>
      </div>
      <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="备注（可选）" />
    </div>
  );
}

/* ================= 我的账号 ================= */
function MyAccount() {
  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setMsg(null);
    try {
      await api.changePassword(oldPwd, newPwd);
      setOldPwd(""); setNewPwd("");
      setMsg("密码已更新，下次登录请使用新密码");
    } catch (e: any) {
      setMsg(e?.message ?? "修改失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="我的账号" sub="修改登录密码">
      <div className="stack gap-10">
        {msg && <div className="badge cyan" style={{ whiteSpace: "normal", padding: "9px 12px" }}>{msg}</div>}
        <div className="field">
          <label>原密码</label>
          <input className="input" type="password" value={oldPwd} onChange={(e) => setOldPwd(e.target.value)} />
        </div>
        <div className="field">
          <label>新密码（≥8 位）</label>
          <input className="input" type="password" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} />
        </div>
        <button className="btn primary" onClick={submit}
                disabled={busy || oldPwd.length < 4 || newPwd.length < 8}>
          {busy ? "提交中…" : "更新密码"}
        </button>
      </div>
    </Panel>
  );
}

/* ================= 接入模块 ================= */
function Connectors() {
  const list = useAsync(() => api.connectors(), []);
  const [kind, setKind] = useState("http");
  const [name, setName] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | "new" | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function add() {
    if (!name.trim()) return;
    setBusy("new");
    setMsg(null);
    try {
      await api.addConnector({ kind, name: name.trim(), endpoint: endpoint.trim() });
      setName(""); setEndpoint("");
      list.reload();
    } catch (e: any) {
      setMsg(e?.message ?? "添加失败");
    } finally {
      setBusy(null);
    }
  }

  async function test(id: number) {
    setBusy(id);
    setMsg(null);
    try {
      const r = await api.testConnector(id);
      setMsg(`${r.ok ? "连通正常" : "连通失败"} · ${r.message} · ${r.ms} ms`);
      list.reload();
    } catch (e: any) {
      setMsg(e?.message ?? "测试失败");
    } finally {
      setBusy(null);
    }
  }

  async function sync(id: number, rows?: any[]) {
    setBusy(id);
    setMsg(null);
    try {
      const r = await api.syncConnector(id, rows ?? []);
      setMsg(`同步完成：新增 ${r.inserted} 行，更新 ${r.updated} 行，拒绝 ${r.rejected} 行`);
      list.reload();
    } catch (e: any) {
      setMsg(e?.message ?? "同步失败");
    } finally {
      setBusy(null);
    }
  }

  function pickFile(ev: React.ChangeEvent<HTMLInputElement>, id: number) {
    const file = ev.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? "");
      const lines = text.split(/\r?\n/).filter((l) => l.trim());
      if (lines.length < 2) { setMsg("CSV 至少需要表头 + 1 行数据"); return; }
      const header = lines[0].split(",").map((h) => h.trim());
      const rows = lines.slice(1).map((line) => {
        const cells = line.split(",");
        const obj: Record<string, string> = {};
        header.forEach((h, i) => (obj[h] = (cells[i] ?? "").trim()));
        return obj;
      });
      sync(id, rows);
    };
    reader.readAsText(file, "utf-8");
    ev.target.value = "";
  }

  return (
    <Panel title="接入模块" sub="数据源连接 · 连通性测试 · 增量同步"
           right={<span className="badge cyan">写入 raw.orders</span>}>
      <div className="stack gap-12">
        {msg && <div className="badge mint" style={{ whiteSpace: "normal", padding: "9px 12px" }}>{msg}</div>}

        {list.loading && !list.data ? <Loading rows={2} /> : list.error ? <ErrorBox message={list.error} /> : (
          <div className="stack gap-8">
            {(list.data?.items ?? []).map((c: any) => (
              <div className="driver" key={c.id} style={{ gridTemplateColumns: "1fr auto", rowGap: 8 }}>
                <div className="stack" style={{ lineHeight: 1.35 }}>
                  <div className="row gap-8">
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{c.name}</span>
                    <span className="badge" style={{ fontSize: 9.5 }}>{KIND_LABEL[c.kind] ?? c.kind}</span>
                    <span className={STATUS_TONE[c.status] ?? "badge"} style={{ fontSize: 9.5 }}>{c.status}</span>
                    {!c.enabled && <span className="badge rose" style={{ fontSize: 9.5 }}>已停用</span>}
                  </div>
                  <span className="muted mono" style={{ fontSize: 10.5 }}>{c.endpoint || "本地文件（无需地址）"}</span>
                  <span className="muted" style={{ fontSize: 10.5 }}>
                    累计同步 {count(c.rows_synced)} 行
                    {c.last_sync_at ? ` · 最近 ${String(c.last_sync_at).slice(0, 16).replace("T", " ")}` : ""}
                    {c.last_test_ms ? ` · 连通 ${c.last_test_ms} ms` : ""}
                  </span>
                </div>

                <div className="row gap-6 wrap" style={{ justifyContent: "flex-end" }}>
                  {c.kind === "csv" ? (
                    <>
                      <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }}
                             onChange={(e) => pickFile(e, c.id)} />
                      <button className="btn sm ghost" disabled={busy === c.id}
                              onClick={() => fileRef.current?.click()}>导入 CSV</button>
                    </>
                  ) : (
                    <>
                      <button className="btn sm ghost" disabled={busy === c.id} onClick={() => test(c.id)}>测试</button>
                      <button className="btn sm ghost" disabled={busy === c.id} onClick={() => sync(c.id)}>同步</button>
                    </>
                  )}
                  <button className="btn sm ghost" disabled={busy === c.id}
                          onClick={async () => { await api.toggleConnector(c.id, !c.enabled); list.reload(); }}>
                    {c.enabled ? "停用" : "启用"}
                  </button>
                  <button className="btn sm ghost" disabled={busy === c.id}
                          onClick={async () => { await api.deleteConnector(c.id); list.reload(); }}>删除</button>
                </div>
              </div>
            ))}
            {(list.data?.items ?? []).length === 0 && <Empty text="还没有接入任何数据源" />}
          </div>
        )}

        <div className="divider" />
        <span className="eyebrow">新增接入</span>
        <div className="row gap-8 wrap" style={{ alignItems: "flex-end" }}>
          <div className="field" style={{ width: 150 }}>
            <label>类型</label>
            <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
              {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div className="field" style={{ width: 190 }}>
            <label>名称</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="如：淘宝订单源" />
          </div>
          <div className="field" style={{ flex: 1, minWidth: 220 }}>
            <label>接口地址{kind === "csv" ? "（CSV 可留空）" : ""}</label>
            <input className="input" value={endpoint} onChange={(e) => setEndpoint(e.target.value)}
                   placeholder="https://api.example.com/orders" disabled={kind === "csv"} />
          </div>
          <button className="btn primary" onClick={add} disabled={busy === "new" || !name.trim()}>
            {busy === "new" ? "添加中…" : "添加"}
          </button>
        </div>
        <span className="muted" style={{ fontSize: 11 }}>
          接口需返回订单数组，或 {"{"}"orders": [...]{"}"}；每行字段：order_id、sku_id、buyer_id、ordered_at、qty、paid、channel
        </span>
      </div>
    </Panel>
  );
}

/* ================= 账号 ================= */
function Users({ max }: { max: number }) {
  const list = useAsync(() => api.users(), []);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [pwd, setPwd] = useState("");
  const [role, setRole] = useState("analyst");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const items = list.data?.items ?? [];
  const full = items.length >= max;

  async function create() {
    setBusy(true);
    setMsg(null);
    try {
      await api.createUser({ email: email.trim(), display_name: name.trim(), password: pwd, role });
      setEmail(""); setName(""); setPwd("");
      list.reload();
      setMsg("账号已创建");
    } catch (e: any) {
      setMsg(e?.message ?? "创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function reset(id: number) {
    const np = prompt("输入新密码（至少 8 位）");
    if (!np) return;
    try {
      await api.resetPassword(id, np);
      setMsg("密码已重置");
    } catch (e: any) {
      setMsg(e?.message ?? "重置失败");
    }
  }

  return (
    <Panel title="账号" sub={`最多 ${max} 人 · 管理员可管理`}
           right={<span className={`badge ${full ? "rose" : "mint"}`}>{items.length} / {max}</span>}>
      <div className="stack gap-12">
        {msg && <div className="badge cyan" style={{ whiteSpace: "normal", padding: "9px 12px" }}>{msg}</div>}

        {list.loading && !list.data ? <Loading rows={2} /> : list.error ? <ErrorBox message={list.error} /> : (
          <div className="stack gap-8">
            {items.map((u: any) => (
              <div className="driver" key={u.id} style={{ gridTemplateColumns: "1fr auto" }}>
                <div className="stack" style={{ lineHeight: 1.35 }}>
                  <div className="row gap-8">
                    <span style={{ fontSize: 12.5, fontWeight: 600 }}>{u.display_name}</span>
                    <span className="badge" style={{ fontSize: 9.5 }}>{u.role}</span>
                    {u.status !== "active" && <span className="badge rose" style={{ fontSize: 9.5 }}>已停用</span>}
                  </div>
                  <span className="muted mono" style={{ fontSize: 10.5 }}>{u.email}</span>
                  <span className="muted" style={{ fontSize: 10 }}>
                    {u.last_login_at ? `最近登录 ${String(u.last_login_at).slice(0, 16).replace("T", " ")}` : "尚未登录"}
                  </span>
                </div>
                <div className="row gap-6">
                  <button className="btn sm ghost" onClick={() => reset(u.id)}>重置密码</button>
                  <button className="btn sm ghost"
                          onClick={async () => {
                            try {
                              await api.patchUser(u.id, { status: u.status === "active" ? "disabled" : "active" });
                              list.reload();
                            } catch (e: any) { setMsg(e?.message ?? "操作失败"); }
                          }}>
                    {u.status === "active" ? "停用" : "启用"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {!full && (
          <>
            <div className="divider" />
            <span className="eyebrow">新增账号</span>
            <div className="row gap-8 wrap" style={{ alignItems: "flex-end" }}>
              <div className="field" style={{ width: 200 }}>
                <label>邮箱</label>
                <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" />
              </div>
              <div className="field" style={{ width: 140 }}>
                <label>姓名</label>
                <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="张三" />
              </div>
              <div className="field" style={{ width: 150 }}>
                <label>初始密码（≥8 位）</label>
                <input className="input" type="password" value={pwd} onChange={(e) => setPwd(e.target.value)} />
              </div>
              <div className="field" style={{ width: 120 }}>
                <label>角色</label>
                <select className="input" value={role} onChange={(e) => setRole(e.target.value)}>
                  <option value="analyst">分析员</option>
                  <option value="viewer">只读</option>
                  <option value="owner">管理员</option>
                </select>
              </div>
              <button className="btn primary" onClick={create}
                      disabled={busy || !email.trim() || !name.trim() || pwd.length < 8}>
                {busy ? "创建中…" : "创建"}
              </button>
            </div>
          </>
        )}
        {full && <span className="muted" style={{ fontSize: 11.5 }}>已达到 {max} 人上限，停用后可腾出名额。</span>}
      </div>
    </Panel>
  );
}
