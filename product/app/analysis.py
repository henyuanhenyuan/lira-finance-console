"""Profit analysis over the published warehouse.

Every number here comes from DuckDB. The UI never computes a business figure.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import duckdb

from . import db, semantic

SKU_SQL = """
WITH line_agg AS (
    SELECT
        sku,
        any_value(title) AS title,
        any_value(category) AS category,
        any_value(supplier) AS supplier,
        any_value(merchant_sku) AS merchant_sku,
        SUM(paid_amount) AS paid,
        SUM(refund_amount) AS refunds,
        SUM(net_revenue) AS net_revenue,
        SUM(goods_cost) AS goods_cost,
        SUM(fulfillment_cost) AS fulfillment_cost,
        SUM(platform_fee) AS platform_fee,
        COUNT(DISTINCT order_id) AS orders,
        COUNT(DISTINCT CASE WHEN refund_amount > 0 THEN order_id END) AS refund_orders,
        SUM(quantity) AS units,
        SUM(CASE WHEN goods_cost IS NULL THEN net_revenue ELSE 0 END) AS unknown_revenue
    FROM lake.lines
    WHERE order_date BETWEEN ? AND ?
    GROUP BY sku
),
ad AS (
    SELECT sku,
           SUM(spend) AS ad_spend,
           SUM(attributed_revenue) AS ad_revenue
    FROM lake.ad_lines
    WHERE ad_date BETWEEN ? AND ?
    GROUP BY sku
)
SELECT
    l.sku,
    l.title,
    l.category,
    l.supplier,
    l.merchant_sku,
    l.paid,
    l.refunds,
    l.net_revenue,
    l.goods_cost,
    l.fulfillment_cost,
    l.platform_fee,
    l.orders,
    l.units,
    COALESCE(a.ad_spend, 0) AS ad_spend,
    COALESCE(a.ad_revenue, 0) AS ad_revenue,
    CASE WHEN l.orders > 0
         THEN CAST(l.refund_orders AS DOUBLE) / l.orders
         ELSE NULL END AS refund_rate,
    CASE WHEN l.net_revenue > 0
         THEN (l.net_revenue - l.unknown_revenue) / l.net_revenue
         ELSE NULL END AS cost_coverage,
    CASE WHEN l.goods_cost IS NULL THEN NULL
         ELSE l.net_revenue - l.goods_cost - l.fulfillment_cost - l.platform_fee
              - COALESCE(a.ad_spend, 0)
    END AS contribution_margin,
    CASE WHEN l.goods_cost IS NULL THEN NULL
         ELSE l.net_revenue - l.goods_cost - l.fulfillment_cost - l.platform_fee
    END AS pre_ad_profit,
    CASE WHEN l.orders > 0 AND l.goods_cost IS NOT NULL
         THEN (l.net_revenue - l.goods_cost - l.fulfillment_cost - l.platform_fee
               - COALESCE(a.ad_spend, 0)) / l.orders
         ELSE NULL
    END AS loss_per_order
