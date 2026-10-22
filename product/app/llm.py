"""Local-model explanation with a deterministic fallback.

The model is a writer, not an analyst. It receives figures the engine already
computed and is constrained to a JSON object with prose and actions. The prose
is forbidden to contain numbers; the template already carries them. If the
model cannot produce a clean object, the template is the answer.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import duckdb

from . import analysis

OLLAMA_URL = os.environ.get("LIRA_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("LIRA_MODEL", "qwen3:4b")
TIMEOUT = float(os.environ.get("LIRA_MODEL_TIMEOUT", "12"))

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "data" / "logs"

_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")

_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "actions"],
}

_SYSTEM = (
    "你是电商利润诊断助手。只输出 JSON，不要输出思考过程。"
    "answer 是 2 到 3 句中文解释；actions 是 1 到 3 条中文行动建议。"
    "不要写任何数字、百分比、日期或金额，也不要复述数据；数字由界面单独展示。"
    "如果成本覆盖不足，要在 answer 里明确说这是估算。"
)


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{digits}f}"


def _pct(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def _log(message: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "llm.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{dt.datetime.now(dt.UTC).isoformat()} {message}\n")
    except OSError:
        pass


def status() -> dict[str, Any]:
    available = False
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=1) as response:
            available = response.status == 200
    except Exception:  # noqa: BLE001 - status is a report, not a request
        available = False
    return {"url": OLLAMA_URL, "model": MODEL, "available": available}


def _allowed(data: Any) -> set[str]:
    allowed: set[str] = set()

    def offer(value: float) -> None:
        for places in (0, 1, 2):
            rendered = f"{value:.{places}f}"
            allowed.add(rendered)
            allowed.add(rendered.replace("-", ""))
        if 0 < abs(value) < 1:
            for places in (0, 1, 2):
                allowed.add(f"{value * 100:.{places}f}")

    def walk(node: Any) -> None:
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, (int, float)):
            offer(float(node))
        elif isinstance(node, str):
            for token in _NUM.findall(node):
                allowed.add(token)
                allowed.add(token.replace("-", ""))
                try:
                    offer(float(token.replace(",", "")))
                except ValueError:
                    pass
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    walk(data)
    return allowed


def _grounded(text: str, data: Any) -> bool:
    allowed = _allowed(data)
    return all(token in allowed for token in _NUM.findall(text))


def _chat(system: str, user: str) -> tuple[dict[str, Any] | None, str]:
    # One cheap probe before the long call: a missing local runtime should
    # fall back immediately, not make the reader wait for a socket timeout.
    if not status()["available"]:
        return None, "model_unavailable"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "think": False,
        "format": _SCHEMA,
        "options": {"temperature": 0.0, "num_predict": 300},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            return None, "model_empty"
        draft = json.loads(content)
        answer = draft.get("answer")
        actions = draft.get("actions")
        if not isinstance(answer, str) or not answer.strip():
            return None, "model_invalid_shape"
        if not isinstance(actions, list) or not all(isinstance(item, str) for item in actions):
            return None, "model_invalid_shape"
        return {"answer": answer.strip(), "actions": [item.strip() for item in actions if item.strip()]}, "ok"
    except TimeoutError:
        return None, "model_timeout"
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            return None, "model_timeout"
        _log(f"chat error: {exc}")
        return None, "model_error"
    except (json.JSONDecodeError, OSError) as exc:
        _log(f"chat parse error: {type(exc).__name__}: {exc}")
        return None, "model_error"


def _route(con: duckdb.DuckDBPyConnection, question: str) -> tuple[str, dict[str, Any]]:
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", question):
        detail = analysis.sku_detail(con, token)
        if detail is not None:
            return "sku", detail
    lowered = question.lower()
    loss_text = lowered.replace("盈亏平衡", "")
    if any(
        word in loss_text
        for word in ("亏", "亏损", "loss", "赔", "为负", "负毛利", "成本覆盖不足")
    ):
        return "loss", analysis.loss_skus(con)
    if any(word in lowered for word in ("广告", "投放", "roi", "直通车", "万相台")):
        return "ad", analysis.ad_waste(con)
    return "overview", analysis.overview(con)


def _template(intent: str, data: dict[str, Any]) -> str:
    if intent == "sku":
        per_order = float(data["loss_per_order"] or 0)
        direction = "亏" if per_order < 0 else "赚"
        return (
            f"{data['sku']} 本期贡献毛利 ¥{_fmt(data['contribution_margin'])}，"
            f"每单{direction} ¥{_fmt(abs(per_order))}，"
            f"退款率 {_pct(data['refund_rate'])}，广告 ¥{_fmt(data['ad_spend'])}。"
            f"成本覆盖 {_pct(data['cost_coverage'])}。"
        )
    if intent == "loss":
        items = data.get("items", [])
        if not items:
            return "这一期没有发现已知成本的亏损 SKU。先确认成本覆盖是否完整。"
        top = items[0]
        return (
            f"本期有 {len(items)} 个亏损 SKU。最大的是 {top['sku']}："
            f"每单亏 ¥{_fmt(abs(top['loss_per_order'] or 0))}，"
            f"贡献毛利 ¥{_fmt(top['contribution_margin'])}，"
            f"退款率 {_pct(top['refund_rate'])}。"
        )
    if intent == "ad":
        items = data.get("items", [])
        if not items:
            return "这一期没有发现广告浪费。"
        top = items[0]
        return (
            f"本期广告浪费约 ¥{_fmt(data['total_waste'])}。最大的是 "
            f"{top['campaign']}（{top['sku']}）：花费 ¥{_fmt(top['spend'])}，"
            f"成交 ¥{_fmt(top['attributed_revenue'])}，"
            f"ROI {_fmt(top['roi']) if top['roi'] is not None else '—'}，"
            f"估算浪费 ¥{_fmt(top['waste'])}。"
        )
    actions = data.get("actions", [])
    lead = f"最该先处理：{actions[0]['title']}。" if actions else ""
    return (
        f"本期贡献毛利 ¥{_fmt(data['contribution_margin'])}，"
        f"成本覆盖 {_pct(data['cost_coverage'])}，"
        f"亏损商品 {data['loss_sku_count']} 个，"
        f"广告浪费 ¥{_fmt(data['ad_waste_total'])}。{lead}"
    )


def answer_question(
    con: duckdb.DuckDBPyConnection,
    question: str,
    start: Any = None,
    end: Any = None,
) -> dict[str, Any]:
    intent, data = _route(con, question)
    if start is not None or end is not None:
        if intent == "ad":
            data = analysis.ad_waste(con, start, end)
        elif intent == "loss":
            data = analysis.loss_skus(con, start, end)
        elif intent == "overview":
            data = analysis.overview(con, start, end)
        elif intent == "sku":
            data = analysis.sku_detail(con, data["sku"], start, end) or data

    template = _template(intent, data)
    context = json.dumps(data, ensure_ascii=False, default=str)
    draft, reason = _chat(
        _SYSTEM,
        f"问题：{question}\n\n数据：{context}\n\n"
        "只返回 JSON：answer 是 2-3 句解释，actions 是 1-3 条动作。不要写数字。",
    )

    if draft is not None:
        # The template owns the explanation; the model owns the actions. Its
        # prose is logged for inspection but not shown, because a small model
        # can state a relationship the numbers do not support even when every
        # numeral it used is allowed.
        _log(f"model explanation (not shown): {draft['answer']!r}")
        actions = [
            item for item in draft["actions"][:3]
            if item and _grounded(item, data)
        ]
        if actions:
            rendered = "\n".join(f"- {item}" for item in actions)
            return {
                "question": question,
                "answer": f"{template}\n\n建议：\n{rendered}",
                "intent": intent,
                "generated": True,
                "reason": "",
                "evidence": data,
            }
        reason = "model_actions_rejected"

    return {
        "question": question,
        "answer": template,
        "intent": intent,
        "generated": False,
        "reason": reason,
        "evidence": data,
    }
