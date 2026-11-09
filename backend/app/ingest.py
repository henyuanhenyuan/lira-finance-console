"""订单行接入：把外部数据源的行写入 raw，并回填平台费。

只做幂等 upsert，不删除既有数据。
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any

from . import db

REQUIRED = ("order_id", "sku_id", "buyer_id", "ordered_at", "qty", "paid")


class IngestError(Exception):
    pass


def _parse_row(raw: dict[str, Any]) -> tuple:
    for key in REQUIRED:
        if key not in raw or str(raw[key]).strip() == "":
            raise IngestError(f"缺少必填字段: {key}")
    try:
        ordered_at = dt.date.fromisoformat(str(raw["ordered_at"])[:10])
    except ValueError as exc:
        raise IngestError(f"日期格式错误: {raw['ordered_at']}") from exc
    try:
        qty = int(raw["qty"])
        paid = Decimal(str(raw["paid"]))
    except (ValueError, InvalidOperation) as exc:
        raise IngestError("qty / paid 必须是数字") from exc
    if qty <= 0 or paid < 0:
        raise IngestError("qty 必须为正、paid 不能为负")
    return (
        str(raw["order_id"]).strip(),
        str(raw["sku_id"]).strip(),
        str(raw["buyer_id"]).strip(),
        ordered_at,
        qty,
        paid,
        str(raw.get("channel") or "导入").strip()[:32],
    )


async def ingest_orders(rows: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    """写入订单。返回新增/更新/拒绝统计。"""
    if not rows:
        raise IngestError("没有可导入的数据行")
    if len(rows) > 20000:
        raise IngestError("单次最多 20000 行")

    known = {r["sku_id"] for r in await db.fetch("SELECT sku_id FROM raw.skus")}
    accepted: list[tuple] = []
    rejected: list[dict[str, str]] = []

    for i, raw in enumerate(rows):
        try:
            parsed = _parse_row(raw)
        except IngestError as exc:
            rejected.append({"row": str(i + 2), "reason": str(exc)})
            continue
        if parsed[1] not in known:
            rejected.append({"row": str(i + 2), "reason": f"未知 SKU: {parsed[1]}"})
            continue
        accepted.append(parsed)

    if not accepted:
        reasons = "；".join(f"第{r['row']}行 {r['reason']}" for r in rejected[:3])
        raise IngestError(f"所有行都被拒绝：{reasons}")

    fees = [(r[0], round(float(r[5]) * 0.05, 2), round(float(r[5]) * 0.006, 2)) for r in accepted]

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            before = await conn.fetchval("SELECT COUNT(*) FROM raw.orders")
            await conn.executemany(
                """INSERT INTO raw.orders(order_id,sku_id,buyer_id,ordered_at,qty,paid,channel)
                   VALUES($1,$2,$3,$4,$5,$6,$7)
                   ON CONFLICT (order_id) DO UPDATE
                   SET qty=EXCLUDED.qty, paid=EXCLUDED.paid, channel=EXCLUDED.channel""",
                accepted,
            )
            await conn.executemany(
                """INSERT INTO raw.platform_fees(order_id,commission,tech_fee)
                   VALUES($1,$2,$3)
                   ON CONFLICT (order_id) DO UPDATE
                   SET commission=EXCLUDED.commission, tech_fee=EXCLUDED.tech_fee""",
                fees,
            )
            after = await conn.fetchval("SELECT COUNT(*) FROM raw.orders")

    await db.refresh_marts()

    return {
        "source": source,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "inserted": int(after) - int(before),
        "updated": len(accepted) - (int(after) - int(before)),
        "rejected_rows": rejected[:20],
    }
