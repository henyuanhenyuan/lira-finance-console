"""LangGraph 多智能体：监督者按需调度 4 个专职 Agent 做实时分析。

拓扑：START → supervisor →（条件边）→ metric / anomaly / rag → supervisor
                        → advisor → END
无 API Key 时走确定性策略，仍然调用真实工具、给出真实数字。
"""

from __future__ import annotations

import json
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from . import llm, metrics, tools

AGENT_META = {
    "supervisor": {"name": "调度中枢", "tools": []},
    "metric_analyst": {"name": "指标分析师", "tools": ["compare_period", "get_metric_series", "run_sql"]},
    "anomaly_hunter": {"name": "异动猎手", "tools": ["find_anomalies", "get_sku_detail"]},
    "rag_librarian": {"name": "知识馆员", "tools": ["search_kb"]},
    "advisor": {"name": "经营顾问", "tools": []},
}

METRIC_HINTS = {
    "毛利率": "margin_rate", "毛利的": "gross_margin",
    "成本覆盖率": "cost_coverage", "成本": "cost_coverage",
    "退款率": "refund_rate", "退款金额": "refund_amount", "退款": "refund_amount",
    "退货": "refund_amount",
    "复购率": "repurchase_rate", "复购": "repurchase_rate",
    "广告ROI": "ad_roi", "广告 ROI": "ad_roi", "ROI": "ad_roi", "roi": "ad_roi",
    "ACOS": "acos", "广告占比": "ad_share", "广告": "ad_spend", "投放": "ad_spend",
    "客单价": "aov", "件单价": "unit_price", "销售件数": "units_sold",
    "订单": "order_count", "毛利": "gross_margin", "利润": "gross_margin", "赚": "gross_margin",
    "收入": "net_revenue", "营收": "net_revenue", "销售": "net_revenue",
}


class State(TypedDict, total=False):
    question: str
    scope: str
    plan: list[str]
    next: str
    visited: list[str]
    steps: list[dict]
    facts: dict
    citations: list[str]
    insight: dict
    model: str
    tokens_in: int
    tokens_out: int
    cost: float


def _record(state: State, agent_key: str, thought: str, tool: str,
            args: dict, observation: dict, latency: int, tokens: int) -> list[dict]:
    steps = list(state.get("steps", []))
    steps.append({
        "idx": len(steps),
        "agent_key": agent_key,
        "agent_name": AGENT_META[agent_key]["name"],
        "thought": thought,
        "tool": tool,
        "args": args,
        "observation": observation,
        "latency_ms": latency,
        "tokens": tokens,
    })
    return steps


async def _think(agent_key: str, question: str, context: dict) -> str:
    """用正式模型生成一句思考；无 Key 时用规则描述。"""
    res = await llm.chat(
        [
            {"role": "system", "content": f"你是{AGENT_META[agent_key]['name']}。用一句中文说明你下一步要查什么，不要输出数字。"},
            {"role": "user", "content": f"问题：{question}\n已知：{json.dumps(context, ensure_ascii=False)[:1200]}"},
        ],
        temperature=0.1,
    )
    if res and res["text"].strip():
        return res["text"].strip()[:120]
    return {
        "supervisor": "按计划调度下一个专职智能体。",
        "metric_analyst": "先取核心指标的最新值与环比。",
        "anomaly_hunter": "用 Z-score 找出偏离基线的 SKU。",
        "rag_librarian": "检索口径文档，确认判定的制度依据。",
        "advisor": "把指标与制度合成可执行动作。",
    }[agent_key]


# ---------------- 节点 ----------------

async def supervisor(state: State) -> dict:
    question = state["question"]
    visited = state.get("visited", [])
    plan = state.get("plan", [])

    pending = [p for p in plan if p not in visited]
    if pending:
        nxt = pending[0]
    else:
        nxt = "advisor"

    thought = await _think("supervisor", question, {"done": visited, "next": nxt})
    steps = _record(state, "supervisor", thought or f"路由到 {AGENT_META.get(nxt, {}).get('name', nxt)}",
                    "", {}, {"next": nxt}, 0, 0)
    return {"steps": steps, "next": nxt,
            "visited": visited + [nxt] if nxt != "advisor" else visited}


