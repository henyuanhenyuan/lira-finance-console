"""Run the local model against the 100-question eval set.

Automatic checks cover intent, required facts, numeric grounding and latency.
The ``human_score`` column is deliberately blank: usefulness needs a person.

    uv run --directory product python ../scripts/eval.py --all
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))

from app import db, llm  # noqa: E402

QUESTIONS = ROOT / "product" / "eval" / "questions.json"
RESULTS = ROOT / "product" / "eval" / "results.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--all", action="store_true", help="run all questions")
    args = parser.parse_args()

    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    if not args.all:
        questions = questions[: args.limit]

    rows = []
    intent_ok = 0
    content_ok = 0
    generated = 0
    latencies = []

    with db.session() as con:
        for item in questions:
            started = time.perf_counter()
            result = llm.answer_question(con, item["question"])
            elapsed = time.perf_counter() - started
            latencies.append(elapsed)
            ok_intent = result["intent"] == item["expected_intent"]
            ok_content = any(token in result["answer"] for token in item["require_any"])
            intent_ok += int(ok_intent)
            content_ok += int(ok_content)
            generated += int(result["generated"])
            rows.append(
                {
                    "question": item["question"],
                    "expected_intent": item["expected_intent"],
                    "actual_intent": result["intent"],
                    "intent_ok": ok_intent,
                    "content_ok": ok_content,
                    "generated": result["generated"],
                    "reason": result["reason"],
                    "latency_s": round(elapsed, 3),
                    "answer": result["answer"],
                    "human_score": "",
                    "human_note": "",
                }
            )

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    print(f"questions      {total}")
    print(f"intent ok      {intent_ok}/{total} ({intent_ok / total:.1%})")
    print(f"content ok     {content_ok}/{total} ({content_ok / total:.1%})")
    print(f"model actions  {generated}/{total} ({generated / total:.1%})")
    print(f"p50 latency    {sorted(latencies)[total // 2]:.2f}s")
    print(f"results        {RESULTS}")
    print("human_score 列为空，需要人工打分（1–5）。")


if __name__ == "__main__":
    main()
