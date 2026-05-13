"""Microsoft Teams delivery via incoming webhook."""
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone

import requests

from matcher import MatchResult

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 10


def _webhook_url() -> str:
    url = os.environ.get("TEAMS_WEBHOOK_URL", "")
    if not url:
        logger.warning("TEAMS_WEBHOOK_URL not set — Teams messages will not be sent")
    return url


def _format_item_fact(match: MatchResult) -> dict:
    item = match.item
    label = "URGENT" if match.is_brief_match else match.keyword
    return {
        "name": f"[{label}] {item.title}",
        "value": f"[{item.source}] {item.url}",
    }


def _build_card(
    title: str,
    sections: list[dict],
    is_urgent: bool = False,
) -> dict:
    """Build an Adaptive-Card-compatible Teams message payload."""
    theme_color = "FF0000" if is_urgent else "0076D7"
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": theme_color,
        "summary": title,
        "sections": sections,
    }


def _post(payload: dict) -> bool:
    url = _webhook_url()
    if not url:
        return False
    try:
        r = requests.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
        r.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Teams delivery failed: %s", exc)
        return False


def deliver_immediate(matches: list[MatchResult]) -> None:
    """Send each matched item immediately, one card per client per run."""
    by_client: dict[str, list[MatchResult]] = defaultdict(list)
    for m in matches:
        by_client[m.client].append(m)

    for client, client_matches in by_client.items():
        has_urgent = any(m.is_brief_match for m in client_matches)
        facts = [_format_item_fact(m) for m in client_matches]

        sections = [
            {
                "activityTitle": f"Coverage update — {client}",
                "activitySubtitle": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "facts": facts,
                "markdown": True,
            }
        ]
        label = "URGENT — " if has_urgent else ""
        payload = _build_card(
            title=f"{label}Coverage update for {client}",
            sections=sections,
            is_urgent=has_urgent,
        )
        if _post(payload):
            logger.info("Delivered %d items for %s to Teams", len(client_matches), client)


def deliver_digest(matches: list[MatchResult]) -> None:
    """Morning digest: group all 24-hour matches by client in a single card per client."""
    if not matches:
        logger.info("Digest: no matches to deliver")
        return

    by_client: dict[str, list[MatchResult]] = defaultdict(list)
    for m in matches:
        by_client[m.client].append(m)

    for client, client_matches in by_client.items():
        has_urgent = any(m.is_brief_match for m in client_matches)
        facts = [_format_item_fact(m) for m in client_matches]

        sections = [
            {
                "activityTitle": f"Morning digest — {client}",
                "activitySubtitle": f"{len(client_matches)} items in the past 24 hours",
                "facts": facts,
                "markdown": True,
            }
        ]
        label = "URGENT — " if has_urgent else ""
        payload = _build_card(
            title=f"{label}Morning digest for {client}",
            sections=sections,
            is_urgent=has_urgent,
        )
        if _post(payload):
            logger.info("Digest delivered %d items for %s", len(client_matches), client)
