"""Offline eval helper for US-008.

Runs the reference (gold) questions from product-docs/research-agent/reference_answers.md
against the live Research Agent API (/search_memories) and prints summaries so you can
compare them to the reference answers.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


DEFAULT_API_URL = "http://localhost:8000/search_memories"


@dataclass
class EvalCase:
    question: str
    ref_answer: str


def _load_reference_cases(ref_path: Path) -> list[EvalCase]:
    """Parse reference_answers.md into (question, reference answer) pairs.

    Format assumptions (see reference_answers.md):
    - Sections with lines like: "**Question:** text..."
    - Followed later by "**Reference answer:**" and a Markdown block until the next '---' or '## '.
    """
    text = ref_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    cases: list[EvalCase] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("**Question:**"):
            question = line.split("**Question:**", 1)[1].strip()
            # Collect reference answer for this question
            ref_answer = ""
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("**Reference answer:**"):
                j += 1
            if j < len(lines) and lines[j].strip().startswith("**Reference answer:**"):
                # Everything after this line until a horizontal rule or next '## ' becomes the ref answer
                ref_lines: list[str] = []
                k = j + 1
                while k < len(lines):
                    s = lines[k]
                    if s.strip().startswith("---") or s.startswith("## "):
                        break
                    ref_lines.append(s)
                    k += 1
                ref_answer = "\n".join(ref_lines).strip()
                i = k
            else:
                i = j

            if question:
                cases.append(EvalCase(question=question, ref_answer=ref_answer))
        else:
            i += 1

    return cases


async def _run_single_case(
    client: httpx.AsyncClient,
    api_url: str,
    case: EvalCase,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": case.question,
        "filters": {},
        "entity_types": None,
        "field_names": None,
        "top_k": 20,
        "context": None,
    }
    resp = await client.post(api_url, json=payload, timeout=60.0)
    resp.raise_for_status()
    data = resp.json()
    return {
        "question": case.question,
        "summary": data.get("summary", ""),
        "degraded": data.get("degraded", False),
        "ref_answer": case.ref_answer,
    }


async def main() -> None:
    root = Path(__file__).resolve().parent.parent
    refs_path = root / "product-docs" / "research-agent" / "reference_answers.md"
    if not refs_path.exists():
        raise SystemExit(f"reference_answers.md not found at {refs_path}")

    cases = _load_reference_cases(refs_path)
    if not cases:
        raise SystemExit("No reference cases found in reference_answers.md")

    print(f"Loaded {len(cases)} reference cases from {refs_path}")

    async with httpx.AsyncClient() as client:
        results: list[dict[str, Any]] = []
        for idx, case in enumerate(cases, 1):
            print(f"\n=== Case {idx}: {case.question} ===")
            try:
                result = await _run_single_case(client, DEFAULT_API_URL, case)
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR running case: {exc}")
                continue
            results.append(result)

            print("\n--- Model summary ---\n")
            print(result["summary"])
            if result["degraded"]:
                print("\n[degraded = True]")

            if case.ref_answer:
                print("\n--- Reference answer (gold) ---\n")
                print(case.ref_answer)

    # Dump machine-readable log for future analysis
    out_path = root / "eval_results_us008.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved JSON results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

