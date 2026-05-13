"""URL-based deduplication backed by a persistent JSON store."""
import hashlib
import json
import logging
from pathlib import Path

from handlers.base import NormalisedItem

logger = logging.getLogger(__name__)

_STORE_PATH = Path(__file__).parent / "data" / "seen_items.json"


def _hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _load_store() -> dict:
    if _STORE_PATH.exists():
        try:
            with _STORE_PATH.open() as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load seen_items.json: %s — starting fresh", exc)
    return {}


def _save_store(store: dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _STORE_PATH.open("w") as fh:
        json.dump(store, fh, indent=2)


def deduplicate(items: list[NormalisedItem]) -> list[NormalisedItem]:
    """Return only items whose URL hash has not been seen before, and persist new hashes."""
    store = _load_store()
    new_items: list[NormalisedItem] = []

    for item in items:
        h = _hash(item.url)
        if h not in store:
            store[h] = item.published_at.isoformat()
            new_items.append(item)
        else:
            logger.debug("Duplicate skipped: %s", item.url)

    if new_items:
        _save_store(store)
        logger.info("Deduplicated: %d new / %d total seen", len(new_items), len(store))

    return new_items
