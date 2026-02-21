#!/usr/bin/env python3
"""One-time script: reshape flat fixtures to canonical entity field format.

Old format: { id, source, type, title, body, metadata: {...}, ... }
New format: { id, source, entity_type, source_id, title, fields: {...}, created_at, updated_at }

Fields dict maps canonical field names to string values.
"""

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"


def reshape_feature_request(item: dict) -> dict:
    meta = item.get("metadata", {})
    fields = {
        "description": item.get("body", ""),
        "customer": meta.get("customer_segment", ""),
        "priority": meta.get("priority", ""),
        "status": "open",
        "votes": str(meta.get("votes", 0)),
    }
    if meta.get("tags"):
        fields["tags"] = json.dumps(meta["tags"])
    if meta.get("url"):
        fields["url"] = meta["url"]
    return _make_canonical(item, "feature_request", fields)


def reshape_roadmap_item(item: dict) -> dict:
    meta = item.get("metadata", {})
    fields = {
        "description": item.get("body", ""),
        "target_start": meta.get("quarter", ""),
        "target_end": "",
        "status": meta.get("status", ""),
        "priority": "",
    }
    if meta.get("team"):
        fields["team"] = meta["team"]
    return _make_canonical(item, "roadmap_item", fields)


def reshape_support_ticket(item: dict) -> dict:
    meta = item.get("metadata", {})
    fields = {
        "description": item.get("body", ""),
        "customer": meta.get("customer", ""),
        "priority": meta.get("severity", ""),
        "status": "open",
        "resolution": meta.get("resolution_status", ""),
    }
    if meta.get("customer_tier"):
        fields["customer_tier"] = meta["customer_tier"]
    return _make_canonical(item, "support_ticket", fields)


def reshape_bug(item: dict) -> dict:
    meta = item.get("metadata", {})
    fields = {
        "description": item.get("body", ""),
        "severity": meta.get("severity", ""),
        "status": meta.get("status", "open"),
        "affected_version": "",
        "priority": meta.get("severity", ""),
    }
    if meta.get("component"):
        fields["component"] = meta["component"]
    if meta.get("affected_users"):
        fields["affected_users"] = str(meta["affected_users"])
    return _make_canonical(item, "bug", fields)


def reshape_prd(item: dict) -> dict:
    meta = item.get("metadata", {})
    fields = {
        "overview": item.get("body", ""),
        "target_users": "",
        "requirements": "",
        "success_metrics": "",
        "status": meta.get("status", ""),
    }
    if meta.get("author"):
        fields["author"] = meta["author"]
    if meta.get("team"):
        fields["team"] = meta["team"]
    if meta.get("stakeholders"):
        fields["stakeholders"] = json.dumps(meta["stakeholders"])
    return _make_canonical(item, "prd", fields)


def reshape_meeting_note(item: dict) -> dict:
    meta = item.get("metadata", {})
    fields = {
        "transcript": item.get("body", ""),
        "summary": "",
        "attendees": json.dumps(meta.get("attendees", [])),
        "date": item.get("created_at", ""),
        "tags": json.dumps([meta.get("meeting_type", "")]) if meta.get("meeting_type") else "[]",
    }
    if meta.get("action_items"):
        fields["action_items"] = json.dumps(meta["action_items"])
    if meta.get("decisions"):
        fields["decisions"] = json.dumps(meta["decisions"])
    return _make_canonical(item, "meeting_note", fields)


def _make_canonical(item: dict, entity_type: str, fields: dict) -> dict:
    old_id = item["id"]
    source_id = old_id.split(":")[-1] if ":" in old_id else old_id
    return {
        "id": old_id,
        "source": item.get("source", "mock"),
        "entity_type": entity_type,
        "source_id": source_id,
        "title": item.get("title", ""),
        "fields": {k: v for k, v in fields.items() if v},
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


RESHAPER = {
    "feature_requests": reshape_feature_request,
    "bugs": reshape_bug,
    "roadmap_items": reshape_roadmap_item,
    "meeting_notes": reshape_meeting_note,
    "prds": reshape_prd,
    "support_tickets": reshape_support_ticket,
}


def main() -> None:
    for filename, reshaper in RESHAPER.items():
        path = FIXTURES_DIR / f"{filename}.json"
        if not path.exists():
            print(f"SKIP {filename}: not found")
            continue

        with open(path) as f:
            old_items = json.load(f)

        new_items = [reshaper(item) for item in old_items]
        with open(path, "w") as f:
            json.dump(new_items, f, indent=2, ensure_ascii=False)

        print(f"OK {filename}: {len(new_items)} items reshaped")


if __name__ == "__main__":
    main()
