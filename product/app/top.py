"""Taobao Open Platform: request signing and a thin client.

This module is real code with no bundled credentials. Whether it can reach
Taobao depends on an app key, an app secret and a merchant session; the
product never pretends otherwise. ``time_get`` is the cheapest way to verify
signing once those exist.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_URL = "https://eco.taobao.com/router/rest"


class TopError(RuntimeError):
    """Taobao returned an error, or the request could not be made."""


class TopNotConfigured(TopError):
    """No app key/secret/session, so no request is attempted."""


def sign(params: dict[str, str], secret: str) -> str:
    keys = sorted(params)
    payload = secret + "".join(f"{key}{params[key]}" for key in keys) + secret
    return hashlib.md5(payload.encode("utf-8")).hexdigest().upper()


def _signed_params(
    app_key: str,
    app_secret: str,
    session: str,
    method: str,
    extra: dict[str, Any],
) -> dict[str, str]:
    if not app_key or not app_secret:
        raise TopNotConfigured("缺少 app key / app secret")
    params: dict[str, str] = {
        "method": method,
        "app_key": app_key,
        "session": session,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "2.0",
        "sign_method": "md5",
    }
    params.update({key: str(value) for key, value in extra.items() if value is not None})
    params["sign"] = sign(params, app_secret)
    return params


def _post(params: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        BASE_URL,
        data=urllib.parse.urlencode(params).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise TopError(f"TOP 请求失败：{type(exc).__name__}: {exc}") from exc
    if not isinstance(body, dict):
        raise TopError("TOP 返回的不是 JSON 对象")
    if "error_response" in body:
        error = body["error_response"]
        raise TopError(
            f"TOP 错误 {error.get('code', '?')}: {error.get('msg', '')} "
            f"{error.get('sub_msg', '')}".strip()
        )
    return body


def time_get(app_key: str, app_secret: str, session: str = "") -> dict[str, Any]:
    return _post(_signed_params(app_key, app_secret, session, "taobao.time.get", {}))


class TopClient:
    def __init__(self, app_key: str, app_secret: str, session: str) -> None:
        if not app_key or not app_secret or not session:
            raise TopNotConfigured("缺少 app key / app secret / session")
        self.app_key = app_key
        self.app_secret = app_secret
        self.session = session

    def call(self, method: str, **extra: Any) -> dict[str, Any]:
        return _post(
            _signed_params(self.app_key, self.app_secret, self.session, method, extra)
        )

    def pull_orders(self, start: str, end: str, page_size: int = 100) -> list[dict[str, Any]]:
        """Return canonical order-line rows for a date range.

        The caller decides where to write them; this client never touches the
        warehouse directly.
        """
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            body = self.call(
                "taobao.trades.sold.get",
                fields="tid,status,payment,created,orders",
                start_created=start,
                end_created=end,
                page_no=page,
                page_size=page_size,
            )
            response = body.get("trades_sold_get_response", {})
            trades = response.get("trades", {}).get("trade", [])
            if isinstance(trades, dict):
                trades = [trades]
            for trade in trades:
                order_id = str(trade.get("tid", ""))
                status = str(trade.get("status", ""))
                created = str(trade.get("created", ""))[:10]
                orders = trade.get("orders", {}).get("order", [])
                if isinstance(orders, dict):
                    orders = [orders]
                for line in orders:
                    sku = line.get("outer_iid") or line.get("sku_id") or line.get("num_iid")
                    paid = line.get("total_fee") or line.get("payment") or trade.get("payment")
                    rows.append(
                        {
                            "order_line_id": f"{order_id}-{line.get('oid', '')}",
                            "order_id": order_id,
                            "sku": str(sku or ""),
                            "quantity": int(float(line.get("num", 0) or 0)),
                            "paid_amount": float(paid or 0),
                            "order_date": created,
                            "status": status,
                        }
                    )
            if not response.get("has_next"):
                break
            page += 1
            if page > 100:  # hard bound; a stuck cursor must not loop forever
                raise TopError("TOP 分页超过 100 页，已停止")
        return rows
