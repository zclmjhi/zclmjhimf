"""
Deduplication: track seen events in a local JSON file.
"""

import hashlib
import json
import logging
import os
from datetime import datetime

import config

logger = logging.getLogger(__name__)


def _event_key(name: str, date: str) -> str:
    """Normalised hash of event name + date."""
    raw = f"{name.strip().lower()}|{date.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_seen() -> dict:
    """Load the seen-events store (creates file if missing)."""
    path = config.SEEN_EVENTS_FILE
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupt seen_events file – starting fresh")
        return {}


def save_seen(store: dict) -> None:
    store["last_checked"] = datetime.now().isoformat()
    with open(config.SEEN_EVENTS_FILE, "w") as f:
        json.dump(store, f, indent=2, default=str)
    logger.info("Saved %d entries to %s", len(store) - 1, config.SEEN_EVENTS_FILE)


def filter_new(events: list[dict]) -> list[dict]:
    """Return only events not previously seen, and record them."""
    store = load_seen()
    new_events = []

    for event in events:
        name = event.get("name", "")
        date = event.get("date", "")
        key = _event_key(name, date)

        if key in store:
            logger.debug("Skipping already-seen event: %s", name)
            continue

        store[key] = {
            "name": name,
            "date": date,
            "first_seen": datetime.now().isoformat(),
        }
        new_events.append(event)

    save_seen(store)
    logger.info("Deduplication: %d new events out of %d total", len(new_events), len(events))
    return new_events
