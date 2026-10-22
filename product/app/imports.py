"""Order, refund and ad imports, plus the folder inbox scan.

The same rule as the cost upload: a mapping is proposed and shown, never
silently inferred. Explicit uploads replace the dataset; files dropped into
the inbox are upserted by primary key, so a nightly export and an incremental
file can share one table.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from . import costs, db
from .costs import _date, _number, _text, path_for, read_table, save_upload

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "data" / "inbox"

LABELS = {
    "order_line_id": "订单行号",
    "order_id": "订单号",
    "sku": "商品编码",
    "quantity": "数量",
    "paid_amount": "实付金额",
    "order_date": "订单日期",
    "status": "订单状态",
    "refund_id": "退款编号",
    "amount": "退款金额",
    "reason": "退款原因",
    "refund_date": "退款日期",
    "ad_date": "广告日期",
    "campaign": "广告计划",
    "spend": "花费",
    "attributed_revenue": "广告成交",
}

SPECS: dict[str, dict[str, Any]] = {
    "orders": {
        "table": "orders",
        "schema": (
            "order_line_id VARCHAR, order_id VARCHAR, sku VARCHAR,"
            " quantity BIGINT, paid_amount DOUBLE, order_date DATE, status VARCHAR"
        ),
        "required": ("order_line_id", "order_id", "sku", "quantity", "paid_amount", "order_date"),
        "optional": ("status",),
        "columns": (
            "order_line_id", "order_id", "sku", "quantity", "paid_amount", "order_date", "status",
        ),
        "pk": ("order_line_id",),
        "types": {
            "order_line_id": "text",
            "order_id": "text",
            "sku": "text",
            "quantity": "int",
            "paid_amount": "number",
            "order_date": "date",
            "status": "text",
        },
        "defaults": {"status": "已完成"},
        "aliases": {
            "order_line_id": ("子订单编号", "订单行编号", "订单编号", "order_line_id"),
            "order_id": ("订单编号", "订单号", "order_id"),
            "sku": ("商品ID", "平台商品ID", "商家编码", "sku编码", "sku", "商品编码", "宝贝标题"),
            "quantity": ("购买数量", "数量", "quantity"),
            "paid_amount": ("买家实际支付金额", "实付金额(元)", "实付金额", "paid_amount"),
            "order_date": ("订单创建时间", "下单时间", "创建时间", "日期", "order_date"),
            "status": ("订单状态", "状态", "status"),
        },
    },
    "refunds": {
        "table": "refunds",
        "schema": (
            "refund_id VARCHAR, order_line_id VARCHAR, amount DOUBLE,"
            " reason VARCHAR, refund_date DATE"
        ),
        "required": ("refund_id", "order_line_id", "amount", "refund_date"),
        "optional": ("reason",),
        "columns": ("refund_id", "order_line_id", "amount", "reason", "refund_date"),
        "pk": ("refund_id",),
        "types": {
            "refund_id": "text",
            "order_line_id": "text",
            "amount": "number",
            "reason": "text",
            "refund_date": "date",
        },
        "defaults": {"reason": ""},
        "aliases": {
            "refund_id": ("退款编号", "退款单号", "refund_id"),
            "order_line_id": ("子订单编号", "订单行编号", "order_line_id"),
            "amount": ("退款金额(元)", "退款金额", "amount"),
            "reason": ("退款原因", "原因", "reason"),
            "refund_date": ("退款时间", "退款日期", "日期", "refund_date"),
        },
    },
    "ads": {
        "table": "ads",
        "schema": (
            "ad_date DATE, campaign VARCHAR, sku VARCHAR,"
            " spend DOUBLE, attributed_revenue DOUBLE"
        ),
        "required": ("ad_date", "campaign", "sku", "spend", "attributed_revenue"),
        "optional": (),
        "columns": ("ad_date", "campaign", "sku", "spend", "attributed_revenue"),
        "pk": ("ad_date", "campaign", "sku"),
        "types": {
            "ad_date": "date",
            "campaign": "text",
            "sku": "text",
            "spend": "number",
            "attributed_revenue": "number",
        },
        "defaults": {},
        "aliases": {
            "ad_date": ("日期", "花费日期", "ad_date"),
            "campaign": ("计划", "计划名称", "campaign"),
            "sku": ("商品ID", "SKU", "sku", "商家编码", "商品编码"),
            "spend": ("花费", "消耗", "spend"),
            "attributed_revenue": ("成交金额", "广告成交", "attributed_revenue", "成交"),
        },
    },
}


def ensure_inbox() -> None:
    for path in (INBOX, INBOX / "processed", INBOX / "failed"):
        path.mkdir(parents=True, exist_ok=True)


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-（）()：:、/]+", "", text).lower()


def suggest(headers: list[str], aliases: dict[str, tuple[str, ...]]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for target, names in aliases.items():
        found: str | None = None
        for alias in names:
            needle = _norm(alias)
            for header in headers:
                if _norm(header) == needle:
                    found = header
                    break
            if found:
                break
        if found is None:
            for alias in names:
                needle = _norm(alias)
                for header in headers:
                    if needle in _norm(header):
                        found = header
                        break
                if found:
                    break
        result[target] = found
    return result


def _targets(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"key": key, "label": LABELS.get(key, key), "required": key in spec["required"]}
        for key in spec["columns"]
    ]


def preview(dataset: str, upload_id: str, path: Path) -> dict[str, Any]:
    if dataset not in SPECS:
        raise ValueError(f"未知数据类型：{dataset}")
    spec = SPECS[dataset]
    headers, rows = read_table(path)
    return {
        "dataset": dataset,
        "upload_id": upload_id,
        "filename": path.name,
        "headers": headers,
        "row_count": len(rows),
        "preview": [[_text(cell) for cell in row] for row in rows[:5]],
        "suggested": suggest(headers, spec["aliases"]),
        "targets": _targets(spec),
    }


def _convert(value: Any, kind: str) -> Any:
    if kind == "date":
        return _date(value)
    if kind == "number":
        return _number(value)
    if kind == "int":
        number = _number(value)
        return None if number is None else int(number)
    return _text(value)


def apply(
    con: duckdb.DuckDBPyConnection,
    dataset: str,
    path: Path,
    mapping: dict[str, str | None],
    filename: str,
    *,
    replace: bool = True,
) -> dict[str, Any]:
    if dataset not in SPECS:
        raise ValueError(f"未知数据类型：{dataset}")
    spec = SPECS[dataset]
    headers, rows = read_table(path)
    header_set = set(headers)

    columns = list(spec["columns"])
    clean: dict[str, str | None] = {}
    for key in columns:
        source = mapping.get(key)
        if source is not None and source not in header_set:
            raise ValueError(f"映射列 {source!r} 不在文件里")
        clean[key] = source

    missing = [key for key in spec["required"] if not clean[key]]
    if missing:
        raise ValueError("缺少必填映射：" + "、".join(LABELS.get(k, k) for k in missing))

    index = {key: headers.index(source) for key, source in clean.items() if source}
    records: dict[tuple[Any, ...], tuple[Any, ...]] = {}
    errors: list[str] = []
    duplicates = 0

    for row_number, row in enumerate(rows, start=2):
        if not any(_text(cell) for cell in row):
            continue
        values: dict[str, Any] = {}
        failed = False
        for key in columns:
            if key in index:
                values[key] = _convert(row[index[key]], spec["types"][key])
                # A real Taobao export has no product-id column; the merchant's
                # style code lives inside the listing title. Extract it here,
                # and let the required-field check refuse a row that has none.
                if (
                    dataset == "orders"
                    and key == "sku"
                    and clean.get("sku") == "宝贝标题"
                ):
                    match = re.search(r"款\s*([A-Za-z]\d+)", _text(row[index[key]]))
                    values[key] = match.group(1) if match else ""
            else:
                values[key] = spec["defaults"].get(key)

            if key in spec["required"]:
                value = values[key]
                if value is None or value == "":
                    errors.append(f"第 {row_number} 行：{LABELS.get(key, key)} 为空或无法解析")
                    failed = True
                    break
        if failed:
            continue
        key = tuple(values[column] for column in spec["pk"])
        if key in records:
            duplicates += 1
        records[key] = tuple(values[column] for column in columns)

    if not records:
        raise ValueError("没有可导入的行：" + "；".join(errors[:3]))

    placeholders = ", ".join("?" for _ in columns)
    date_column = {"orders": "order_date", "refunds": "refund_date", "ads": "ad_date"}[dataset]
    con.execute("BEGIN")
    try:
        con.execute(f"CREATE TABLE IF NOT EXISTS raw.{spec['table']} ({spec['schema']})")
        con.execute(
            f"CREATE OR REPLACE TEMP TABLE _incoming_import ({spec['schema']})"
        )
        con.executemany(
            f"INSERT INTO _incoming_import VALUES ({placeholders})",
            list(records.values()),
        )

        if replace:
            con.execute(f"DELETE FROM raw.{spec['table']}")
        else:
            key_columns = ", ".join(spec["pk"])
            con.execute(
                f"DELETE FROM raw.{spec['table']} "
                f"WHERE ({key_columns}) IN (SELECT {key_columns} FROM _incoming_import)"
            )

        con.execute(
            f"INSERT INTO raw.{spec['table']} ({', '.join(columns)}) "
            f"SELECT {', '.join(columns)} FROM _incoming_import"
        )
        con.execute("DROP TABLE _incoming_import")
        db.refresh_views(con)

        con.execute(
            "CREATE TABLE IF NOT EXISTS ops.import_log ("
            " imported_at TIMESTAMP, dataset VARCHAR, filename VARCHAR,"
            " imported BIGINT, skipped BIGINT, status VARCHAR, error VARCHAR)"
        )
        con.execute(
            "INSERT INTO ops.import_log SELECT now(), ?, ?, ?, ?, 'ok', NULL",
            [dataset, filename, len(records), len(errors)],
        )
        latest = con.execute(
            f"SELECT max({date_column}) FROM raw.{spec['table']}"
        ).fetchone()[0]
        db.record_dataset(
            con,
            dataset=dataset,
            source=filename,
            rows=len(records),
            latest=str(latest) if latest is not None else "",
            note="replace" if replace else "upsert",
        )
        db.bump_snapshot(con, f"import {dataset}")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    return {
        "dataset": dataset,
        "imported": len(records),
        "skipped": len(errors),
        "duplicates": duplicates,
        "errors": errors[:10],
    }


def _dataset_from_name(name: str) -> str | None:
    lower = name.lower()
    for dataset, prefixes in (
        ("orders", ("orders", "order")),
        ("refunds", ("refunds", "refund")),
        ("ads", ("ads", "ad")),
        ("costs", ("costs", "cost")),
    ):
        if any(lower.startswith(prefix + "_") or lower.startswith(prefix + "-") for prefix in prefixes):
            return dataset
    return None


def scan_inbox(inbox: Path | None = None) -> list[dict[str, Any]]:
    root = inbox or INBOX
    processed = root / "processed"
    failed = root / "failed"
    for path in (root, processed, failed):
        path.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {".csv", ".xlsx", ".xlsm"}:
            continue
        dataset = _dataset_from_name(path.name)
        if dataset is None:
            shutil.move(str(path), str(failed / path.name))
            results.append({"file": path.name, "status": "failed", "error": "无法从文件名判断数据类型"})
            continue

        try:
            headers, _rows = read_table(path)
            if dataset == "costs":
                mapping = costs.suggest_mapping(headers)
                with db.session() as con:
                    result = costs.apply(con, path, mapping, path.name)
            else:
                spec = SPECS[dataset]
                mapping = suggest(headers, spec["aliases"])
                with db.session() as con:
                    result = apply(con, dataset, path, mapping, path.name, replace=False)
            shutil.move(str(path), str(processed / path.name))
            results.append({"file": path.name, "status": "ok", **result})
        except Exception as exc:  # noqa: BLE001 - recorded and moved aside
            shutil.move(str(path), str(failed / path.name))
            with db.session() as con:
                con.execute(
                    "CREATE TABLE IF NOT EXISTS ops.import_log ("
                    " imported_at TIMESTAMP, dataset VARCHAR, filename VARCHAR,"
                    " imported BIGINT, skipped BIGINT, status VARCHAR, error VARCHAR)"
                )
                con.execute(
                    "INSERT INTO ops.import_log SELECT now(), ?, ?, 0, 0, 'failed', ?",
                    [dataset, path.name, str(exc)[:300]],
                )
            results.append({"file": path.name, "status": "failed", "error": str(exc)})
    return results


def status() -> dict[str, Any]:
    ensure_inbox()
    pending = [p.name for p in INBOX.iterdir() if p.is_file()]
    processed = len(list((INBOX / "processed").iterdir()))
    failed = len(list((INBOX / "failed").iterdir()))
    last = None
    with db.session() as con:
        row = con.execute(
            "SELECT imported_at, dataset, filename, imported, skipped, status "
            "FROM ops.import_log ORDER BY imported_at DESC LIMIT 1"
        ).fetchone()
        if row:
            last = {
                "at": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
                "dataset": row[1],
                "filename": row[2],
                "imported": int(row[3]),
                "skipped": int(row[4]),
                "status": row[5],
            }
    return {
        "inbox": str(INBOX),
        "pending": pending,
        "processed": processed,
        "failed": failed,
        "last": last,
    }
