-- Lira 2.0 单库架构：raw / mart / agent / kb / eval / ops
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS agent;
CREATE SCHEMA IF NOT EXISTS kb;
CREATE SCHEMA IF NOT EXISTS eval;
CREATE SCHEMA IF NOT EXISTS ops;

-- ============ ops ============
CREATE TABLE IF NOT EXISTS ops.users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'analyst',
    status        TEXT NOT NULL DEFAULT 'active',
    last_login_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE ops.users ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE ops.users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS ops.connectors (
    id            BIGSERIAL PRIMARY KEY,
    kind          TEXT NOT NULL,
    name          TEXT NOT NULL,
    endpoint      TEXT NOT NULL DEFAULT '',
    config        JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled       BOOLEAN NOT NULL DEFAULT true,
    status        TEXT NOT NULL DEFAULT 'idle',
    last_tested_at TIMESTAMPTZ,
    last_test_ms  INT NOT NULL DEFAULT 0,
    last_sync_at  TIMESTAMPTZ,
    rows_synced   BIGINT NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.model_configs (
    id          BIGSERIAL PRIMARY KEY,
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    base_url    TEXT NOT NULL DEFAULT '',
    purpose     TEXT NOT NULL DEFAULT 'production',  -- production | test
    is_default  BOOLEAN NOT NULL DEFAULT false,
    note        TEXT NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.settings (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.audit_log (
    id         BIGSERIAL PRIMARY KEY,
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    target     TEXT NOT NULL DEFAULT '',
    payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============ raw ============
CREATE TABLE IF NOT EXISTS raw.skus (
    sku_id     TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    category   TEXT NOT NULL,
    supplier   TEXT NOT NULL,
    list_price NUMERIC(12,2) NOT NULL,
    cost       NUMERIC(12,2) NOT NULL,
    cost_known BOOLEAN NOT NULL DEFAULT true,
    pack_cost  NUMERIC(12,2) NOT NULL,
    shipping   NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.orders (
    order_id   TEXT PRIMARY KEY,
    sku_id     TEXT NOT NULL REFERENCES raw.skus(sku_id),
    buyer_id   TEXT NOT NULL,
    ordered_at DATE NOT NULL,
    qty        INT  NOT NULL,
    paid       NUMERIC(12,2) NOT NULL,
    channel    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_date  ON raw.orders(ordered_at);
CREATE INDEX IF NOT EXISTS idx_orders_buyer ON raw.orders(buyer_id, ordered_at);

CREATE TABLE IF NOT EXISTS raw.refunds (
    refund_id   TEXT PRIMARY KEY,
    order_id    TEXT NOT NULL REFERENCES raw.orders(order_id),
    refunded_at DATE NOT NULL,
    amount      NUMERIC(12,2) NOT NULL,
    reason      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.ad_daily (
    sku_id      TEXT NOT NULL REFERENCES raw.skus(sku_id),
    stat_date   DATE NOT NULL,
    spend       NUMERIC(12,2) NOT NULL,
    gmv         NUMERIC(12,2) NOT NULL,
    clicks      INT NOT NULL,
    impressions INT NOT NULL,
    PRIMARY KEY (sku_id, stat_date)
);

CREATE INDEX IF NOT EXISTS idx_refunds_order  ON raw.refunds(order_id);
CREATE INDEX IF NOT EXISTS idx_orders_sku_date ON raw.orders(sku_id, ordered_at);
CREATE INDEX IF NOT EXISTS idx_ad_daily_date   ON raw.ad_daily(stat_date);

CREATE TABLE IF NOT EXISTS raw.platform_fees (
    order_id   TEXT PRIMARY KEY REFERENCES raw.orders(order_id),
    commission NUMERIC(12,2) NOT NULL,
    tech_fee   NUMERIC(12,2) NOT NULL
);

-- ============ mart ============
-- 未知成本的订单行：cogs / shipping / pack / gross_margin 一律为 NULL，绝不按 0 处理。
CREATE OR REPLACE VIEW mart.order_lines AS
SELECT o.order_id, o.sku_id, o.buyer_id, s.title, s.category, s.supplier,
       o.ordered_at, o.qty, o.paid, o.channel,
       s.cost_known,
       COALESCE(r.amount, 0)                              AS refund_amount,
       o.paid - COALESCE(r.amount, 0)                     AS net_revenue,
       CASE WHEN s.cost_known THEN s.cost * o.qty ELSE NULL END      AS cogs,
       CASE WHEN s.cost_known THEN s.shipping * o.qty ELSE NULL END  AS shipping_cost,
       CASE WHEN s.cost_known THEN s.pack_cost * o.qty ELSE NULL END AS pack_cost,
       COALESCE(f.commission, 0) + COALESCE(f.tech_fee, 0) AS platform_fee,
       CASE WHEN r.refund_id IS NULL THEN 0 ELSE 1 END     AS refunded
FROM raw.orders o
JOIN raw.skus s USING (sku_id)
LEFT JOIN raw.refunds r ON r.order_id = o.order_id
LEFT JOIN raw.platform_fees f ON f.order_id = o.order_id;

DROP MATERIALIZED VIEW IF EXISTS mart.metric_daily CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mart.sku_daily CASCADE;
DROP VIEW IF EXISTS mart.metric_daily CASCADE;
DROP VIEW IF EXISTS mart.sku_summary CASCADE;
DROP VIEW IF EXISTS mart.sku_daily CASCADE;

CREATE MATERIALIZED VIEW mart.sku_daily AS
WITH base AS (
    SELECT sku_id, title, category, supplier, ordered_at AS stat_date,
           bool_and(cost_known)  AS cost_known,
           SUM(net_revenue)      AS net_revenue,
           SUM(cogs)             AS cogs,
           SUM(shipping_cost)    AS shipping_cost,
           SUM(pack_cost)        AS pack_cost,
           SUM(platform_fee)     AS platform_fee,
           COUNT(*)              AS order_count,
           SUM(qty)              AS units,
           SUM(refunded)         AS refund_orders,
           SUM(refund_amount)    AS refund_amount
    FROM mart.order_lines
    GROUP BY 1, 2, 3, 4, 5
), ads AS (
    SELECT sku_id, stat_date, SUM(spend) spend, SUM(gmv) ad_gmv,
           SUM(clicks) ad_clicks, SUM(impressions) ad_impressions
    FROM raw.ad_daily GROUP BY 1, 2
)
SELECT b.sku_id, b.title, b.category, b.supplier, b.stat_date, b.cost_known,
       b.net_revenue, b.cogs, b.shipping_cost, b.pack_cost, b.platform_fee,
       b.order_count, b.units, b.refund_orders, b.refund_amount,
       COALESCE(a.spend, 0)          AS ad_spend,
       COALESCE(a.ad_gmv, 0)         AS ad_gmv,
       COALESCE(a.ad_clicks, 0)      AS ad_clicks,
       COALESCE(a.ad_impressions, 0) AS ad_impressions,
       CASE WHEN b.cost_known
            THEN b.net_revenue - b.cogs - b.shipping_cost - b.pack_cost
                 - b.platform_fee - COALESCE(a.spend, 0)
            ELSE NULL END                                     AS gross_margin
FROM base b LEFT JOIN ads a USING (sku_id, stat_date);

CREATE OR REPLACE VIEW mart.sku_summary AS
SELECT sku_id, title, category, supplier,
       bool_and(cost_known) AS cost_known,
       SUM(net_revenue)   AS net_revenue,
       SUM(cogs)          AS cogs,
       SUM(shipping_cost) AS shipping_cost,
       SUM(pack_cost)     AS pack_cost,
       SUM(platform_fee)  AS platform_fee,
       SUM(ad_spend)      AS ad_spend,
       SUM(ad_gmv)        AS ad_gmv,
       SUM(gross_margin)  AS gross_margin,
       SUM(order_count)   AS order_count,
       SUM(units)         AS units,
       SUM(refund_orders) AS refund_orders,
       SUM(refund_amount) AS refund_amount,
       CASE WHEN SUM(net_revenue) > 0
            THEN SUM(gross_margin) / SUM(net_revenue) ELSE NULL END AS margin_rate,
       CASE WHEN SUM(order_count) > 0
            THEN SUM(gross_margin) / SUM(order_count) ELSE NULL END AS margin_per_order,
       CASE WHEN SUM(order_count) > 0
            THEN SUM(refund_orders)::numeric / SUM(order_count) ELSE 0 END AS refund_rate,
       CASE WHEN SUM(ad_spend) > 0
            THEN SUM(ad_gmv) / SUM(ad_spend) ELSE 0 END          AS ad_roi
FROM mart.sku_daily
GROUP BY 1, 2, 3, 4;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sku_daily ON mart.sku_daily (sku_id, stat_date);

CREATE MATERIALIZED VIEW mart.metric_daily AS
SELECT stat_date,
       SUM(net_revenue)   AS net_revenue,
       SUM(gross_margin)  AS gross_margin,
       SUM(ad_spend)      AS ad_spend,
       SUM(ad_gmv)        AS ad_gmv,
       SUM(order_count)   AS order_count,
       SUM(units)         AS units,
       SUM(refund_orders) AS refund_orders,
       SUM(refund_amount) AS refund_amount,
       CASE WHEN SUM(net_revenue) FILTER (WHERE cost_known) > 0
            THEN SUM(gross_margin) / SUM(net_revenue) FILTER (WHERE cost_known) END AS margin_rate,
       CASE WHEN SUM(order_count) > 0
            THEN SUM(refund_orders)::numeric / SUM(order_count) ELSE 0 END AS refund_rate,
       CASE WHEN SUM(ad_spend) > 0
            THEN SUM(ad_gmv) / SUM(ad_spend) ELSE 0 END          AS ad_roi,
       CASE WHEN SUM(order_count) > 0
            THEN SUM(net_revenue) / SUM(order_count) ELSE 0 END  AS aov,
       CASE WHEN SUM(net_revenue) > 0
            THEN SUM(net_revenue) FILTER (WHERE cost_known) / SUM(net_revenue) ELSE 0 END AS cost_coverage
FROM mart.sku_daily
GROUP BY 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_metric_daily ON mart.metric_daily (stat_date);

-- ============ agent ============
CREATE TABLE IF NOT EXISTS agent.agents (
    key           TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    model_hint    TEXT NOT NULL DEFAULT 'production',
    system_prompt TEXT NOT NULL DEFAULT '',
    tools         TEXT[] NOT NULL DEFAULT '{}',
    enabled       BOOLEAN NOT NULL DEFAULT true,
    sort_order    INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent.tools (
    key          TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL,
    input_schema JSONB NOT NULL,
    calls        BIGINT NOT NULL DEFAULT 0,
    avg_latency  NUMERIC(10,1) NOT NULL DEFAULT 0,
    enabled      BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS agent.runs (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    trigger     TEXT NOT NULL DEFAULT 'manual',
    model       TEXT NOT NULL DEFAULT '',
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    latency_ms  INT NOT NULL DEFAULT 0,
    tokens_in   INT NOT NULL DEFAULT 0,
    tokens_out  INT NOT NULL DEFAULT 0,
    cost_usd    NUMERIC(10,6) NOT NULL DEFAULT 0,
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    result      JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_runs_started ON agent.runs(started_at DESC);

CREATE TABLE IF NOT EXISTS agent.steps (
    id          BIGSERIAL PRIMARY KEY,
    run_id      BIGINT NOT NULL REFERENCES agent.runs(id) ON DELETE CASCADE,
    idx         INT NOT NULL,
    agent_key   TEXT NOT NULL,
    thought     TEXT NOT NULL DEFAULT '',
    tool        TEXT NOT NULL DEFAULT '',
    args        JSONB NOT NULL DEFAULT '{}'::jsonb,
    observation JSONB NOT NULL DEFAULT '{}'::jsonb,
    latency_ms  INT NOT NULL DEFAULT 0,
    tokens      INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_steps_run ON agent.steps(run_id, idx);

CREATE TABLE IF NOT EXISTS agent.insights (
    id         BIGSERIAL PRIMARY KEY,
    scope      TEXT NOT NULL,
    ref        TEXT NOT NULL DEFAULT '',
    headline   TEXT NOT NULL,
    drivers    JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence NUMERIC(4,3) NOT NULL DEFAULT 0,
    evidence   JSONB NOT NULL DEFAULT '[]'::jsonb,
    actions    JSONB NOT NULL DEFAULT '[]'::jsonb,
    model      TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_insights_scope ON agent.insights(scope, ref, created_at DESC);

-- ============ kb ============
CREATE TABLE IF NOT EXISTS kb.docs (
    id         BIGSERIAL PRIMARY KEY,
    slug       TEXT UNIQUE NOT NULL,
    title      TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kb.chunks (
    id        BIGSERIAL PRIMARY KEY,
    doc_id    BIGINT NOT NULL REFERENCES kb.docs(id) ON DELETE CASCADE,
    idx       INT NOT NULL,
    content   TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    tsv       tsvector
);
CREATE INDEX IF NOT EXISTS idx_chunks_fts ON kb.chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_vec ON kb.chunks
    USING hnsw (embedding vector_cosine_ops);

-- ============ eval ============
CREATE TABLE IF NOT EXISTS eval.cases (
    id             BIGSERIAL PRIMARY KEY,
    key            TEXT UNIQUE NOT NULL,
    category       TEXT NOT NULL,
    question       TEXT NOT NULL,
    expected_tools TEXT[] NOT NULL DEFAULT '{}',
    expect_contains TEXT[] NOT NULL DEFAULT '{}',
    rubric         TEXT NOT NULL DEFAULT '',
    difficulty     TEXT NOT NULL DEFAULT 'medium'
);

CREATE TABLE IF NOT EXISTS eval.runs (
    id                 BIGSERIAL PRIMARY KEY,
    model              TEXT NOT NULL DEFAULT '',
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at        TIMESTAMPTZ,
    total              INT NOT NULL DEFAULT 0,
    passed             INT NOT NULL DEFAULT 0,
    success_rate       NUMERIC(5,3) NOT NULL DEFAULT 0,
    tool_accuracy      NUMERIC(5,3) NOT NULL DEFAULT 0,
    citation_hit       NUMERIC(5,3) NOT NULL DEFAULT 0,
    hallucination_rate NUMERIC(5,3) NOT NULL DEFAULT 0,
    p95_latency_ms     INT NOT NULL DEFAULT 0,
    avg_cost           NUMERIC(10,6) NOT NULL DEFAULT 0,
    detail             JSONB NOT NULL DEFAULT '[]'::jsonb
);
