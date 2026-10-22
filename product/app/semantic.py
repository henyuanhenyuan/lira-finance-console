"""The metric vocabulary, in one place.

Analysis code reads these names; the API serves the same definitions to the
UI. A second copy of "contribution margin" in the client would be a second
definition of it.
"""

from __future__ import annotations

VERSION = "1.0.0"

METRICS: dict[str, dict[str, str]] = {
    "net_revenue": {
        "label": "净收入",
        "description": "买家实付减去退款。",
        "unit": "currency",
    },
    "gross_margin": {
        "label": "贡献毛利",
        "description": "净收入 - 商品成本 - 运费包材 - 平台费 - 广告。",
        "unit": "currency",
    },
    "cost_coverage": {
        "label": "成本覆盖率",
        "description": "有成本记录的收入 / 总收入；低于 100% 时利润为估算。",
        "unit": "ratio",
    },
    "loss_per_order": {
        "label": "每单亏损",
        "description": "贡献毛利 / 订单数；负数表示每单亏钱。",
        "unit": "currency",
    },
    "refund_rate": {
        "label": "退款率",
        "description": "发生退款的订单数 / 订单数。",
        "unit": "ratio",
    },
    "ad_spend": {
        "label": "广告花费",
        "description": "广告表中的花费之和。",
        "unit": "currency",
    },
    "ad_roi": {
        "label": "广告 ROI",
        "description": "广告成交 / 广告花费。",
        "unit": "ratio",
    },
    "order_count": {
        "label": "订单数",
        "description": "去重订单数。",
        "unit": "count",
    },
    "units_sold": {
        "label": "销售件数",
        "description": "订单行数量之和。",
        "unit": "count",
    },
    "aov": {
        "label": "客单价",
        "description": "净收入 / 订单数。",
        "unit": "currency",
    },
}

DIMENSIONS: dict[str, dict[str, str]] = {
    "sku": {"label": "商品", "description": "平台商品 ID。"},
    "category": {"label": "类目", "description": "商品表里的一级类目。"},
    "supplier": {"label": "供应商", "description": "商品表里的供应商。"},
    "date": {"label": "日期", "description": "订单日期。"},
    "month": {"label": "月份", "description": "订单日期所在月份。"},
}


def catalogue() -> dict:
    return {
        "version": VERSION,
        "metrics": [
            {"name": name, **definition} for name, definition in METRICS.items()
        ],
        "dimensions": [
            {"name": name, **definition} for name, definition in DIMENSIONS.items()
        ],
    }
