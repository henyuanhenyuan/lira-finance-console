"""模型路由：正式走 API（qwen-plus 级），本机 4B 仅供测试。

无凭证时返回 None，上层自动降级到确定性分析器 —— 绝不伪造数字。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

import httpx

from .config import get_settings

PRICES: dict[str, tuple[float, float]] = {
    "qwen-plus": (0.00011, 0.00028),
    "qwen-max": (0.00033, 0.00132),
    "qwen-turbo": (0.00005, 0.00010),
    "gpt-4o-mini": (0.00015, 0.00060),
    "gpt-4o": (0.00250, 0.01000),
    "deepseek-chat": (0.00014, 0.00028),
    "qwen3:4b": (0.0, 0.0),
}


class LLMResult(dict):
    pass


def cost_of(model: str, tin: int, tout: int) -> float:
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return round(tin / 1000 * pin + tout / 1000 * pout, 6)


def active_model(purpose: str = "production") -> dict[str, Any]:
    s = get_settings()
    if purpose == "test":
        return {"provider": "ollama", "model": s.test_llm_model,
                "base_url": s.test_llm_base_url, "api_key": "", "test_only": True}
    return {"provider": s.llm_provider, "model": s.llm_model,
            "base_url": s.llm_base_url, "api_key": s.llm_api_key, "test_only": False}


def available(purpose: str = "production") -> bool:
    s = get_settings()
    if purpose == "test":
        return True  # Ollama 是否真的在跑由调用时决定
    return bool(s.llm_api_key)


async def chat(
    messages: list[dict[str, str]],
    *,
    purpose: str = "production",
    json_mode: bool = False,
    temperature: float = 0.2,
    timeout: float | None = None,
) -> LLMResult | None:
    cfg = active_model(purpose)
    s = get_settings()
    if purpose != "test" and not s.llm_api_key:
        return None
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    body: dict[str, Any] = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        async with httpx.AsyncClient(timeout=timeout or s.llm_timeout_s) as client:
            resp = await client.post(
                f"{cfg['base_url'].rstrip('/')}/chat/completions",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None

    usage = data.get("usage", {}) or {}
    tin = int(usage.get("prompt_tokens", 0))
    tout = int(usage.get("completion_tokens", 0))
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    return LLMResult(
        text=text,
        model=cfg["model"],
        tokens_in=tin,
        tokens_out=tout,
        cost=cost_of(cfg["model"], tin, tout),
        test_only=cfg["test_only"],
    )


# ---------- 向量：API 优先，否则确定性本地向量 ----------

def _local_embed(text: str, dim: int) -> list[float]:
    """字符 2/3-gram 哈希投影 + L2 归一化。离线可用、确定性、可复现。"""
    vec = [0.0] * dim
    clean = re.sub(r"\s+", "", text)
    grams: list[str] = []
    for n in (2, 3):
        grams += [clean[i:i + n] for i in range(max(0, len(clean) - n + 1))]
    if not grams:
        grams = [text]
    for g in grams:
        h = hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


async def embed(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    if s.llm_api_key:
        try:
            headers = {"Authorization": f"Bearer {s.llm_api_key}",
                       "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{s.llm_base_url.rstrip('/')}/embeddings",
                    headers=headers,
                    json={"model": s.embed_model, "input": texts,
                          "dimensions": s.embed_dim},
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                return [d["embedding"] for d in sorted(data, key=lambda x: x["index"])]
        except Exception:
            pass
    return [_local_embed(t, s.embed_dim) for t in texts]


def to_vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def parse_json(text: str) -> dict | None:
    """从模型回复里抠出 JSON 对象。"""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None