FROM line_agg l
LEFT JOIN ad a ON a.sku = l.sku
ORDER BY contribution_margin ASC NULLS LAST
"""

AD_SQL = """
SELECT sku, campaign, SUM(spend) AS spend, SUM(attributed_revenue) AS attributed_revenue
FROM lake.ad_lines
WHERE ad_date BETWEEN ? AND ?
GROUP BY sku, campaign
ORDER BY spend DESC
"""


def _f(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _period(
    con: duckdb.DuckDBPyConnection,
    start: dt.date | None,
    end: dt.date | None,
) -> tuple[dt.date, dt.date]:
    if start is not None and end is not None:
        if start > end:
            raise ValueError("start must be <= end")
        return start, end

    latest = con.execute("SELECT max(order_date) FROM raw.orders").fetchone()[0]
    if latest is None:
        today = dt.date.today()
        return start or today, end or today

    resolved_end = end or latest
    resolved_start = start or (resolved_end - dt.timedelta(days=29))
    if resolved_start > resolved_end:
        raise ValueError("start must be <= end")
    return resolved_start, resolved_end


def _sku_rows(
    con: duckdb.DuckDBPyConnection, start: dt.date, end: dt.date
) -> list[dict[str, Any]]:
    cursor = con.execute(SKU_SQL, [start, end, start, end])
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _freshness(con: duckdb.DuckDBPyConnection) -> dict[str, str | None]:
    def one(sql: str) -> str | None:
        value = con.execute(sql).fetchone()[0]
        return value.isoformat() if hasattr(value, "isoformat") else value

    return {
        "orders": one("SELECT max(order_date) FROM raw.orders"),
        "refunds": one("SELECT max(refund_date) FROM raw.refunds"),
        "ads": one("SELECT max(ad_date) FROM raw.ads"),
        "costs": one("SELECT max(effective_from) FROM raw.costs"),
    }


def _action(
    kind: str, ident: str, title: str, reason: str, impact: float, confidence: str
) -> dict[str, Any]:
    return {
        "id": ident,
        "kind": kind,
        "title": title,
        "reason": reason,
        "impact": round(float(impact), 2),
        "confidence": confidence,
    }


def _previous_window(start: dt.date, end: dt.date) -> tuple[dt.date, dt.date]:
    span = (end - start).days + 1
    previous_end = start - dt.timedelta(days=1)
    return previous_end - dt.timedelta(days=span - 1), previous_end


def _totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    known = [row for row in rows if row["contribution_margin"] is not None]
    total_net = sum(float(row["net_revenue"] or 0) for row in rows)
    known_net = sum(float(row["net_revenue"] or 0) for row in known)
    orders = sum(float(row["orders"] or 0) for row in known)
    units = sum(float(row["units"] or 0) for row in known)
    contribution = sum(float(row["contribution_margin"] or 0) for row in known)
    return {
        "net_revenue": total_net,
        "known_net_revenue": known_net,
        "coverage": known_net / total_net if total_net > 0 else None,
        "orders": orders,
        "units": units,
        "aov": known_net / orders if orders > 0 else None,
        "contribution": contribution,
    }


def _comparison(
    name: str, label: str, current: Any, previous: Any, unit: str = "currency"
) -> dict[str, Any]:
    change = None
    if current is not None and previous not in (None, 0):
        change = (float(current) - float(previous)) / abs(float(previous))
    return {
        "metric": name,
        "label": label,
        "current": _f(current),
        "previous": _f(previous),
        "change": _f(change),
        "comparable": change is not None,
        "unit": unit,
    }


def category_breakdown(
    con: duckdb.DuckDBPyConnection, start: dt.date, end: dt.date
) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT COALESCE(category, '（未分类）') AS category,
               SUM(net_revenue) AS net_revenue,
               SUM(CASE WHEN goods_cost IS NULL THEN NULL
                        ELSE net_revenue - goods_cost - fulfillment_cost - platform_fee END) AS line_margin,
               COUNT(DISTINCT order_id) AS orders
        FROM lake.lines
        WHERE order_date BETWEEN ? AND ?
        GROUP BY 1
        ORDER BY 2 DESC
        """,
        [start, end],
    ).fetchall()
    ad_rows = con.execute(
        """
        SELECT COALESCE(s.category, '（未分类）') AS category, SUM(a.spend) AS ad_spend
        FROM raw.ads AS a
        LEFT JOIN raw.skus AS s ON s.sku = a.sku
        WHERE a.ad_date BETWEEN ? AND ?
        GROUP BY 1
        """,
        [start, end],
    ).fetchall()
    ads = {row[0]: float(row[1] or 0) for row in ad_rows}
    total = sum(float(row[1] or 0) for row in rows)
    result: list[dict[str, Any]] = []
    for category, net_revenue, line_margin, orders in rows:
        ad = ads.get(category, 0.0)
        contribution = None if line_margin is None else float(line_margin) - ad
        result.append(
            {
                "category": category,
                "net_revenue": _f(net_revenue),
                "contribution_margin": _f(contribution),
                "orders": int(orders or 0),
                "share": _f(float(net_revenue or 0) / total if total > 0 else None),
            }
        )
    return result


