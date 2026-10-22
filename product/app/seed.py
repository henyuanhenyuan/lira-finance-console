"""Deterministic sample data for the local profit diagnosis app.

Same seed, same files, same numbers. A demo whose numbers move between runs is
a demo nobody can review.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample"

START = date(2026, 8, 1)
END = date(2026, 10, 20)

SKUS = [
    {
        "sku": "A001", "title": "纯棉基础短袖", "category": "服饰", "supplier": "S1",
        "price": 59.0, "costs": [(date(2026, 8, 1), 28.0), (date(2026, 9, 15), 32.0)],
        "ship": 4.0, "pack": 1.5, "refund_rate": 0.18, "daily_orders": 2.2,
        "ad_spend": 120.0, "ad_revenue": 70.0, "campaign": "A001-直通车",
    },
    {
        "sku": "A002", "title": "休闲短裤", "category": "服饰", "supplier": "S1",
        "price": 49.0, "costs": [(date(2026, 8, 1), 22.0)],
        "ship": 4.0, "pack": 1.2, "refund_rate": 0.10, "daily_orders": 1.8,
        "ad_spend": 30.0, "ad_revenue": 60.0, "campaign": "A002-直通车",
    },
    {
        "sku": "M212", "title": "连帽卫衣", "category": "服饰", "supplier": "S2",
        "price": 129.0, "costs": [(date(2026, 8, 1), 45.0)],
        "ship": 5.0, "pack": 2.0, "refund_rate": 0.22, "daily_orders": 1.2,
        "ad_spend": 150.0, "ad_revenue": 160.0, "campaign": "计划B",
    },
    {
        "sku": "H310", "title": "保温杯", "category": "家居", "supplier": "S3",
        "price": 39.0, "costs": [(date(2026, 8, 1), 18.0)],
        "ship": 6.0, "pack": 2.5, "refund_rate": 0.05, "daily_orders": 1.5,
        "ad_spend": 10.0, "ad_revenue": 40.0, "campaign": "H310-直通车",
    },
    {
        "sku": "H311", "title": "收纳盒", "category": "家居", "supplier": "S3",
        "price": 29.0, "costs": [(date(2026, 8, 1), 12.0)],
        "ship": 6.0, "pack": 2.0, "refund_rate": 0.06, "daily_orders": 1.0,
        "ad_spend": 0.0, "ad_revenue": 0.0, "campaign": "",
    },
    {
        "sku": "K401", "title": "运动袜", "category": "配饰", "supplier": "S4",
        "price": 19.0, "costs": [(date(2026, 8, 1), 5.0)],
        "ship": 3.0, "pack": 0.8, "refund_rate": 0.03, "daily_orders": 2.0,
        "ad_spend": 8.0, "ad_revenue": 30.0, "campaign": "K401-直通车",
    },
    {
        "sku": "K402", "title": "棒球帽", "category": "配饰", "supplier": "S4",
        "price": 39.0, "costs": [(date(2026, 8, 1), 9.0)],
        "ship": 3.0, "pack": 0.8, "refund_rate": 0.08, "daily_orders": 1.0,
        "ad_spend": 0.0, "ad_revenue": 0.0, "campaign": "",
    },
    {
        # Deliberately has no cost row: the product must say "unknown", not 0.
        "sku": "X999", "title": "新款T恤", "category": "服饰", "supplier": "S5",
        "price": 69.0, "costs": [],
        "ship": 4.0, "pack": 1.5, "refund_rate": 0.12, "daily_orders": 2.5,
        "ad_spend": 30.0, "ad_revenue": 20.0, "campaign": "X999-直通车",
    },
]

FEES = [
    ("服饰", 0.05, 0.006),
    ("家居", 0.05, 0.006),
    ("配饰", 0.05, 0.006),
]

REFUND_REASONS = ["尺码", "质量", "颜色", "物流"]


def ensure_sample(force: bool = False) -> None:
    """Write the sample CSVs once, unless ``force`` asks for a reset."""
    SAMPLE.mkdir(parents=True, exist_ok=True)
    if not force and (SAMPLE / "orders.csv").exists():
        return

    rng = random.Random(42)

    with (
        (SAMPLE / "orders.csv").open("w", newline="", encoding="utf-8") as orders_f,
        (SAMPLE / "refunds.csv").open("w", newline="", encoding="utf-8") as refunds_f,
        (SAMPLE / "ads.csv").open("w", newline="", encoding="utf-8") as ads_f,
        (SAMPLE / "costs.csv").open("w", newline="", encoding="utf-8") as costs_f,
        (SAMPLE / "skus.csv").open("w", newline="", encoding="utf-8") as skus_f,
        (SAMPLE / "fees.csv").open("w", newline="", encoding="utf-8") as fees_f,
    ):
        orders = csv.writer(orders_f)
        refunds = csv.writer(refunds_f)
        ads = csv.writer(ads_f)
        costs = csv.writer(costs_f)
        skus = csv.writer(skus_f)
        fees = csv.writer(fees_f)

        orders.writerow(
            ["order_line_id", "order_id", "sku", "quantity", "paid_amount", "order_date", "status"]
        )
        refunds.writerow(["refund_id", "order_line_id", "amount", "reason", "refund_date"])
        ads.writerow(["ad_date", "campaign", "sku", "spend", "attributed_revenue"])
        costs.writerow(["sku", "effective_from", "unit_cost", "shipping_cost", "packaging_cost"])
        skus.writerow(["sku", "title", "category", "supplier"])
        fees.writerow(["category", "commission_rate", "payment_fee_rate"])

        for item in SKUS:
            skus.writerow([item["sku"], item["title"], item["category"], item["supplier"]])
            for effective_from, unit_cost in item["costs"]:
                costs.writerow(
                    [item["sku"], effective_from.isoformat(), unit_cost, item["ship"], item["pack"]]
                )

        for category, commission, payment in FEES:
            fees.writerow([category, commission, payment])

        day = START
        while day <= END:
            for item in SKUS:
                count = max(0, round(item["daily_orders"] * rng.uniform(0.6, 1.4)))
                for index in range(count):
                    quantity = rng.randint(1, 3)
                    paid = round(item["price"] * quantity * rng.uniform(0.9, 1.0), 2)
                    line_id = f"{day:%Y%m%d}-{item['sku']}-{index}"
                    orders.writerow(
                        [line_id, line_id, item["sku"], quantity, paid, day.isoformat(), "已完成"]
                    )

                    if rng.random() < item["refund_rate"]:
                        amount = round(paid * rng.uniform(0.3, 1.0), 2)
                        refund_day = min(END, day + timedelta(days=rng.randint(1, 10)))
                        refunds.writerow(
                            [
                                f"R-{line_id}",
                                line_id,
                                amount,
                                rng.choice(REFUND_REASONS),
                                refund_day.isoformat(),
                            ]
                        )

                if item["ad_spend"] > 0:
                    spend = round(item["ad_spend"] * rng.uniform(0.8, 1.2), 2)
                    revenue = round(item["ad_revenue"] * rng.uniform(0.8, 1.2), 2)
                    ads.writerow([day.isoformat(), item["campaign"], item["sku"], spend, revenue])

            day += timedelta(days=1)
