# Lira 现产品架构（唯一权威）

> 本文件描述当前在 `product/` 中交付的产品，是本仓库的最高技术标准。
> 旧架构、旧文档、旧产品或与本文冲突的内容一律不存在；冲突时以本文和当前代码为准。

版本：1.0　｜　状态：当前产品　｜　更新日期：2026-10-22

---

## 1. 产品定位

Lira 是面向淘宝/天猫中小商家的**本地利润诊断产品**：

- 把平台订单/退款/广告与商家自己的成本表连起来，算出**真实贡献毛利**；
- 找出**卖一单亏一单的 SKU**、**广告浪费**和**退款异常**；
- 用确定性引擎算数字，用本地模型给建议；
- 全部在本机运行，数据不出门。

五个页面：今日、亏损商品、广告浪费、问一句、数据与同步。

产品不是大屏、不是 BI 拖拽器、不是多租户 SaaS、不是开放式 AI Agent。

---

## 2. 系统形态

**模块化单体 + 本地单租户。**

- 一个 Python 进程：FastAPI、导入、分析、调度、AI 网关；
- 一个本地 React SPA，由同一个 FastAPI 进程托管；
- DuckDB 单文件仓，ops 表保存快照、分析记录、导入日志、动作记录；
- Ollama 本地模型，可选；
- 不拆微服务，不引入 Kafka/Flink/Redis/Postgres/Airflow/Java。

单机、单商家、本地优先。多租户不在当前产品范围内。

---

## 3. 技术栈（当前代码）

| 层 | 选型 |
|---|---|
| 语言 | Python 3.13 |
| 包管理 | uv |
| API | FastAPI + Uvicorn |
| 契约 | Pydantic v2；请求 `extra="forbid"` |
| 数据引擎 | DuckDB（单文件） |
| Excel/CSV | openpyxl + 标准库 csv |
| 本地模型 | Ollama，默认 `qwen3:4b`，JSON Schema 结构化输出 |
| 加密 | cryptography（凭证/备份） |
| 文件事件 | watchdog |
| 前端 | React 19、Vite、TypeScript、Tailwind CSS 4、Ant Design 6、ECharts 6、TanStack Query 5、React Router 7、PWA |
| 测试 | pytest |
| CI | GitHub Actions（Windows） |
| 服务化 | PowerShell + NSSM（外部依赖） |

---

## 4. 目录

```
product/
├── app/
│   ├── main.py          # FastAPI、API v1、PIN、SSE、静态托管
│   ├── db.py            # DuckDB、视图、快照、事务、ops 表
│   ├── semantic.py      # 指标/维度目录（口径版本）
│   ├── analysis.py      # 利润桥/亏损/广告/环比/异常/趋势/类目
│   ├── imports.py       # 订单/退款/广告导入、收件箱扫描
│   ├── costs.py         # 成本表上传、列映射、模板
│   ├── connectors.py    # 凭证、配额、PII、连接器状态/拉取
│   ├── top.py           # 淘宝开放平台签名与客户端
│   ├── erp.py           # 通用 ERP HTTP 客户端
│   ├── scheduler.py     # 文件事件 + 定时兜底
│   ├── llm.py           # 本地模型建议、数字/动作校验、模板回退
│   ├── ops.py           # 状态、加密备份、诊断包
│   └── seed.py          # 确定性样例数据
├── web/                 # React 源码；构建产物 dist/
├── static/              # 无构建产物时的原生回退页
├── sample/              # 样例 CSV（运行时生成/忽略）
├── eval/                # 100 条模型评测集
├── test_smoke.py        # 后端/契约/导入/连接器/eval 测试
└── pyproject.toml
scripts/                 # 启动、构建、服务安装、eval
.github/workflows/ci.yml
README.md
ARCHITECTURE.md
```

---

## 5. 数据流

```
文件上传 / 收件箱 / TOP / ERP
  → imports：列映射、逐行校验、拒绝行报告
  → 事务写入 raw
  → 视图 lake.lines / lake.ad_lines（成本 as-of join、SKU 别名）
  → 分析：利润桥 / 亏损 SKU / 广告浪费 / 环比异常 / 趋势 / 类目
  → ops.snapshot + ops.analysis_run + 证据
  → API v1
  → React 五页
```

- 导入是事务性的；失败回滚。
- 每次导入/重载递增 `ops.snapshot`。
- 订单、退款、广告、成本各自有数据集注册表记录。
- 成本按 `effective_from` 做 ASOF 匹配；支持平台 SKU → 商家款号的别名。
- 未知成本是“未知”，不是 0；成本覆盖不足时利润为估算。

---

## 6. 数据模型

**raw**：`orders`、`refunds`、`ads`、`costs`、`skus`、`fees`、`sku_alias`。

**lake**：
- `lake.lines`：订单行 + 退款 + 成本 + 平台费 + SKU 信息；
- `lake.ad_lines`：广告花费与成交。

