# Lira 2.0 架构说明（唯一权威）

> 本文件描述当前在 `backend/` 与 `frontend/` 中交付的产品。
> 旧版 v1（DuckDB 单机版）已整体移除，冲突时以本文和当前代码为准。

版本：2.0.0 ｜ 状态：当前产品 ｜ 端口：8012

---

## 1. 定位

面向淘天中小商家的**多智能体财务分析控制台**：把平台订单/退款/广告与商家自己的成本口径连起来，
算出真实贡献毛利，并由多个专职 Agent 在**每个视图里**实时给出归因、置信度、证据与可执行动作。

AI 不是问答入口，而是嵌在界面里的分析组件；问答只作为右下角的辅助追问。

技术选型对齐《杭州 AI 技术岗 JD 分析报告》结论①：
`Python + FastAPI + LangGraph + RAG(pgvector) + MCP + 多智能体 + 评测集`。

---

## 2. 系统形态

**模块化单体 + 单库。**

- 一个 Python 进程：FastAPI、Agent 编排、RAG、评测、静态托管；
- 一个 React SPA，构建产物由同一进程托管；
- PostgreSQL 单库承载业务数据、向量、智能体运行、评测与运维数据；
- MCP 服务端为独立 stdio 进程，可被外部 Agent 客户端接入。

---

## 3. 技术栈

| 层 | 选型 |
|---|---|
| 运行时 | Python 3.12、Node 20+ |
| API | FastAPI + Uvicorn（GZip 压缩） |
| 数据访问 | asyncpg 连接池 + 原生 SQL |
| 数据库 | PostgreSQL 16 + pgvector（Docker，宿主机 5433） |
| Agent | LangGraph（StateGraph 监督者拓扑） |
| 检索 | pgvector HNSW + 全文混合检索 |
| 工具协议 | MCP Server（`mcp>=2.3`，stdio） |
| 模型 | OpenAI 兼容协议；生产 qwen-plus，测试 qwen3:4b |
| 前端 | React 19、Vite 6、TypeScript 5、ECharts 5（按需引入） |
| 鉴权 | bcrypt + JWT（12 小时） |

---

## 4. 目录

```
backend/
├── app/
│   ├── main.py          # FastAPI 装配、生命周期、静态托管
│   ├── config.py        # 环境变量配置
│   ├── db.py            # 连接池、建表、物化视图刷新
│   ├── schema.sql       # 六 schema DDL
│   ├── metrics.py       # 18 个量化口径（唯一计算入口）
│   ├── graph.py         # LangGraph 多智能体
│   ├── tools.py         # 7 个 MCP 工具 + 只读守卫
│   ├── rag.py           # 切分 / 嵌入 / 混合检索
│   ├── llm.py           # 模型路由 + 向量（含离线降级）
│   ├── runner.py        # 一次 Run 的落库
│   ├── eval_harness.py  # 六项评测指标
│   ├── ingest.py        # 订单接入（幂等 + 逐行校验）
│   ├── seed.py          # 190 天确定性样例数据
│   ├── security.py      # 口令 / JWT / 当前用户
│   ├── mcp_server.py    # MCP stdio 服务端
│   └── routers/         # auth / dashboard / work / agents / settings
frontend/
├── src/
│   ├── App.tsx          # 路由（页面级懒加载）
│   ├── components/      # Shell / Panel / Chart / InsightCard / QAWidget
│   ├── pages/           # Login / Work / Agents / Settings / Screen
│   ├── lib/             # api 客户端、鉴权上下文
│   └── styles.css       # 设计系统
docker-compose.yml       # pgvector/pgvector:pg16
start.ps1                # Windows 一键启动
```

---

## 5. 数据模型（PostgreSQL，六个 schema）

| schema | 内容 |
|---|---|
| `raw` | orders / refunds / ad_daily / skus / platform_fees —— 明细，事务写入 |
| `mart` | order_lines（视图）、sku_daily、metric_daily（**物化视图**）、sku_summary（视图） |
| `agent` | agents / tools / runs / steps / insights |
| `kb` | docs / chunks（vector(1024) + tsvector，HNSW 索引） |
| `eval` | cases / runs |
| `ops` | users / connectors / model_configs / settings / audit_log |

**口径原则**：未知成本的 SKU，其毛利为 `NULL` 而非 0；成本覆盖率单独暴露，利润不会被静默高估。

---

## 6. 指标层

18 个口径全部由 SQL 计算，`metrics.py` 是唯一入口：

- 利润：净收入、贡献毛利、毛利率、每单毛利、成本覆盖率、亏损SKU占比
- 转化：订单数、销售件数、客单价、件单价、复购率
- 广告：广告花费、ROI、ACOS、广告占比
- 风险：退款率、退款金额
- 结构：利润集中度 CR5

**环比规则**：上一窗口必须有 ≥60% 的天数有数据才算基线，否则返回 `has_baseline=false`，
前端显示「—」，不会拿 1 天去比 90 天得出上万百分比。

---

## 7. 多智能体

```
START → Supervisor ─┬─→ MetricAnalyst  取数与同环比
                    ├─→ AnomalyHunter  Z-score 异动 + SKU 明细
                    ├─→ RagLibrarian   口径检索与引用
                    └─→ Advisor        结论合成（不产数字）
                              → END
```

- 数字全部来自工具，Agent 只做解释与建议；
- 每条结论带 `evidence`（`sku:*` / `kb:slug#idx`）；
- 无 API Key 时自动降级为**确定性分析引擎**：同样调用真实工具、给出真实数字，措辞由规则合成；
- 口径类提问（≤30 字且命中口径关键词）直接引用知识库原文。

---

## 8. 接入模块

支持 `csv / http / taobao / erp` 四类数据源：

- 测试：HTTP 类真实发起请求并记录延迟；CSV 类无需连通性测试；
- 同步：HTTP 类拉取订单数组，CSV 类在浏览器解析后按行提交；
- 写入 `raw.orders` 为**幂等 upsert**，逐行校验字段、日期、数量与 SKU，拒绝行给出原因；
- 同步后自动刷新 `mart` 物化视图。

---

## 9. 性能

| 措施 | 效果 |
|---|---|
| `mart` 用物化视图 + 唯一索引 | 90 天总览 2131ms → 28ms |
| 18 个指标并发计算 | 串行 36 次查询改为 `asyncio.gather` |
| 路由级懒加载 + 手动分包 | 首屏 JS 1371KB → 270KB |
| ECharts 按需注册 | echarts 分块 1012KB → 507KB |
| GZip 中间件 | 总览响应 3344B → 921B（-72%） |
| 明细表索引 | `orders(ordered_at)`、`orders(buyer_id,ordered_at)`、`refunds(order_id)` 等 |

---

## 10. 评测

`Agent 模型 → 评测` 一键跑批，输出：

任务成功率 · 工具调用准确率 · 引用命中率 · 幻觉率 · P95 延迟 · 单次 token 成本

幻觉判定：结论中每个数字必须能在工具观测值中找到（含「万」「百分比」量级换算）。
当前基线：**15/15 通过，幻觉率 0%，P95 < 200ms**。
