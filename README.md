# Lira · 财务智能体控制台

面向淘天中小商家的**多智能体财务分析控制台**。AI 不是问答框，而是嵌进每个视图的分析组件：实时读取订单、退款、广告与成本口径，直接产出归因、置信度、证据与可执行动作。

---

## 界面结构

```
登录页
 └─ 智能财务分析（工作模块）
      ├─ 经营总览：6 主指标 + 18 口径全量网格 + 趋势 + AI 研判
      ├─ 诊断作业：发起多智能体分析 + 执行轨迹 + 运行历史
      ├─ 利润排行：按毛利 / 毛利率 / 广告 / 退款排序
      └─ 辅助问答（右下角小组件，补充分口径追问）
 └─ 可视化大屏（右上角一键切换，全屏霸屏版）
 └─ Agent 模型：智能体 / MCP 工具 / 知识库 / 评测
 └─ 设置：接入模块 / 账号 / 模型路由 / 度量口径 / 审计
```

---

## 架构

```
frontend/  React 19 + TypeScript + Vite + ECharts（毛玻璃 3D + 霸屏大屏）
backend/   FastAPI + asyncpg + LangGraph + pgvector + MCP
           ├── app/metrics.py        18 个量化口径（全部 SQL 计算）
           ├── app/graph.py          LangGraph：Supervisor + 4 个专职 Agent
           ├── app/tools.py          7 个 MCP 工具（只读 + JSON Schema + 审计）
           ├── app/rag.py            pgvector HNSW + 全文混合检索
           ├── app/eval_harness.py   6 项评测指标
           ├── app/ingest.py         订单接入（幂等 upsert + 逐行校验）
           └── app/mcp_server.py     MCP stdio 服务端
docker-compose.yml  pgvector/pgvector:pg16（宿主机 5433）
```

### 数据分六个 schema

| schema | 作用 |
|---|---|
| `raw` | 订单 / 退款 / 广告 / 成本 / 商品 / 平台费明细 |
| `mart` | 视图层：订单行、SKU 日汇总、SKU 汇总、日指标 —— **指标唯一来源** |
| `agent` | 智能体、工具、运行、步骤、洞察 |
| `kb` | 知识库文档与向量块（HNSW） |
| `eval` | 评测用例与评测运行 |
| `ops` | 账号、接入项、模型配置、设置、审计 |

### 多智能体拓扑

```
START → Supervisor ─┬─→ MetricAnalyst  （取数与同环比）
                    ├─→ AnomalyHunter  （Z-score 异动 + SKU 明细）
                    ├─→ RagLibrarian   （口径检索与引用）
                    └─→ Advisor        （结论合成，不产数字）
                              → END
```

数字全部来自 SQL；Agent 只做解释、归因与建议；每条结论带 `evidence`。

---

## 账号体系

- 最多 **5 个账号**，管理员可创建、停用、重置密码；停用后立即无法登录。
- 角色：`owner`（管理员）/ `analyst`（分析员）/ `viewer`（只读）。
- 密码 bcrypt 散列，JWT 有效期 12 小时，每次请求校验账号状态。
- 演示账号：`admin@lira.local` / `lira2026`（首次启动自动创建）。

## 接入模块

支持 4 类数据源：本地 CSV、通用 HTTP、淘宝开放平台、ERP 接口。

- **测试**：对 HTTP 类真实发起请求并记录延迟；CSV 类无需连通性测试。
- **同步**：HTTP 类拉取 `{"orders":[...]}` 或订单数组；CSV 类在浏览器解析后按行提交。
- 写入 `raw.orders` 为**幂等 upsert**，逐行校验字段、日期、数量与 SKU，拒绝行给出原因。
- 所有接入动作写审计日志。

---

## 快速开始

前置：Docker、Python 3.12、Node 20+。

```bash
docker compose up -d
```

```bash
cd backend && uv venv .venv --python 3.12 && uv pip install --python .venv/Scripts/python.exe -e .
```

```bash
cd frontend && npm install && npm run build
```

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8012
```

打开 <http://localhost:8012>，演示账号 `admin@lira.local` / `lira2026`。

Windows 可用 `.\start.ps1` 一键完成上述步骤。MCP 服务端另起：`python -m app.mcp_server`（stdio）。

---

## 模型路由

| 用途 | 默认 | 说明 |
|---|---|---|
| 生产 | `qwen-plus`（DashScope 兼容模式） | 配置 `LIRA_LLM_API_KEY` 后启用 |
| 备选 | `qwen-max` / `gpt-4o-mini` / `deepseek-chat` | 设置页可切换默认 |
| 测试 | 本机 `qwen3:4b` | **仅测试用途**，能力有限，不用于生产结论 |

未配置 API Key 时自动降级为**确定性分析引擎**：同样调用真实工具、给出真实数字，只是措辞由规则合成，不会编造数据。

---

## 评测

`Agent 模型 → 评测` 可一键跑批，输出六项指标：

任务成功率 · 工具调用准确率 · 引用命中率 · 幻觉率 · P95 延迟 · 单次 token 成本

幻觉判定：结论中出现的每个数字必须能在工具观测值中找到（含「万」「百分比」量级换算）。

---

## 性能

| 措施 | 效果 |
|---|---|
| `mart` 物化视图 + 唯一索引 | 90 天总览 **2131ms → 28ms** |
| 18 个指标并发计算 | 36 次串行查询 → `asyncio.gather` |
| 路由级懒加载 + 手动分包 | 首屏 JS **1371KB → 270KB** |
| ECharts 按需注册 | echarts 分块 **1012KB → 507KB** |
| GZip 中间件 | 总览响应 **3344B → 921B（-72%）** |
| 明细表索引 | orders / refunds / ad_daily 常用查询路径 |

实测接口耗时：总览 7 天 13ms、90 天 27ms，排行 9ms。

---

## 许可

[MIT](LICENSE)