async def metric_analyst(state: State) -> dict:
    q = state["question"]
    wanted: list[str] = []
    for kw, metric in sorted(METRIC_HINTS.items(), key=lambda kv: -len(kv[0])):
        if kw in q and metric not in wanted:
            wanted.append(metric)
    if not wanted:
        wanted = ["gross_margin", "net_revenue", "margin_rate", "order_count"]
    wanted = wanted[:3]

    facts = dict(state.get("facts", {}))
    facts.setdefault("compare", {})
    facts.setdefault("series", {})
    steps = list(state.get("steps", []))
    tin = toks = 0
    cost = state.get("cost", 0.0)

    thought = await _think("metric_analyst", q, {"metrics": wanted})
    for metric in wanted:
        try:
            obs, ms = await tools.call("compare_period", {"metric": metric, "days": 7})
        except Exception as exc:  # noqa: BLE001
            obs, ms = {"error": str(exc)}, 0
        facts["compare"][metric] = obs
        steps = _record({"steps": steps}, "metric_analyst", thought, "compare_period",
                        {"metric": metric, "days": 7}, obs, ms, 0)

    primary = wanted[0]
    try:
        ser, ms = await tools.call("get_metric_series", {"metric": primary, "days": 30})
    except Exception as exc:  # noqa: BLE001
        ser, ms = {"error": str(exc)}, 0
    facts["series"][primary] = ser.get("points", [])
    steps = _record({"steps": steps}, "metric_analyst", thought, "get_metric_series",
                    {"metric": primary, "days": 30},
                    {"points": len(ser.get("points", [])), "total": ser.get("total")}, ms, 0)

    return {"facts": facts, "steps": steps, "tokens_in": tin, "tokens_out": toks,
            "cost": cost}


async def anomaly_hunter(state: State) -> dict:
    q = state["question"]
    facts = dict(state.get("facts", {}))
    steps = list(state.get("steps", []))
    thought = await _think("anomaly_hunter", q, {})

    try:
        obs, ms = await tools.call("find_anomalies", {"days": 7})
    except Exception as exc:  # noqa: BLE001
        obs, ms = {"items": [], "error": str(exc)}, 0
    items = obs.get("items", [])
    facts["anomalies"] = items
    steps = _record({"steps": steps}, "anomaly_hunter", thought, "find_anomalies",
                    {"days": 7},
                    {"count": len(items), "worst": obs.get("worst"),
                     "items": items[:6]}, ms, 0)

    if items:
        worst = items[0]["sku_id"]
        try:
            det, ms2 = await tools.call("get_sku_detail", {"sku_id": worst})
        except Exception as exc:  # noqa: BLE001
            det, ms2 = {"error": str(exc)}, 0
        facts["worst_sku"] = det
        steps = _record({"steps": steps}, "anomaly_hunter", thought, "get_sku_detail",
                        {"sku_id": worst},
                        {k: det.get(k) for k in ("sku_id", "title", "gross_margin",
                                                 "margin_rate", "ad_roi", "refund_rate")},
                        ms2, 0)

    return {"facts": facts, "steps": steps}


async def rag_librarian(state: State) -> dict:
    q = state["question"]
    facts = dict(state.get("facts", {}))
    steps = list(state.get("steps", []))
    citations = list(state.get("citations", []))
    thought = await _think("rag_librarian", q, {})

    try:
        obs, ms = await tools.call("search_kb", {"query": q, "k": 4})
    except Exception as exc:  # noqa: BLE001
        obs, ms = {"hits": [], "citations": [], "error": str(exc)}, 0
    facts["kb"] = obs.get("hits", [])
    citations.extend([c for c in obs.get("citations", []) if c not in citations])
    steps = _record({"steps": steps}, "rag_librarian", thought, "search_kb",
                    {"query": q},
                    {"hits": [h["title"] for h in obs.get("hits", [])]}, ms, 0)

    return {"facts": facts, "steps": steps, "citations": citations}


UNSAFE_PATTERNS = ("忽略之前", "忽略以上", "ignore previous", "ignore above", "系统提示",
                   "system prompt", "密码", "password", "删除", "drop ", "delete ",
                   "truncate", "清空", "导出所有", "密钥", "api key", "token 给我")


def _unsafe(q: str) -> bool:
    low = q.lower()
    return any(p in low for p in UNSAFE_PATTERNS)


def _fmt_money(v: float) -> str:
    return f"{v/10000:.2f} 万" if abs(v) >= 10000 else f"{v:.0f} 元"


def _fmt_pct(v: float) -> str:
    return f"{v*100:.1f}%"


async def advisor(state: State) -> dict:
    facts = state.get("facts", {})
    citations = state.get("citations", [])
    steps = list(state.get("steps", []))

    insight = await _llm_insight(state) or _rule_insight(state)
    insight.setdefault("evidence", [])
    for c in citations:
        if c not in insight["evidence"]:
            insight["evidence"].append(c)

    steps = _record({"steps": steps}, "advisor", insight.get("headline", ""), "",
                    {}, {"confidence": insight.get("confidence"),
                         "drivers": len(insight.get("drivers", [])),
                         "actions": len(insight.get("actions", []))}, 0, 0)
    model = llm.active_model("production")["model"] if llm.available() else "rule-engine"
    return {"insight": insight, "steps": steps, "facts": facts, "model": model}


