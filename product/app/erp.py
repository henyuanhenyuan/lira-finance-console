"""Generic ERP HTTP boundary.

Vendors differ, so this adapter deliberately defines a small contract:
``GET /health`` and ``GET /orders?start=&end=`` returning either a list or
``{"orders": [...]}``. A vendor adapter can wrap or replace it without
touching the warehouse.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class ErpError(RuntimeError):
    pass


class ErpNotConfigured(ErpError):
    pass


class ErpClient:
    def __init__(self, base_url: str, token: str, timeout: float = 15.0) -> None:
        if not base_url or not token:
            raise ErpNotConfigured("缺少 ERP 地址 / token")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise ErpError(f"ERP 请求失败：{type(exc).__name__}: {exc}") from exc
        return body

    def ping(self) -> Any:
        return self._get("/health")

    def pull_orders(self, start: str, end: str) -> list[dict[str, Any]]:
        payload = self._get("/orders", {"start": start, "end": end})
        items = payload.get("orders", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ErpError("ERP /orders 没有返回列表")
        rows: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "order_line_id": str(item.get("order_line_id") or item.get("id") or ""),
                    "order_id": str(item.get("order_id") or item.get("order") or ""),
                    "sku": str(item.get("sku") or item.get("product_code") or ""),
                    "quantity": int(float(item.get("quantity") or item.get("qty") or 0)),
                    "paid_amount": float(item.get("paid_amount") or item.get("paid") or 0),
                    "order_date": str(item.get("order_date") or item.get("date") or "")[:10],
                    "status": str(item.get("status") or "已完成"),
                }
            )
        return rows
