"""
Deduplication: track seen events in a local JSON file.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone

import config

logger = logging.getLogger(__name__)


def _normalise_key(name: str, date_str: str) -> str:
    raw = f"{name.strip().lower()}|{date_str.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_seen() -> dict:
    path = config.SEEN_EVENTS_FILE
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def save_seen(seen: dict) -> None:
    seen["_last_checked"] = datetime.now(timezone.utc).isoformat()
    with open(path := config.SEEN_EVENTS_FILE, "w") as f:
        json.dump(seen, f, indent=2)
    logger.info("Saved %d seen events to %s", len(seen) - 1, path)


def filter_new(events: list[dict]) -> tuple[list[dict], int]:
    """Return (new_events, duplicate_count)."""
    seen = load_seen()
    new_events = []
    dupes = 0

    for event in events:
        key = _normalise_key(
            event.get("name", ""),
            event.get("date", ""),
        )
        if key in seen:
            dupes += 1
            continue
        seen[key] = {
            "name": event.get("name", ""),
            "date": event.get("date", ""),
            "first_seen": datetime.now(timezone.utc).isoformat(),
        }
        new_events.append(event)

    save_seen(seen)
    logger.info("Deduplication: %d new, %d duplicates", len(new_events), dupes)
    return new_events, dupes
