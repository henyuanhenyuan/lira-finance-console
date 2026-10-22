# Lira · 本地利润诊断

面向淘宝/天猫中小商家的本地经营分析产品。

平台知道卖了多少，但不知道商家的成本；商家的表格知道成本，却没有平台订单。Lira 把两边接起来，算出真实贡献毛利，找出**卖一单亏一单的 SKU**、**广告浪费**和**退款异常**。数字由 DuckDB 计算，建议由本地模型给出；数据不出门。

---

## 快速开始

前置：Python 3.13、uv、Node 20+、Ollama（可选，用于 AI 建议）。

```bash
uv sync --directory product
```

```bash
cd product/web && npm ci && npm run build
```

```bash
cd product && ollama pull qwen3:4b
```

```bash
uv run --directory product python -m app.main
```

打开 http://127.0.0.1:8010

没有构建前端时，服务会回退到 `product/static` 的原生页面；没有 Ollama 时，问答回退到确定性模板。

---

## 五个页面

- **今日**：利润、订单、客单价、成本覆盖、环比异常、趋势、三条动作、利润桥、类目
- **亏损商品**：按总亏损排序，点开看利润桥、证据、建议
- **广告浪费**：低于盈亏平衡 ROI 的计划与估算浪费
- **问一句**：自然语言问答，模板事实 + 模型建议 + 证据
- **数据与同步**：收件箱、连接器、数据源、三类导入、SKU 映射、成本导入、历史、口径、备份/诊断

---

## 导入数据

支持 CSV/XLSX：

- 订单、退款、广告：列映射、逐行校验、替换或按主键增量；
- 成本表：商品编码、生效日期、采购单价，运费/包材可选；
- SKU 映射：平台商品 ID → 商家款号；
- 真实淘宝“已卖出的宝贝”导出：GBK、真实列名、从宝贝标题提取款号。

也可以把文件放进 `product/data/inbox/`，文件名以 `orders_`、`refunds_`、`ads_`、`costs_` 开头。文件事件会立即触发，5 分钟轮询兜底。

---

## 连接器

- 淘宝开放平台：界面保存 app key / app secret / 商家 session；真实拉取需要 ISV 权限与可用会话；
- ERP：通用 `/health` + `/orders` 契约，具体厂商需适配；
- 凭证本机加密，接口不回显 secret；配额默认 60 次/分钟；PII 最小化。

没有凭证时不会发起真实请求，也不会伪造联调结果。

---

## 测试与评测

```bash
uv run --directory product pytest
```

```bash
uv run --directory product python ../scripts/eval.py --all
```

- 35 个后端/契约/导入/连接器测试；
- 100 条模型评测问题；自动检查意图、内容、动作，`human_score` 需要人工打分。

---

## 配置

| 变量 | 说明 |
|---|---|
| `LIRA_API_HOST` / `LIRA_API_PORT` | 监听地址/端口，默认 `127.0.0.1:8010` |
| `LIRA_PIN` | 局域网访问 PIN；设置后 API 需要 `X-Lira-Pin` |
| `LIRA_MODEL` | Ollama 模型，默认 `qwen3:4b` |
| `LIRA_OLLAMA_URL` | Ollama 地址，默认 `http://127.0.0.1:11434` |
| `LIRA_SYNC_SECONDS` | 收件箱兜底轮询间隔，默认 300 |
| `LIRA_TOP_LIVE` | 设为 `1` 时连接器测试会发起真实 TOP 签名校验 |
| `LIRA_BACKUP_KEY` | 备份加密密钥；不设则使用本机密钥 |
| `LIRA_WEB_ROOT` | 前端构建产物目录，默认 `product/web/dist` |

---

## 部署

- 启动：`scripts/start.ps1`
- 构建前端：`scripts/build-web.ps1`
- Windows 服务：`scripts/install-service.ps1`（需要 NSSM）
- CI：`.github/workflows/ci.yml`

---

## 已知限制

- 成本口径只含采购价、运费、包材；平台佣金/支付费按类目费率；退款按订单日期归集；未建模广告以外的营销费用；
- 淘宝/ERP 真实拉取需要外部授权；
- 真实商家数据对账、人工 eval 评分仍需外部输入；
- Windows 服务安装依赖 NSSM，尚未在目标机器验证；
- React bundle 约 2.3 MB（gzip 约 768 KB），可继续做路由级拆包。

架构与不变量见 [ARCHITECTURE.md](ARCHITECTURE.md)。