def trend(
    con: duckdb.DuckDBPyConnection,
    start: dt.date,
    end: dt.date,
    granularity: str = "day",
) -> dict[str, Any]:
    if granularity not in {"day", "month"}:
        raise ValueError("granularity must be day or month")
    line_expr = "order_date" if granularity == "day" else "date_trunc('month', order_date)"
    ad_expr = "ad_date" if granularity == "day" else "date_trunc('month', ad_date)"
    line_rows = con.execute(
        f"""
        SELECT {line_expr} AS bucket,
               SUM(net_revenue) AS net_revenue,
               SUM(CASE WHEN goods_cost IS NULL THEN NULL
                        ELSE net_revenue - goods_cost - fulfillment_cost - platform_fee END) AS line_margin
        FROM lake.lines
        WHERE order_date BETWEEN ? AND ?
        GROUP BY 1
        ORDER BY 1
        """,
        [start, end],
    ).fetchall()
    ad_rows = con.execute(
        f"""
        SELECT {ad_expr} AS bucket, SUM(spend) AS ad_spend
        FROM raw.ads
        WHERE ad_date BETWEEN ? AND ?
        GROUP BY 1
        """,
        [start, end],
    ).fetchall()

    width = 10 if granularity == "day" else 7
    lines = {str(row[0])[:width]: (float(row[1] or 0), row[2]) for row in line_rows}
    ads = {str(row[0])[:width]: float(row[1] or 0) for row in ad_rows}
    buckets = sorted(set(lines) | set(ads))
    rows: list[dict[str, Any]] = []
    for bucket in buckets:
        net, line_margin = lines.get(bucket, (0.0, None))
        ad = ads.get(bucket, 0.0)
        contribution = None if line_margin is None else float(line_margin) - ad
        rows.append(
            {
                "bucket": bucket,
                "net_revenue": round(net, 2),
                "contribution_margin": _f(contribution),
            }
        )
    return {
        "granularity": granularity,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "snapshot_id": db.snapshot_id(con),
        "metric_version": semantic.VERSION,
        "rows": rows,
    }