async def _llm_insight(state: State) -> dict | None:
    if not llm.available():
        return None
    facts = state.get("facts", {})
    compare = facts.get("compare", {})
    payload = {
        "compare": {k: {"current": v.get("current"), "pct": v.get("pct")}
                    for k, v in compare.items()},
        "anomalies": facts.get("anomalies", [])[:5],
        "worst_sku": facts.get("worst_sku"),
        "kb": [{"title": h["title"], "chunk": h["chunk_id"]} for h in facts.get("kb", [])],
    }
    res = await llm.chat(
        [
            {"role": "system", "content":
                "你是电商财务分析顾问。只能引用输入数据里的数字，禁止编造。"
                "输出严格 JSON：{\"headline\":string,\"drivers\":[{\"factor\":string,\"impact\":number,\"share\":number}],"
                "\"confidence\":number(0-1),\"evidence\":[string],\"actions\":[{\"title\":string,\"expected\":string}]}"},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        json_mode=True,
        temperature=0.2,
    )
    if not res:
        return None
    data = llm.parse_json(res["text"])
    if not isinstance(data, dict) or not data.get("headline"):
        return None
    data.setdefault("drivers", [])
    data.setdefault("actions", [])
    data.setdefault("confidence", 0.6)
    data.setdefault("evidence", [])
    return data


def _headline_of(compare: dict) -> str:
    if not compare:
        return "已完成本周经营指标的取数与校验"
    primary = next(iter(compare))
    c = compare[primary]
    label = metrics.CATALOGUE.get(primary, {}).get("label", primary)
    unit = metrics.CATALOGUE.get(primary, {}).get("unit", "currency")
    cur = c.get("current", 0) or 0
    pct = c.get("pct", 0) or 0
    if unit == "ratio":
        return (f"近 7 天{label}为 {cur*100:.1f}%，"
                f"环比{'下降' if pct < 0 else '上升'} {abs(pct)*100:.1f}%")
    if unit == "count":
        return (f"近 7 天{label} {cur:.0f}，"
                f"环比{'下滑' if pct < 0 else '增长'} {abs(pct)*100:.1f}%")
    return (f"近 7 天{label} {_fmt_money(cur)}，"
            f"环比{'下滑' if pct < 0 else '增长'} {abs(pct)*100:.1f}%")


def _refusal(state: State) -> dict:
    return {
        "headline": "拒绝执行：该请求涉及敏感信息或写操作，超出分析权限",
        "drivers": [],
        "confidence": 0.99,
        "evidence": ["kb:cost-policy#0"],
        "actions": [],
    }


POLICY_HINTS = ("多少", "阈值", "超过", "低于", "定义", "规则", "口径", "怎么算", "预警", "流程")


def _policy_insight(kb: list[dict]) -> dict | None:
    """口径类问题：直接引用制度原文，不掺入经营数字。"""
    if not kb:
        return None
    top = kb[0]
    body = top["content"]
    for sep in ("。", "；"):
        cut = body.find(sep)
        if 0 < cut < 110:
            body = body[: cut + 1]
            break
    return {
        "headline": f"依据《{top['title']}》：{body}",
        "drivers": [{"factor": f"来源文档：{top['title']}", "impact": 0, "share": 1}],
        "confidence": 0.92,
        "evidence": [h["chunk_id"] for h in kb[:3]],
        "actions": [],
    }


def _rule_insight(state: State) -> dict:
    """确定性结论：所有数字来自工具返回，不臆造。"""
    question = state.get("question", "")
    if _unsafe(question):
        return _refusal(state)

    facts = state.get("facts", {})
    compare = facts.get("compare", {})
    anomalies = facts.get("anomalies", [])
    worst = facts.get("worst_sku")
    kb = facts.get("kb", [])
    cc = compare.get("cost_coverage") or {}

    # 只有「短问题 + 问口径」才走制度原文。长问题多半是要做经营分析，
    # 哪怕顺带提到口径规则，也应该走归因与建议。
    if len(question) <= 30 and any(k in question for k in POLICY_HINTS):
        policy = _policy_insight(kb)
        if policy:
            return policy

    drivers: list[dict] = []
    actions: list[dict] = []
    evidence: list[str] = []

    headline = _headline_of(compare)

    if anomalies:
        top = anomalies[:3]
        total_impact = sum(a["current"] - a["baseline"] for a in top)
        for a in top:
            drivers.append({
                "factor": f"{a['title']}（{a['sku_id']}）毛利异动",
                "impact": round(a["current"] - a["baseline"], 2),
                "share": round(abs(a["current"] - a["baseline"]) /
                               (abs(total_impact) or 1), 3),
            })
            evidence.append(f"sku:{a['sku_id']}")
        names = "、".join(a["title"] for a in anomalies[:2])
        losers = sum(1 for a in anomalies if a["current"] < 0)
        tail = f"，其中 {losers} 个处于亏损状态" if losers else ""
        headline += f"；{len(anomalies)} 个 SKU 出现统计异常{tail}，{names} 最突出"
        actions.append({
            "title": f"复核 {anomalies[0]['sku_id']} 的成本与投放",
            "expected": f"回收约 {_fmt_money(max(0, -total_impact))}/周",
        })

    if worst:
        if worst.get("ad_roi") is not None and worst["ad_roi"] < 1.5:
            drivers.append({"factor": f"{worst['sku_id']} 广告 ROI 仅 {worst['ad_roi']:.2f}",
                            "impact": -round(float(worst.get("ad_spend") or 0), 2), "share": 0.2})
            actions.append({"title": f"暂停 {worst['sku_id']} 的广告计划",
                            "expected": "止住 ROI<1.5 的无效投放"})
        if worst.get("margin_rate") is not None and worst["margin_rate"] < 0:
            actions.append({"title": f"{worst['sku_id']} 进入调价/降本评审",
                            "expected": "把每单毛利拉回正值"})

    if cc and cc.get("current", 1) < 0.98:
        drivers.append({"factor": "部分 SKU 缺少成本记录，毛利为估算",
                        "impact": 0, "share": 0})
        actions.append({"title": "补全成本表",
                        "expected": f"成本覆盖率从 {_fmt_pct(cc.get('current', 0))} 提升到 100%"})

    for h in kb[:2]:
        evidence.append(h["chunk_id"])

    if not drivers:
        drivers.append({"factor": "核心指标处于正常波动区间", "impact": 0, "share": 1})
    if not actions:
        actions.append({"title": "维持当前投放与定价", "expected": "指标稳定，无需干预"})

    confidence = 0.55
    if compare:
        confidence += 0.2
    if anomalies:
        confidence += 0.1
    if kb:
        confidence += 0.1
    if cc and cc.get("current", 1) < 0.98:
        confidence -= 0.15

    return {
        "headline": headline,
        "drivers": drivers[:4],
        "confidence": round(min(0.95, max(0.2, confidence)), 2),
        "evidence": evidence,
        "actions": actions[:3],
    }


# ---------------- 图 ----------------

def _plan_for(question: str) -> list[str]:
    q = question
    plan = ["metric_analyst"]
    if any(k in q for k in ("为什么", "异常", "下滑", "亏", "异动", "问题", "原因", "哪")):
        plan.append("anomaly_hunter")
    if any(k in q for k in ("口径", "定义", "规则", "阈值", "怎么算", "流程", "制度",
                            "建议", "怎么办", "处理", "提升", "优化", "诊断", "报告",
                            "多少", "超过", "预警", "低于", "算")):
        plan.append("rag_librarian")
    return plan


def _route(state: State) -> str:
    return state.get("next", "advisor")


def build_graph():
    g = StateGraph(State)
    g.add_node("supervisor", supervisor)
    g.add_node("metric_analyst", metric_analyst)
    g.add_node("anomaly_hunter", anomaly_hunter)
    g.add_node("rag_librarian", rag_librarian)
    g.add_node("advisor", advisor)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges(
        "supervisor", _route,
        {"metric_analyst": "metric_analyst",
         "anomaly_hunter": "anomaly_hunter",
         "rag_librarian": "rag_librarian",
         "advisor": "advisor"},
    )
    for node in ("metric_analyst", "anomaly_hunter", "rag_librarian"):
        g.add_edge(node, "supervisor")
    g.add_edge("advisor", END)
    return g.compile()


_APP = None


def app():
    global _APP
    if _APP is None:
        _APP = build_graph()
    return _APP


async def run(question: str, scope: str = "diagnosis") -> State:
    started = time.perf_counter()
    init: State = {
        "question": question,
        "scope": scope,
        "plan": [] if _unsafe(question) else _plan_for(question),
        "visited": [],
        "steps": [],
        "facts": {},
        "citations": [],
        "insight": {},
        "model": "",
        "tokens_in": 0,
        "tokens_out": 0,
        "cost": 0.0,
    }
    result = await app().ainvoke(init)
    result["latency_ms"] = int((time.perf_counter() - started) * 1000)
    return result
