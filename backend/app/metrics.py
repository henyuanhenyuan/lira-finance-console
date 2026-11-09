"""指标层：18 个量化口径，全部由 SQL 计算。

Agent 只能读这里，不能自己算数。
窗口口径：$1 = 起点前推天数, $2 = 终点前推天数（0 表示到今天）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from . import db

VERSION = "1.0.0"

CATALOGUE: dict[str, dict[str, str]] = {
    "net_revenue": {"label": "净收入", "unit": "currency", "group": "利润",
                    "formula": "买家实付 - 退款金额"},
    "gross_margin": {"label": "贡献毛利", "unit": "currency", "group": "利润",
                     "formula": "净收入 - 采购成本 - 运费 - 包材 - 平台费 - 广告"},
    "margin_rate": {"label": "毛利率", "unit": "ratio", "group": "利润",
                    "formula": "贡献毛利 / 净收入（仅已知成本部分）"},
    "margin_per_order": {"label": "每单毛利", "unit": "currency", "group": "利润",
                         "formula": "贡献毛利 / 订单数"},
    "cost_coverage": {"label": "成本覆盖率", "unit": "ratio", "group": "利润",
                      "formula": "已知成本 SKU 的收入 / 总收入"},
    "loss_sku_ratio": {"label": "亏损SKU占比", "unit": "ratio", "group": "利润",
                       "formula": "窗口内毛利为负的 SKU 数 / 有成本记录的 SKU 数"},
    "order_count": {"label": "订单数", "unit": "count", "group": "转化",
                    "formula": "去重订单数"},
    "units_sold": {"label": "销售件数", "unit": "count", "group": "转化",
                   "formula": "订单行数量之和"},
    "aov": {"label": "客单价", "unit": "currency", "group": "转化",
            "formula": "净收入 / 订单数"},
    "unit_price": {"label": "件单价", "unit": "currency", "group": "转化",
                   "formula": "净收入 / 销售件数"},
    "repurchase_rate": {"label": "复购率", "unit": "ratio", "group": "转化",
                        "formula": "窗口内下单≥2 次的买家 / 总买家"},
    "ad_spend": {"label": "广告花费", "unit": "currency", "group": "广告",
                 "formula": "广告表花费之和"},
    "ad_roi": {"label": "广告ROI", "unit": "ratio", "group": "广告",
               "formula": "广告成交 / 广告花费"},
    "acos": {"label": "ACOS", "unit": "ratio", "group": "广告",
             "formula": "广告花费 / 广告成交"},
    "ad_share": {"label": "广告占比", "unit": "ratio", "group": "广告",
                 "formula": "广告花费 / 净收入"},
    "refund_rate": {"label": "退款率", "unit": "ratio", "group": "风险",
                    "formula": "退款订单数 / 订单数"},
    "refund_amount": {"label": "退款金额", "unit": "currency", "group": "风险",
                      "formula": "退款金额之和"},
    "cr5": {"label": "利润集中度CR5", "unit": "ratio", "group": "结构",
            "formula": "贡献毛利前 5 名 SKU / 总贡献毛利"},
}

# 仅用于「展示成百分比」的指标。aov / unit_price / margin_per_order 是金额，不在此列。
RATIO_METRICS = {"margin_rate", "cost_coverage", "loss_sku_ratio",
                 "repurchase_rate", "ad_roi", "acos", "ad_share", "refund_rate", "cr5"}

_W = "WHERE stat_date > CURRENT_DATE - $1::int AND stat_date <= CURRENT_DATE - $2::int"

WINDOW_SQL: dict[str, str] = {
    "net_revenue": f"SELECT COALESCE(SUM(net_revenue),0) FROM mart.metric_daily {_W}",
    "gross_margin": f"SELECT COALESCE(SUM(gross_margin),0) FROM mart.metric_daily {_W}",
    "margin_rate": f"""
        SELECT COALESCE(SUM(gross_margin) / NULLIF(SUM(net_revenue) FILTER (WHERE cost_known),0), 0)
        FROM mart.sku_daily {_W}""",
    "margin_per_order": f"""
        SELECT COALESCE(SUM(gross_margin) / NULLIF(SUM(order_count),0), 0)
        FROM mart.sku_daily {_W}""",
    "cost_coverage": f"""
        SELECT COALESCE(SUM(net_revenue) FILTER (WHERE cost_known)
                        / NULLIF(SUM(net_revenue),0), 0)
        FROM mart.sku_daily {_W}""",
    "loss_sku_ratio": f"""
        WITH s AS (
            SELECT sku_id, SUM(gross_margin) gm FROM mart.sku_daily
            {_W} AND cost_known GROUP BY 1
        )
        SELECT COALESCE(
            COUNT(*) FILTER (WHERE gm < 0)::numeric / NULLIF(COUNT(*),0), 0) FROM s""",
    "order_count": f"SELECT COALESCE(SUM(order_count),0) FROM mart.metric_daily {_W}",
    "units_sold": f"SELECT COALESCE(SUM(units),0) FROM mart.metric_daily {_W}",
    "aov": f"""SELECT COALESCE(SUM(net_revenue)/NULLIF(SUM(order_count),0),0)
               FROM mart.metric_daily {_W}""",
    "unit_price": f"""SELECT COALESCE(SUM(net_revenue)/NULLIF(SUM(units),0),0)
                      FROM mart.metric_daily {_W}""",
    "repurchase_rate": """
        WITH b AS (
            SELECT buyer_id, COUNT(*) c FROM raw.orders
            WHERE ordered_at > CURRENT_DATE - $1::int AND ordered_at <= CURRENT_DATE - $2::int
            GROUP BY 1
        )
        SELECT COALESCE(COUNT(*) FILTER (WHERE c >= 2)::numeric / NULLIF(COUNT(*),0), 0) FROM b""",
    "ad_spend": f"SELECT COALESCE(SUM(ad_spend),0) FROM mart.metric_daily {_W}",
    "ad_roi": f"""SELECT COALESCE(SUM(ad_gmv)/NULLIF(SUM(ad_spend),0),0)
                  FROM mart.metric_daily {_W}""",
    "acos": f"""SELECT COALESCE(SUM(ad_spend)/NULLIF(SUM(ad_gmv),0),0)
                FROM mart.metric_daily {_W}""",
    "ad_share": f"""SELECT COALESCE(SUM(ad_spend)/NULLIF(SUM(net_revenue),0),0)
                    FROM mart.metric_daily {_W}""",
    "refund_rate": f"""SELECT COALESCE(SUM(refund_orders)::numeric/NULLIF(SUM(order_count),0),0)
                       FROM mart.metric_daily {_W}""",
    "refund_amount": f"SELECT COALESCE(SUM(refund_amount),0) FROM mart.metric_daily {_W}",
    "cr5": f"""
        WITH s AS (
            SELECT sku_id, SUM(gross_margin) gm FROM mart.sku_daily
            {_W} AND cost_known GROUP BY 1
        ), r AS (
            SELECT gm, SUM(gm) OVER () total,
                   ROW_NUMBER() OVER (ORDER BY gm DESC) rn FROM s
        )
        SELECT COALESCE(SUM(gm) FILTER (WHERE rn <= 5)
                        / NULLIF(MAX(total),0), 0) FROM r""",
}

SERIES_SQL: dict[str, str] = {
    "net_revenue": "SELECT stat_date AS d, net_revenue AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "gross_margin": "SELECT stat_date AS d, gross_margin AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "margin_rate": "SELECT stat_date AS d, margin_rate AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int AND margin_rate IS NOT NULL ORDER BY d",
    "margin_per_order": "SELECT stat_date AS d, CASE WHEN order_count>0 THEN gross_margin/order_count END AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "cost_coverage": "SELECT stat_date AS d, cost_coverage AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "loss_sku_ratio": """
        SELECT stat_date AS d,
               COUNT(*) FILTER (WHERE gross_margin < 0)::numeric / NULLIF(COUNT(*),0) AS v
        FROM mart.sku_daily
        WHERE stat_date > CURRENT_DATE - $1::int AND cost_known
        GROUP BY stat_date ORDER BY d""",
    "order_count": "SELECT stat_date AS d, order_count AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "units_sold": "SELECT stat_date AS d, units AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "aov": "SELECT stat_date AS d, aov AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "unit_price": "SELECT stat_date AS d, CASE WHEN units>0 THEN net_revenue/units END AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "repurchase_rate": """
        SELECT t.d, COUNT(*) FILTER (WHERE t.prior > 0)::numeric / NULLIF(COUNT(*),0) AS v
        FROM (
            SELECT o.ordered_at AS d, o.buyer_id,
                   (SELECT COUNT(*) FROM raw.orders p
                    WHERE p.buyer_id = o.buyer_id AND p.ordered_at < o.ordered_at) AS prior
            FROM raw.orders o WHERE o.ordered_at > CURRENT_DATE - $1::int
        ) t GROUP BY t.d ORDER BY t.d""",
    "ad_spend": "SELECT stat_date AS d, ad_spend AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "ad_roi": "SELECT stat_date AS d, ad_roi AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "acos": "SELECT stat_date AS d, CASE WHEN ad_gmv>0 THEN ad_spend/ad_gmv END AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "ad_share": "SELECT stat_date AS d, CASE WHEN net_revenue>0 THEN ad_spend/net_revenue END AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "refund_rate": "SELECT stat_date AS d, refund_rate AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "refund_amount": "SELECT stat_date AS d, refund_amount AS v FROM mart.metric_daily WHERE stat_date > CURRENT_DATE - $1::int ORDER BY d",
    "cr5": """
        WITH ranked AS (
            SELECT stat_date, gross_margin,
                   ROW_NUMBER() OVER (PARTITION BY stat_date ORDER BY gross_margin DESC) AS rn,
                   SUM(gross_margin) OVER (PARTITION BY stat_date) AS total
            FROM mart.sku_daily
            WHERE stat_date > CURRENT_DATE - $1::int AND cost_known
        )
        SELECT stat_date AS d,
               CASE WHEN total > 0 THEN SUM(gross_margin) FILTER (WHERE rn <= 5)/total END AS v
        FROM ranked GROUP BY stat_date, total ORDER BY d""",
}


RANKING_METRICS = ["gross_margin", "net_revenue", "margin_rate", "ad_spend", "refund_amount"]


def catalogue() -> dict[str, Any]:
    return {
        "version": VERSION,
        "metrics": [{"name": k, **v, "ratio": k in RATIO_METRICS} for k, v in CATALOGUE.items()],
        "groups": ["利润", "转化", "广告", "风险", "结构"],
    }


async def series(metric: str, days: int = 30) -> list[dict[str, Any]]:
    if metric not in SERIES_SQL:
        raise KeyError(f"未知指标: {metric}")
    rows = await db.fetch(SERIES_SQL[metric], days)
    return [{"date": r["d"].isoformat(), "value": float(r["v"]) if r["v"] is not None else None}
            for r in rows]


async def window_value(metric: str, start: int, end: int = 0) -> float:
    if metric not in WINDOW_SQL:
        raise KeyError(f"未知指标: {metric}")
    val = await db.fetchval(WINDOW_SQL[metric], start, end)
    return float(val) if val is not None else 0.0


async def _day_coverage(start: int, end: int) -> int:
    val = await db.fetchval(
        """SELECT COUNT(DISTINCT stat_date) FROM mart.metric_daily
           WHERE stat_date > CURRENT_DATE - $1::int AND stat_date <= CURRENT_DATE - $2::int""",
        start, end,
    )
    return int(val or 0)


async def compare(metric: str, days: int = 7) -> dict[str, Any]:
    cur = await window_value(metric, days, 0)
    prev = await window_value(metric, days * 2, days)
    delta = cur - prev
    # 上一窗口必须真的有足够多的天数，否则「环比」是在拿 1 天比 90 天
    prev_days = await _day_coverage(days * 2, days)
    has_baseline = abs(prev) > 1e-9 and prev_days >= max(1, int(days * 0.6))
    pct = (delta / abs(prev)) if has_baseline else 0.0
    return {
        "metric": metric,
        "label": CATALOGUE.get(metric, {}).get("label", metric),
        "unit": CATALOGUE.get(metric, {}).get("unit", "number"),
        "ratio": metric in RATIO_METRICS,
        "current": round(cur, 4),
        "previous": round(prev, 4),
        "delta": round(delta, 4),
        "pct": round(pct, 4),
        "has_baseline": has_baseline,
        "days": days,
    }


async def overview(days: int = 7) -> dict[str, Any]:
    keys = list(CATALOGUE)
    results = await asyncio.gather(*(compare(k, days) for k in keys))
    return dict(zip(keys, results))


async def sku_ranking(metric: str = "gross_margin", days: int = 7, limit: int = 10, asc: bool = True):
    if metric not in RANKING_METRICS:
        raise KeyError(f"不支持的排行指标: {metric}")
    order = "ASC" if asc else "DESC"
    rows = await db.fetch(
        f"""
        SELECT d.sku_id, d.title, d.category, d.supplier,
               SUM(d.net_revenue)   AS net_revenue,
               SUM(d.gross_margin)  AS gross_margin,
               SUM(d.ad_spend)      AS ad_spend,
               SUM(d.order_count)   AS order_count,
               SUM(d.refund_orders) AS refund_orders,
               CASE WHEN SUM(d.net_revenue)>0
                    THEN SUM(d.gross_margin)/SUM(d.net_revenue) END AS margin_rate,
               CASE WHEN SUM(d.ad_spend)>0
                    THEN SUM(d.ad_gmv)/SUM(d.ad_spend) END AS ad_roi
        FROM mart.sku_daily d
        WHERE d.stat_date > CURRENT_DATE - $1::int AND d.cost_known
        GROUP BY 1,2,3,4
        ORDER BY {metric} {order} NULLS LAST
        LIMIT $2
        """,
        days, limit,  # type: ignore[arg-type]
    )
    return [db.jsonable(dict(r)) for r in rows]


async def category_mix(days: int = 30):
    rows = await db.fetch(
        """
        SELECT category,
               SUM(net_revenue)  AS net_revenue,
               SUM(gross_margin) AS gross_margin,
               SUM(order_count)  AS order_count
        FROM mart.sku_daily
        WHERE stat_date > CURRENT_DATE - $1::int AND cost_known
        GROUP BY 1 ORDER BY gross_margin DESC
        """,
        days,
    )
    return [db.jsonable(dict(r)) for r in rows]


async def anomalies(days: int = 7, z_threshold: float = 1.8):
    rows = await db.fetch(
        """
        WITH win AS (
            SELECT sku_id, SUM(gross_margin) AS cur
            FROM mart.sku_daily
            WHERE stat_date > CURRENT_DATE - $1::int AND cost_known GROUP BY 1
        ), base AS (
            SELECT sku_id, AVG(gross_margin) AS mu, STDDEV_POP(gross_margin) AS sd
            FROM mart.sku_daily
            WHERE stat_date <= CURRENT_DATE - $1::int
              AND stat_date > CURRENT_DATE - $1::int * 4
              AND cost_known
            GROUP BY 1
        )
        SELECT w.sku_id, s.title, s.category, w.cur, b.mu, b.sd,
               CASE WHEN b.sd > 0 THEN (w.cur - b.mu)/b.sd ELSE 0 END AS z,
               CASE WHEN b.mu <> 0 THEN (w.cur - b.mu)/ABS(b.mu) ELSE 0 END AS pct
        FROM win w JOIN base b USING (sku_id) JOIN raw.skus s USING (sku_id)
        WHERE ABS(CASE WHEN b.sd > 0 THEN (w.cur - b.mu)/b.sd ELSE 0 END) >= $2
        ORDER BY ABS(CASE WHEN b.sd > 0 THEN (w.cur - b.mu)/b.sd ELSE 0 END) DESC
        LIMIT 10
        """,
        days, z_threshold,
    )
    return [
        {
            "sku_id": r["sku_id"], "title": r["title"], "category": r["category"],
            "current": round(float(r["cur"] or 0), 2),
            "baseline": round(float(r["mu"] or 0), 2),
            "z": round(float(r["z"] or 0), 2),
            "pct": round(float(r["pct"] or 0), 3),
            "direction": "down" if float(r["cur"] or 0) < float(r["mu"] or 0) else "up",
        }
        for r in rows
    ]


async def sku_detail(sku_id: str):
    row = await db.fetchrow(
        """SELECT s.sku_id, s.title, s.category, s.supplier, s.list_price, s.cost,
                  s.cost_known, d.net_revenue, d.gross_margin, d.margin_rate,
                  d.order_count, d.units, d.refund_orders, d.refund_rate,
                  d.ad_spend, d.ad_roi, d.margin_per_order
           FROM mart.sku_summary d JOIN raw.skus s USING (sku_id)
           WHERE sku_id = $1""",
        sku_id,
    )
    return db.jsonable(dict(row)) if row else None