def overview(
    con: duckdb.DuckDBPyConnection,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> dict[str, Any]:
    start, end = _period(con, start, end)
    rows = _sku_rows(con, start, end)
    known = [row for row in rows if row["contribution_margin"] is not None]

    total_net = sum(float(row["net_revenue"] or 0) for row in rows)
    known_net = sum(float(row["net_revenue"] or 0) for row in known)
    coverage = known_net / total_net if total_net > 0 else None

    previous_start, previous_end = _previous_window(start, end)
    current_totals = _totals(rows)
    previous_totals = _totals(_sku_rows(con, previous_start, previous_end))

    paid = sum(float(row["paid"] or 0) for row in known)
    refunds = sum(float(row["refunds"] or 0) for row in known)
    goods = sum(float(row["goods_cost"] or 0) for row in known)
    fulfillment = sum(float(row["fulfillment_cost"] or 0) for row in known)
    platform = sum(float(row["platform_fee"] or 0) for row in known)
    ad = sum(float(row["ad_spend"] or 0) for row in known)
    contribution = sum(float(row["contribution_margin"] or 0) for row in known)

    losses = [
        row
        for row in known
        if float(row["contribution_margin"] or 0) < 0 and float(row["net_revenue"] or 0) > 0
    ]
    losses.sort(key=lambda row: float(row["contribution_margin"]))

    waste = ad_waste(con, start, end)
    confidence = "高" if coverage is not None and coverage >= 0.95 else "中"

    actions: list[dict[str, Any]] = []
    if losses:
        top = losses[0]
        actions.append(
            _action(
                "loss",
                f"loss:{top['sku']}",
                f"{top['sku']} {top['title']} 每单亏 ¥{abs(float(top['loss_per_order'] or 0)):.2f}",
                f"贡献毛利 ¥{float(top['contribution_margin']):.2f}，"
                f"退款率 {float(top['refund_rate'] or 0):.1%}，"
                f"广告 ¥{float(top['ad_spend'] or 0):.2f}",
                abs(float(top["contribution_margin"])),
                confidence,
            )
        )

    loss_sku = losses[0]["sku"] if losses else None
    for item in waste["items"]:
        if loss_sku is not None and item["sku"] == loss_sku:
            continue
        actions.append(
            _action(
                "ad",
                f"ad:{item['campaign']}",
                f"{item['campaign']} 近一期多花 ¥{item['waste']:.2f}",
                f"ROI {item['roi']:.2f}"
                if item["roi"] is not None
                else "广告成交不足",
                item["waste"],
                "中",
            )
        )
        break

    refund_candidates = [
        row
        for row in known
        if row["refund_rate"] is not None and float(row["net_revenue"] or 0) > 0
    ]
    refund_candidates.sort(key=lambda row: float(row["refund_rate"] or 0), reverse=True)
    if refund_candidates:
        top = refund_candidates[0]
        actions.append(
            _action(
                "refund",
                f"refund:{top['sku']}",
                f"{top['sku']} 退款率 {float(top['refund_rate'] or 0):.1%}",
                f"退款 ¥{float(top['refunds'] or 0):.2f}，类目 {top['category']}",
                float(top["refunds"] or 0),
                "中",
            )
        )

    missing = [row["sku"] for row in rows if row["contribution_margin"] is None]
    warnings: list[str] = []
    if coverage is not None and coverage < 0.8:
        warnings.append(f"成本覆盖 {coverage:.0%}：利润为已知成本部分的估算。")
    if missing:
        warnings.append(f"{'、'.join(missing)} 缺少成本记录，未计入利润。")

    if len(actions) < 3 and coverage is not None and coverage < 0.8:
        actions.append(
            _action(
                "data",
                "data:coverage",
                f"成本覆盖 {coverage:.0%}",
                "补齐成本表后，亏损判断才会完整。",
                0.0,
                "高",
            )
        )

    comparisons = [
        _comparison(
            "net_revenue", "净收入",
            current_totals["net_revenue"], previous_totals["net_revenue"],
        ),
        _comparison(
            "contribution_margin", "贡献毛利",
            current_totals["contribution"], previous_totals["contribution"],
        ),
        _comparison(
            "order_count", "订单数",
            current_totals["orders"], previous_totals["orders"], unit="count",
        ),
        _comparison(
            "aov", "客单价",
            current_totals["aov"], previous_totals["aov"],
        ),
    ]
    anomalies = [
        {
            "metric": item["metric"],
            "label": item["label"],
            "current": item["current"],
            "previous": item["previous"],
            "change": item["change"],
            "direction": "上升" if float(item["change"]) >= 0 else "下降",
        }
        for item in comparisons
        if item["comparable"] and item["change"] is not None and abs(float(item["change"])) >= 0.2
    ]
    snapshot = db.snapshot_id(con)
    freshness = _freshness(con)

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "previous_period": {
            "start": previous_start.isoformat(),
            "end": previous_end.isoformat(),
        },
        "snapshot_id": snapshot,
        "metric_version": semantic.VERSION,
        "net_revenue": _f(total_net),
        "known_net_revenue": _f(known_net),
        "contribution_margin": _f(contribution),
        "cost_coverage": _f(coverage),
        "order_count": int(round(current_totals["orders"])),
        "units_sold": int(round(current_totals["units"])),
        "aov": _f(current_totals["aov"]),
        "loss_sku_count": len(losses),
        "ad_waste_total": waste["total_waste"],
        "comparisons": comparisons,
        "anomalies": anomalies,
        "categories": category_breakdown(con, start, end)[:6],
        "profit_bridge": [
            {"label": "买家实付", "value": _f(paid)},
            {"label": "退款", "value": _f(-refunds)},
            {"label": "商品成本", "value": _f(-goods)},
            {"label": "运费/包材", "value": _f(-fulfillment)},
            {"label": "平台费用", "value": _f(-platform)},
            {"label": "广告", "value": _f(-ad)},
            {"label": "贡献毛利", "value": _f(contribution)},
        ],
        "actions": actions[:3],
        "warnings": warnings,
        "freshness": freshness,
        "evidence": {
            "snapshot_id": snapshot,
            "metric_version": semantic.VERSION,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "coverage": _f(coverage),
            "freshness": freshness,
        },
        "sample": True,
    }


def _loss_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku": row["sku"],
        "title": row["title"],
        "category": row["category"],
        "supplier": row["supplier"],
        "merchant_sku": row["merchant_sku"],
        "net_revenue": _f(row["net_revenue"]),
        "refund_rate": _f(row["refund_rate"]),
        "cost_coverage": _f(row["cost_coverage"]),
        "contribution_margin": _f(row["contribution_margin"]),
        "loss_per_order": _f(row["loss_per_order"]),
        "ad_spend": _f(row["ad_spend"]),
    }


