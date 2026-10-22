"""Cost-table upload: parse a file, suggest a mapping, apply it.

The mapping is a column-to-column declaration, not an inference that silently
binds whichever header scored best. The suggestions are visible and correctable
before anything is written.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
import uuid
from pathlib import Path
from typing import Any

import duckdb
import openpyxl

from . import db

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT / "data" / "uploads"

_ALLOWED = {".csv", ".xlsx", ".xlsm"}
_REQUIRED = ("sku", "effective_from", "unit_cost")
_OPTIONAL = ("shipping_cost", "packaging_cost")
_TARGETS = _REQUIRED + _OPTIONAL

_ALIASES: dict[str, tuple[str, ...]] = {
    "sku": ("商品编码", "商家编码", "sku编码", "款号", "货号", "商品id", "sku", "编码"),
    "effective_from": (
        "生效日期", "开始日期", "进货日期", "采购日期", "日期", "effective_from", "date",
    ),
    "unit_cost": ("采购单价", "进货单价", "单位成本", "成本单价", "成本", "unit_cost", "cost"),
    "shipping_cost": ("运费", "物流费", "快递费", "shipping_cost", "shipping"),
    "packaging_cost": ("包材", "包装费", "包材费", "packaging_cost", "packaging"),
}


def save_upload(filename: str, data: bytes) -> tuple[str, Path]:
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED:
        raise ValueError("只支持 .csv / .xlsx / .xlsm 文件")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex
    path = UPLOAD_DIR / f"{upload_id}{suffix}"
    path.write_bytes(data)
    return upload_id, path


def path_for(upload_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", upload_id):
        raise ValueError("上传编号不合法")
    matches = list(UPLOAD_DIR.glob(f"{upload_id}.*"))
    if not matches:
        raise FileNotFoundError("找不到这次上传，请重新读取文件")
    return matches[0]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 20_000 <= float(value) <= 80_000:
            return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(value))).date()
        return None
    text = _text(value)
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y%m%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value)
    if not text:
        return None
    for token in ("¥", "￥", ",", "，", "元", " "):
        text = text.replace(token, "")
    try:
        return float(text)
    except ValueError:
        return None


def _read_csv(path: Path) -> list[list[Any]]:
    last: Exception | None = None
    for encoding in ("utf-8-sig", "gbk", "utf-8"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return [list(row) for row in csv.reader(handle)]
        except UnicodeDecodeError as exc:
            last = exc
    raise ValueError("CSV 编码无法识别，请另存为 UTF-8") from last


def _read_xlsx(path: Path) -> list[list[Any]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def read_table(path: Path) -> tuple[list[str], list[list[Any]]]:
    rows = _read_csv(path) if path.suffix.lower() == ".csv" else _read_xlsx(path)
    rows = [row for row in rows if any(_text(cell) for cell in row)]
    if not rows:
        raise ValueError("文件是空的")
    header = [_text(cell) for cell in rows[0]]
    if not any(header):
        raise ValueError("第一行没有列名")

    seen: dict[str, int] = {}
    unique: list[str] = []
    for name in header:
        base = name or "未命名列"
        count = seen.get(base, 0) + 1
        seen[base] = count
        unique.append(base if count == 1 else f"{base}_{count}")

    body: list[list[Any]] = []
    for row in rows[1:]:
        padded = list(row)[: len(unique)]
        padded.extend([None] * (len(unique) - len(padded)))
        body.append(padded)
    return unique, body


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-（）()：:、/]+", "", text).lower()


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    normalized = {header: _norm(header) for header in headers}
    result: dict[str, str | None] = {}
    for target, aliases in _ALIASES.items():
        found: str | None = None
        for alias in aliases:
            needle = _norm(alias)
            for header, normalized_header in normalized.items():
                if normalized_header == needle:
                    found = header
                    break
            if found:
                break
        if found is None:
            for alias in aliases:
                needle = _norm(alias)
                for header, normalized_header in normalized.items():
                    if needle in normalized_header:
                        found = header
                        break
                if found:
                    break
        result[target] = found
    return result


def preview(upload_id: str, path: Path) -> dict[str, Any]:
    headers, rows = read_table(path)
    return {
        "upload_id": upload_id,
        "filename": path.name,
        "headers": headers,
        "row_count": len(rows),
        "preview": [[_text(cell) for cell in row] for row in rows[:5]],
        "suggested": suggest_mapping(headers),
    }


def apply(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    mapping: dict[str, str | None],
    filename: str,
) -> dict[str, Any]:
    headers, rows = read_table(path)
    header_set = set(headers)

    clean: dict[str, str | None] = {}
    for target in _TARGETS:
        source = mapping.get(target)
        if source is not None and source not in header_set:
            raise ValueError(f"映射列 {source!r} 不在文件里")
        clean[target] = source

    missing = [target for target in _REQUIRED if not clean[target]]
    if missing:
        raise ValueError("缺少必填映射：" + "、".join(missing))

    index = {
        target: headers.index(source)
        for target, source in clean.items()
        if source is not None
    }

    incoming: dict[tuple[str, dt.date], tuple[str, dt.date, float, float, float]] = {}
    errors: list[str] = []
    duplicates = 0

    for row_number, row in enumerate(rows, start=2):
        if not any(_text(cell) for cell in row):
            continue
        sku = _text(row[index["sku"]])
        effective = _date(row[index["effective_from"]])
        unit = _number(row[index["unit_cost"]])
        shipping = _number(row[index["shipping_cost"]]) if "shipping_cost" in index else 0.0
        packaging = _number(row[index["packaging_cost"]]) if "packaging_cost" in index else 0.0

        if not sku:
            errors.append(f"第 {row_number} 行：商品编码为空")
            continue
        if effective is None:
            errors.append(f"第 {row_number} 行：生效日期无法解析")
            continue
        if unit is None:
            errors.append(f"第 {row_number} 行：采购单价无法解析")
            continue

        key = (sku, effective)
        if key in incoming:
            duplicates += 1
        incoming[key] = (
            sku,
            effective,
            unit,
            shipping or 0.0,
            packaging or 0.0,
        )

    if not incoming:
        raise ValueError("没有可导入的行：" + "；".join(errors[:3]))

    con.execute("BEGIN")
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS raw.costs ("
            " sku VARCHAR, effective_from DATE, unit_cost DOUBLE,"
            " shipping_cost DOUBLE, packaging_cost DOUBLE)"
        )
        con.execute(
            "CREATE OR REPLACE TEMP TABLE _incoming_costs ("
            " sku VARCHAR, effective_from DATE, unit_cost DOUBLE,"
            " shipping_cost DOUBLE, packaging_cost DOUBLE)"
        )
        con.executemany(
            "INSERT INTO _incoming_costs VALUES (?, ?, ?, ?, ?)",
            list(incoming.values()),
        )
        con.execute(
            "DELETE FROM raw.costs WHERE sku IN (SELECT DISTINCT sku FROM _incoming_costs)"
        )
        con.execute(
            "INSERT INTO raw.costs (sku, effective_from, unit_cost, shipping_cost, packaging_cost) "
            "SELECT sku, effective_from, unit_cost, shipping_cost, packaging_cost FROM _incoming_costs"
        )
        con.execute("DROP TABLE _incoming_costs")

        con.execute(
            "CREATE TABLE IF NOT EXISTS ops.cost_import ("
            " imported_at TIMESTAMP, filename VARCHAR, imported BIGINT, skipped BIGINT)"
        )
        con.execute(
            "INSERT INTO ops.cost_import SELECT now(), ?, ?, ?",
            [filename, len(incoming), len(errors)],
        )
        latest = con.execute("SELECT max(effective_from) FROM raw.costs").fetchone()[0]
        db.record_dataset(
            con,
            dataset="costs",
            source=filename,
            rows=len(incoming),
            latest=str(latest) if latest is not None else "",
            note="upsert",
        )
        db.bump_snapshot(con, "import costs")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    return {
        "imported": len(incoming),
        "skipped": len(errors),
        "duplicates": duplicates,
        "errors": errors[:10],
    }


def template(con: duckdb.DuckDBPyConnection) -> str:
    rows = con.execute("SELECT sku FROM raw.skus ORDER BY sku").fetchall()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["商品编码", "生效日期", "采购单价", "运费", "包材", "备注"])
    for (sku,) in rows:
        writer.writerow([sku, "2026-10-01", "", "", "", "按需填写"])
    return "﻿" + buffer.getvalue()
