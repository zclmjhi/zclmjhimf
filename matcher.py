"""Keyword matching against the client registry and active briefs."""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from handlers.base import NormalisedItem

logger = logging.getLogger(__name__)

_BRIEFS_PATH = Path(__file__).parent / "config" / "briefs.json"


@dataclass
class MatchResult:
    item: NormalisedItem
    client: str
    keyword: str
    notify_channel: str
    is_brief_match: bool


def _load_briefs() -> list[dict]:
    if not _BRIEFS_PATH.exists():
        return []
    try:
        with _BRIEFS_PATH.open() as fh:
            data = json.load(fh)
        now = datetime.now(timezone.utc)
        active = []
        for brief in data.get("briefs", []):
            expires = datetime.fromisoformat(brief["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires > now:
                active.append(brief)
            else:
                logger.debug("Brief expired: %s / %s", brief["client"], brief["keywords"])
        return active
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        logger.warning("Could not load briefs.json: %s", exc)
        return []


def _matches(text: str, keyword: str) -> bool:
    return keyword.lower() in text.lower()


def _is_noise(title: str, noise_terms: list[str]) -> bool:
    title_lower = title.lower()
    return any(term.lower() in title_lower for term in noise_terms)


def match_items(
    items: list[NormalisedItem],
    registry: dict,
) -> list[MatchResult]:
    """
    Match each item against:
      1. Active briefs (flagged as urgent)
      2. Client keyword lists from registry

    Items whose title matches a noise_filter term are discarded before matching.
    Returns all matches; a single item may match multiple clients/briefs.
    """
    active_briefs = _load_briefs()
    clients = registry.get("clients", [])
    noise_terms = registry.get("noise_filter", [])
    results: list[MatchResult] = []

    for item in items:
        if noise_terms and _is_noise(item.title, noise_terms):
            logger.debug("Noise filtered: %s", item.title)
            continue

        haystack = f"{item.title} {item.summary}"

        # Brief matching first so urgent flag takes priority
        for brief in active_briefs:
            for kw in brief.get("keywords", []):
                if _matches(haystack, kw):
                    results.append(
                        MatchResult(
                            item=item,
                            client=brief["client"],
                            keyword=kw,
                            notify_channel=brief.get("notify_channel", "general"),
                            is_brief_match=True,
                        )
                    )
                    logger.info(
                        "BRIEF MATCH: '%s' matched brief keyword '%s' for %s",
                        item.title,
                        kw,
                        brief["client"],
                    )
                    break  # one keyword match per brief is enough

        # Registry matching
        for client in clients:
            for kw in client.get("keywords", []):
                if _matches(haystack, kw):
                    results.append(
                        MatchResult(
                            item=item,
                            client=client["name"],
                            keyword=kw,
                            notify_channel=client.get("notify_channel", "general"),
                            is_brief_match=False,
                        )
                    )
                    logger.info(
                        "MATCH: '%s' matched keyword '%s' for %s",
                        item.title,
                        kw,
                        client["name"],
                    )
                    break  # one keyword match per client is enough

    return results