def loss_skus(
    con: duckdb.DuckDBPyConnection,
    start: dt.date | None = None,
    end: dt.date | None = None,
    min_loss: float = 0.0,
) -> dict[str, Any]:
    start, end = _period(con, start, end)
    rows = _sku_rows(con, start, end)
    items = [
        row
        for row in rows
        if row["contribution_margin"] is not None
        and float(row["contribution_margin"]) < -abs(min_loss)
        and float(row["net_revenue"] or 0) > 0
    ]
    items.sort(key=lambda row: float(row["contribution_margin"]))
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "snapshot_id": db.snapshot_id(con),
        "metric_version": semantic.VERSION,
        "items": [_loss_item(row) for row in items],
    }


def ad_waste(
    con: duckdb.DuckDBPyConnection,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> dict[str, Any]:
    start, end = _period(con, start, end)
    sku_rows = {row["sku"]: row for row in _sku_rows(con, start, end)}

    cursor = con.execute(AD_SQL, [start, end])
    columns = [item[0] for item in cursor.description]
    ads = [dict(zip(columns, row)) for row in cursor.fetchall()]

    total_by_sku: dict[str, float] = {}
    for row in ads:
        total_by_sku[row["sku"]] = total_by_sku.get(row["sku"], 0.0) + float(row["spend"] or 0)

    items: list[dict[str, Any]] = []
    for row in ads:
        sku = row["sku"]
        metric = sku_rows.get(sku)
        if metric is None or metric["contribution_margin"] is None:
            continue

        spend = float(row["spend"] or 0)
        attributed = float(row["attributed_revenue"] or 0)
        if spend <= 0:
            continue

        pre_ad_profit = float(metric["pre_ad_profit"] or 0)
        total_spend = total_by_sku.get(sku, 0.0)
        allocated = (
            max(0.0, pre_ad_profit) * (spend / total_spend) if total_spend > 0 else 0.0
        )
        waste = max(0.0, spend - allocated)
        if waste <= 0.01:
            continue

        roi = attributed / spend if spend > 0 else None
        breakeven = attributed / allocated if allocated > 0 else None
        if pre_ad_profit <= 0:
            suggestion = "广告前已亏损，建议暂停"
        elif roi is not None and breakeven is not None and roi < breakeven * 0.6:
            suggestion = "暂停"
        else:
            suggestion = "降价/换词/换素材"

        items.append(
            {
                "sku": sku,
                "title": metric["title"],
                "campaign": row["campaign"],
                "spend": round(spend, 2),
                "attributed_revenue": round(attributed, 2),
                "roi": round(roi, 2) if roi is not None else None,
                "breakeven_roi": round(breakeven, 2) if breakeven is not None else None,
                "waste": round(waste, 2),
                "suggestion": suggestion,
            }
        )

    items.sort(key=lambda item: item["waste"], reverse=True)
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "snapshot_id": db.snapshot_id(con),
        "metric_version": semantic.VERSION,
        "total_waste": round(sum(item["waste"] for item in items), 2),
        "items": items,
    }


