"""Search quality evaluation — measures precision@5 against curated test queries.

Usage:
    python -m tests.evaluation.evaluate [--qdrant-host localhost] [--qdrant-port 6333]

Requires a seeded Qdrant instance with mock data.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from research_agent.config.loader import get_settings
from research_agent.embedding.openai_provider import OpenAIEmbeddingProvider
from research_agent.memory.memory_service import MemoryService
from research_agent.storage.db import Database
from research_agent.vector.qdrant_client import QdrantStore

QUERIES_PATH = Path(__file__).parent / "test_queries.json"


def _is_relevant(result: dict[str, Any], query_spec: dict[str, Any]) -> bool:
    """Check if a result is relevant based on type and keyword matching."""
    expected_types = query_spec.get("expected_types", [])
    expected_keywords = [k.lower() for k in query_spec.get("expected_keywords", [])]

    type_match = result.get("type", "") in expected_types
    text = f"{result.get('title', '')} {result.get('body', '')}".lower()
    keyword_match = any(kw in text for kw in expected_keywords)

    return type_match and keyword_match


def precision_at_k(results: list[dict[str, Any]], query_spec: dict[str, Any], k: int = 5) -> float:
    """Calculate precision@k: fraction of top-k results that are relevant."""
    top_k = results[:k]
    if not top_k:
        return 0.0
    relevant = sum(1 for r in top_k if _is_relevant(r, query_spec))
    return relevant / len(top_k)


def recall(results: list[dict[str, Any]], query_spec: dict[str, Any]) -> float:
    """Approximate recall: do we have at least one relevant result in top results?"""
    return 1.0 if any(_is_relevant(r, query_spec) for r in results) else 0.0


async def run_evaluation() -> dict[str, Any]:
    settings = get_settings()

    db = Database(db_path=settings.database_path)
    await db.init()

    vector_store = QdrantStore(host=settings.qdrant_host, port=settings.qdrant_port)
    embedder = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key, model=settings.embedding_model
    )
    await vector_store.ensure_collection(embedder.dimension())

    memory = MemoryService(
        db=db, vector_store=vector_store, embedding_provider=embedder, summarizer=None
    )

    with open(QUERIES_PATH) as f:
        queries = json.load(f)

    results_report: list[dict[str, Any]] = []
    total_p5 = 0.0
    total_recall = 0.0
    passing = 0

    for q in queries:
        search_result = await memory.search_memories(query=q["query"], top_k=10)
        raw = search_result.raw_results

        p5 = precision_at_k(raw, q, k=5)
        rec = recall(raw, q)
        total_p5 += p5
        total_recall += rec

        passed = p5 > 0 or rec > 0
        if passed:
            passing += 1

        results_report.append({
            "id": q["id"],
            "query": q["query"],
            "precision@5": round(p5, 3),
            "recall": round(rec, 3),
            "result_count": len(raw),
            "passed": passed,
        })

    n = len(queries)
    summary = {
        "total_queries": n,
        "passing": passing,
        "pass_rate": round(passing / n * 100, 1) if n else 0,
        "avg_precision@5": round(total_p5 / n, 3) if n else 0,
        "avg_recall": round(total_recall / n, 3) if n else 0,
        "target_pass_rate": 80.0,
        "meets_target": (passing / n * 100) >= 80.0 if n else False,
    }

    await vector_store.close()
    await db.close()

    return {"summary": summary, "details": results_report}


def main() -> None:
    report = asyncio.run(run_evaluation())

    print("\n" + "=" * 60)
    print("SEARCH QUALITY EVALUATION REPORT")
    print("=" * 60)

    s = report["summary"]
    print(f"\nQueries: {s['total_queries']}")
    print(f"Passing: {s['passing']} ({s['pass_rate']}%)")
    print(f"Avg Precision@5: {s['avg_precision@5']}")
    print(f"Avg Recall: {s['avg_recall']}")
    print(f"Target: {s['target_pass_rate']}%")
    print(f"Meets Target: {'YES' if s['meets_target'] else 'NO'}")

    print(f"\n{'ID':<6} {'P@5':>5} {'Recall':>7} {'#':>3} {'Pass':>5}  Query")
    print("-" * 80)
    for d in report["details"]:
        status = "PASS" if d["passed"] else "FAIL"
        print(
            f"{d['id']:<6} {d['precision@5']:>5.3f} {d['recall']:>7.3f} "
            f"{d['result_count']:>3} {status:>5}  {d['query'][:50]}"
        )

    output_path = Path(__file__).parent / "baseline_results.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
