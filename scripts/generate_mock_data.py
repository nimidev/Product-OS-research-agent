#!/usr/bin/env python3
"""
Mock Data Generator Documentation
==================================

This script documents the creation process for the mock fixture dataset used by
the Product-OS Research Agent. The dataset represents organizational knowledge
from a hypothetical ChatGPT product team at OpenAI.

The fixture files in data/fixtures/ were hand-crafted (with AI assistance) to
ensure realistic, interconnected content that exercises the Research Agent's
semantic search, cross-referencing, and synthesis capabilities.

Dataset Overview
----------------
- feature_requests.json : 50 items — Enterprise and consumer feature requests
- bugs.json             : 40 items — Bug reports across all product surfaces
- roadmap_items.json    : 25 items — Roadmap with planned/in_progress/launched status
- meeting_notes.json    : 40 items — Sprint reviews, customer feedback, planning
- prds.json             : 20 items — Product requirement documents
- support_tickets.json  : 30 items — Customer support interactions

Total: 205 items spanning January 2025 to February 2026.

Schema
------
Each item follows this structure:

    {
        "id": "mock:{type}:{3-digit-number}",
        "title": "...",
        "body": "...(detailed, 50-150 words)",
        "source": "mock",
        "metadata": {
            "tags": ["..."],
            "priority": "high|medium|low",
            "url": "",
            // roadmap_items also include: "status": "planned|in_progress|launched"
        },
        "created_at": "2025-XX-XXTXX:XX:XX+00:00",
        "updated_at": "2025-XX-XXTXX:XX:XX+00:00"
    }

Cross-Cutting Themes
--------------------
These themes intentionally appear across multiple fixture files to test the
Research Agent's ability to discover related information across data sources:

1. Enterprise data privacy
   - feature_requests: items 013, 023, 033
   - roadmap_items: items 012, 025
   - meeting_notes: items 002, 013, 023
   - prds: items 008, 018
   - support_tickets: items 013, 020, 028, 029

2. Memory system
   - feature_requests: items 006, 041
   - bugs: items 001, 009, 021, 036
   - roadmap_items: item 011
   - meeting_notes: item 001
   - prds: item 001
   - support_tickets: item 019

3. Voice mode
   - feature_requests: items 009, 032, 049
   - bugs: item 016
   - roadmap_items: item 005
   - meeting_notes: item 005
   - prds: item 004

4. Code Interpreter
   - feature_requests: item 017
   - bugs: items 003, 011, 022
   - meeting_notes: item 012
   - prds: item 006
   - support_tickets: item 021

5. Enterprise SSO/security
   - feature_requests: items 001, 013, 043
   - bugs: item 006
   - roadmap_items: item 010
   - meeting_notes: items 002, 015
   - prds: item 012
   - support_tickets: items 015, 020

6. Content policy / safety
   - bugs: item 038
   - meeting_notes: items 011, 017, 029
   - support_tickets: items 003, 009, 024

Tag Distribution
----------------
Enterprise-related tags appear in all 6 files.
Developer/API tags span feature_requests, bugs, prds, and support_tickets.
Mobile tags appear in feature_requests, bugs, and support_tickets.
UX/accessibility tags appear in feature_requests, bugs, roadmap_items, and prds.

Usage
-----
The fixtures are static JSON files intended to be loaded directly by the
Research Agent's ingestion pipeline. No generation step is needed — simply
read the files from data/fixtures/.

    import json
    from pathlib import Path

    FIXTURES_DIR = Path(__file__).parent.parent / "data" / "fixtures"

    def load_fixtures():
        fixtures = {}
        for path in FIXTURES_DIR.glob("*.json"):
            with open(path) as f:
                fixtures[path.stem] = json.load(f)
        return fixtures

    if __name__ == "__main__":
        data = load_fixtures()
        for name, items in sorted(data.items()):
            print(f"{name}: {len(items)} items")
"""

import json
from pathlib import Path


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"

EXPECTED_COUNTS = {
    "feature_requests": 50,
    "bugs": 40,
    "roadmap_items": 25,
    "meeting_notes": 40,
    "prds": 20,
    "support_tickets": 30,
}


def load_fixtures() -> dict[str, list[dict]]:
    """Load all fixture JSON files from the fixtures directory."""
    fixtures = {}
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        with open(path) as f:
            fixtures[path.stem] = json.load(f)
    return fixtures


def validate_item(item: dict, file_name: str) -> list[str]:
    """Validate a single fixture item against the expected schema."""
    errors = []
    required_fields = ["id", "title", "body", "source", "metadata", "created_at", "updated_at"]

    for field in required_fields:
        if field not in item:
            errors.append(f"[{file_name}] {item.get('id', '???')}: missing field '{field}'")

    if "metadata" in item:
        meta = item["metadata"]
        if "tags" not in meta or not isinstance(meta["tags"], list):
            errors.append(f"[{file_name}] {item['id']}: metadata.tags must be a list")
        if "priority" not in meta:
            errors.append(f"[{file_name}] {item['id']}: metadata.priority is missing")

    if "body" in item:
        word_count = len(item["body"].split())
        if word_count < 40:
            errors.append(f"[{file_name}] {item['id']}: body too short ({word_count} words)")

    return errors


def validate_fixtures(fixtures: dict[str, list[dict]]) -> None:
    """Validate all fixtures and print a summary report."""
    total_items = 0
    all_errors = []
    all_tags = set()

    print("=" * 60)
    print("Mock Fixture Dataset Validation Report")
    print("=" * 60)

    for name, items in sorted(fixtures.items()):
        count = len(items)
        total_items += count
        expected = EXPECTED_COUNTS.get(name, "?")
        status = "OK" if count == expected else f"MISMATCH (expected {expected})"
        print(f"  {name:25s} {count:4d} items  {status}")

        for item in items:
            errors = validate_item(item, name)
            all_errors.extend(errors)
            if "metadata" in item and "tags" in item["metadata"]:
                all_tags.update(item["metadata"]["tags"])

    print(f"\n  {'TOTAL':25s} {total_items:4d} items")
    print(f"  Unique tags: {len(all_tags)}")
    print(f"  Validation errors: {len(all_errors)}")

    if all_errors:
        print("\nErrors:")
        for error in all_errors:
            print(f"  - {error}")

    print("\nTag cloud:")
    for tag in sorted(all_tags):
        print(f"  - {tag}")

    print("=" * 60)


if __name__ == "__main__":
    fixtures = load_fixtures()
    validate_fixtures(fixtures)