def sku_detail(
    con: duckdb.DuckDBPyConnection,
    sku: str,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> dict[str, Any] | None:
    start, end = _period(con, start, end)
    rows = _sku_rows(con, start, end)
    metric = next((row for row in rows if row["sku"] == sku), None)
    if metric is None:
        return None

    contribution = float(metric["contribution_margin"] or 0)
    confidence = (
        "高"
        if metric["cost_coverage"] is not None and float(metric["cost_coverage"]) >= 0.95
        else "中"
    )

    actions: list[dict[str, Any]] = []
    if metric["contribution_margin"] is not None and contribution < 0:
        actions.append(
            _action(
                "loss",
                f"loss:{sku}",
                f"每单亏 ¥{abs(float(metric['loss_per_order'] or 0)):.2f}",
                f"贡献毛利 ¥{contribution:.2f}，"
                f"退款率 {float(metric['refund_rate'] or 0):.1%}，"
                f"广告 ¥{float(metric['ad_spend'] or 0):.2f}",
                abs(contribution),
                confidence,
            )
        )
    if float(metric["ad_spend"] or 0) > 0:
        actions.append(
            _action(
                "ad",
                f"ad:{sku}",
                "暂停广告做一次小测试",
                f"广告花费 ¥{float(metric['ad_spend'] or 0):.2f}，先看停投后的销量变化。",
                float(metric["ad_spend"] or 0),
                "中",
            )
        )
    if metric["refund_rate"] is not None and float(metric["refund_rate"]) > 0.15:
        actions.append(
            _action(
                "refund",
                f"refund:{sku}",
                "检查退货原因",
                f"退款率 {float(metric['refund_rate']):.1%}，先看尺码/质量问题。",
                float(metric["refunds"] or 0),
                "中",
            )
        )

    paid = float(metric["paid"] or 0)
    refunds = float(metric["refunds"] or 0)
    goods = float(metric["goods_cost"] or 0)
    fulfillment = float(metric["fulfillment_cost"] or 0)
    platform = float(metric["platform_fee"] or 0)
    ad = float(metric["ad_spend"] or 0)

    orders = con.execute(
        "SELECT count(*) FROM raw.orders WHERE sku = ? AND order_date BETWEEN ? AND ?",
        [sku, start, end],
    ).fetchone()[0]
    refund_count = con.execute(
        "SELECT count(*) FROM raw.refunds r "
        "JOIN raw.orders o ON o.order_line_id = r.order_line_id "
        "WHERE o.sku = ? AND o.order_date BETWEEN ? AND ?",
        [sku, start, end],
    ).fetchone()[0]
    ad_count = con.execute(
        "SELECT count(*) FROM raw.ads WHERE sku = ? AND ad_date BETWEEN ? AND ?",
        [sku, start, end],
    ).fetchone()[0]
    cost_count = con.execute("SELECT count(*) FROM raw.costs WHERE sku = ?", [sku]).fetchone()[0]

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "snapshot_id": db.snapshot_id(con),
        "metric_version": semantic.VERSION,
        "sku": sku,
        "title": metric["title"],
        "category": metric["category"],
        "supplier": metric["supplier"],
        "merchant_sku": metric["merchant_sku"],
        "net_revenue": _f(metric["net_revenue"]),
        "refund_rate": _f(metric["refund_rate"]),
        "cost_coverage": _f(metric["cost_coverage"]),
        "contribution_margin": _f(metric["contribution_margin"]),
        "loss_per_order": _f(metric["loss_per_order"]),
        "ad_spend": _f(ad),
        "profit_bridge": [
            {"label": "买家实付", "value": _f(paid)},
            {"label": "退款", "value": _f(-refunds)},
            {"label": "商品成本", "value": _f(-goods)},
            {"label": "运费/包材", "value": _f(-fulfillment)},
            {"label": "平台费用", "value": _f(-platform)},
            {"label": "广告", "value": _f(-ad)},
            {"label": "贡献毛利", "value": _f(contribution)},
        ],
        "actions": actions,
        "evidence": {
            "orders": int(orders),
            "refunds": int(refund_count),
            "ads": int(ad_count),
            "costs": int(cost_count),
        },
    }


def data_health(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    start, end = _period(con, None, None)
    rows = _sku_rows(con, start, end)

    total_net = sum(float(row["net_revenue"] or 0) for row in rows)
    known_net = sum(
        float(row["net_revenue"] or 0)
        for row in rows
        if row["contribution_margin"] is not None
    )
    coverage = known_net / total_net if total_net > 0 else None
    missing = [row["sku"] for row in rows if row["contribution_margin"] is None]

    def source(name: str, table: str, column: str) -> dict[str, Any]:
        latest, count = con.execute(
            f"SELECT max({column}), count(*) FROM {table}"
        ).fetchone()
        return {
            "name": name,
            "latest": latest.isoformat() if hasattr(latest, "isoformat") else latest,
            "rows": int(count),
            "status": "ok" if count else "empty",
        }

    last = con.execute("SELECT max(synced_at) FROM ops.sync_run").fetchone()[0]

    warnings: list[str] = []
    if coverage is not None and coverage < 0.8:
        warnings.append(f"成本覆盖 {coverage:.0%}，利润为估算。")
    if missing:
        warnings.append(f"缺少成本：{'、'.join(missing)}。")

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "snapshot_id": db.snapshot_id(con),
        "metric_version": semantic.VERSION,
        "coverage": _f(coverage),
        "missing_skus": missing,
        "sources": [
            source("订单", "raw.orders", "order_date"),
            source("退款", "raw.refunds", "refund_date"),
            source("广告", "raw.ads", "ad_date"),
            source("成本", "raw.costs", "effective_from"),
        ],
        "last_sync": last.isoformat() if hasattr(last, "isoformat") else last,
        "warnings": warnings,
        "sample": True,
    }
