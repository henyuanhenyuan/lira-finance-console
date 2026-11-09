"""pgvector 知识库：切分、嵌入、混合检索（向量 + 全文）。"""

from __future__ import annotations

import re
from typing import Any

from . import db, llm

CHUNK_SIZE = 220
CHUNK_OVERLAP = 40


def _split(text: str) -> list[str]:
    text = text.strip()
    if len(text) <= CHUNK_SIZE:
        return [text]
    sentences = re.split(r"(?<=[。；！？\n])", text)
    chunks: list[str] = []
    buf = ""
    for s in sentences:
        if len(buf) + len(s) > CHUNK_SIZE and buf:
            chunks.append(buf.strip())
            buf = buf[-CHUNK_OVERLAP:] + s
        else:
            buf += s
    if buf.strip():
        chunks.append(buf.strip())
    return [c for c in chunks if c]


async def index_all(force: bool = False) -> dict[str, Any]:
    """把 kb.docs 全部切分并写入 kb.chunks。"""
    if not force:
        n = await db.fetchval("SELECT COUNT(*) FROM kb.chunks")
        if n and n > 0:
            return {"chunks": n, "skipped": True}

    docs = await db.fetch("SELECT id, title, body FROM kb.docs ORDER BY id")
    await db.execute("DELETE FROM kb.chunks")
    total = 0
    for doc in docs:
        pieces = _split(doc["body"])
        vectors = await llm.embed(pieces)
        rows = []
        for i, (piece, vec) in enumerate(zip(pieces, vectors)):
            rows.append((doc["id"], i, piece, llm.to_vector_literal(vec)))
        async with db.pool().acquire() as conn:
            await conn.executemany(
                "INSERT INTO kb.chunks(doc_id, idx, content, embedding, tsv)"
                " VALUES($1,$2,$3,$4::vector, to_tsvector('simple', $3))",
                rows,
            )
        total += len(rows)
    return {"chunks": total, "skipped": False}


async def search(query: str, k: int = 4) -> list[dict[str, Any]]:
    """向量召回 + 全文召回做加权融合（简化版混合检索）。"""
    vec = (await llm.embed([query]))[0]
    lit = llm.to_vector_literal(vec)
    rows = await db.fetch(
        """
        WITH vec AS (
            SELECT c.id, c.content, c.idx, d.title, d.slug,
                   1 - (c.embedding <=> $1::vector) AS sim
            FROM kb.chunks c JOIN kb.docs d ON d.id = c.doc_id
            ORDER BY c.embedding <=> $1::vector
            LIMIT $2
        ), fts AS (
            SELECT c.id, ts_rank(c.tsv, plainto_tsquery('simple', $3)) AS rank
            FROM kb.chunks c
            WHERE c.tsv @@ plainto_tsquery('simple', $3)
            LIMIT $2
        )
        SELECT v.id, v.content, v.title, v.slug, v.idx,
               v.sim, COALESCE(f.rank, 0) AS fts,
               (v.sim * 0.75 + COALESCE(f.rank, 0) * 0.25) AS score
        FROM vec v LEFT JOIN fts f USING (id)
        ORDER BY score DESC
        LIMIT $2
        """,
        lit, k, query,  # type: ignore[arg-type]
    )
    return [
        {
            "chunk_id": f"kb:{r['slug']}#{r['idx']}",
            "title": r["title"],
            "slug": r["slug"],
            "content": r["content"],
            "score": round(float(r["score"] or 0), 4),
        }
        for r in rows
    ]