**ops**：
- `snapshot`：快照号；
- `analysis_run`：分析/问答记录与证据 JSON；
- `dataset_registry`：数据集、来源、行数、最新日期；
- `action_ack`：采纳/忽略；
- `import_log`、`cost_import`、`telemetry`。

---

## 7. 指标与分析

指标定义集中在 `semantic.py`，当前口径版本 `1.0.0`：

- 净收入、贡献毛利、成本覆盖率、每单亏损、退款率
- 广告花费、广告 ROI、订单数、销售件数、客单价

分析：

- 利润桥：实付 → 退款 → 商品成本 → 运费/包材 → 平台费 → 广告 → 贡献毛利；
- 环比：净收入、贡献毛利、订单数、客单价；
- 异常：|变化| ≥ 20%；
- 趋势：按日/月；
- 类目：净收入、占比、贡献毛利、订单；
- 亏损 SKU、广告浪费、SKU 明细与证据。

所有比率都是 `SUM(a) / SUM(b)`，不是 `AVG(a/b)`。除零给 NULL，不给 0。

---

## 8. API v1

统一错误信封：`{"error":{"code","message"}}`。

- `GET /api/v1/overview`
- `GET /api/v1/loss-skus`
- `GET /api/v1/ad-waste`
- `GET /api/v1/skus/{sku}`
- `GET /api/v1/trend`
- `GET /api/v1/data-health`
- `GET /api/v1/semantic/catalogue`
- `GET /api/v1/datasets`
- `GET /api/v1/history`
- `GET /api/v1/evidence/{run_id}`
- `POST /api/v1/ask`、`GET /api/v1/ask/stream`
- `POST /api/v1/sync`、`POST /api/v1/import/scan`
- 订单/退款/广告/成本导入、SKU 别名、连接器、运维接口

`LIRA_PIN` 设置后，所有 `/api` 请求需要 `X-Lira-Pin`。

---

## 9. AI 边界

本地模型只做三件事：

1. 输入映射建议（连接器/导入的候选）；
2. **行动建议**：在结构化 findings 上生成 1–3 条动作；
3. 问答路由（关键词 + SKU 识别）。

模型**不**做：

- 算数字；
- 写自由 SQL；
- 决定调查路径（固定分析流程）；
- 多 agent、planning、实时盯流。

事实和数字由确定性模板给出；模型建议必须通过数字/动作校验，否则回退模板。模型不可用时产品照常工作。

---

## 10. 连接器

- **文件夹**：`product/data/inbox/`，watchdog 文件事件 + 5 分钟兜底；
- **淘宝开放平台**：`top.py` 实现 MD5 签名、`time_get`、订单拉取；需要 app key/secret/session/ISV 权限；
- **ERP**：`erp.py` 定义 `/health` 与 `/orders` 的通用契约；具体厂商接口需要适配。

凭证用本机密钥加密保存；状态接口不回显 secret；配额默认 60 次/分钟；订单 PII 在进入仓库前丢弃，买家标识只保留截断哈希。

**没有凭证就不发起真实请求，也不伪造联调结果。**

---

## 11. 安全与运维

- 凭证加密；备份加密（含数据库、凭证、日志）；
- 诊断包只含日志与状态；
- PIN 保护局域网访问；
- 本地数据库依赖操作系统磁盘加密；
- 审计记录：导入、凭证、采纳动作、分析记录；
- 备份/诊断通过 API 与数据页操作。

---

## 12. 运行与部署

```bash
uv sync --directory product
cd product/web && npm ci && npm run build
uv run --directory product python -m app.main
```

- 默认 `127.0.0.1:8010`；`LIRA_API_HOST` / `LIRA_API_PORT` 可改。
- 没有 `web/dist` 时回退到 `product/static`。
- Windows 服务：`scripts/install-service.ps1`（需要 NSSM）。
- 启动脚本：`scripts/start.ps1`。
- 前端构建：`scripts/build-web.ps1`。

---

## 13. 测试与评测

- `uv run --directory product pytest`：35 个测试；
- 覆盖：导入、映射、事务、快照、v1、趋势、历史/证据、备份/诊断、PIN、TOP 签名、TOP/ERP mock 拉取、真实淘宝导出形状、GBK/XLSX；
- `uv run --directory product python ../scripts/eval.py --all`：100 条问题；
- 自动检查意图/内容/动作；`human_score` 列留空，需要人工评分。

---

## 14. 不变量

1. 数字由 DuckDB 计算，模型不碰数字。
2. 未知不是 0；成本覆盖不足时明确标“估算”。
3. 导入事务化；失败回滚。
4. 没有真实凭证就不发真实连接器请求。
5. 当前 `product/` 是唯一产品；旧代码、旧文档、旧 worktree/分支不得保留。
6. 任何新增都先问：是否让商家每天打开 5 分钟、按建议改一件事更容易；否则不加。
