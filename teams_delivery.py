"""Microsoft Teams delivery via Power Automate Workflows webhook — Adaptive Card format."""
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone

import requests

from matcher import MatchResult

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 10

_SOURCE_LABELS = {
    "google_alerts": "Google Alerts",
    "inbox": "Newsletter",
    "rest_api_example": "REST API",
}


def _webhook_url() -> str:
    url = os.environ.get("TEAMS_WEBHOOK_URL", "")
    if not url:
        logger.warning("TEAMS_WEBHOOK_URL not set — Teams messages will not be sent")
    return url


def _source_label(source: str) -> str:
    return _SOURCE_LABELS.get(source, source.replace("_", " ").title())


def _build_adaptive_card(
    title: str,
    subtitle: str,
    matches: list[MatchResult],
) -> dict:
    """
    Build an Adaptive Card with a header and one Container per matched item.

    Each Container shows the article headline as a clickable link and the
    source in small muted text beneath it. No raw URLs are visible.
    """
    has_urgent = any(m.is_brief_match for m in matches)

    body = [
        {
            "type": "TextBlock",
            "text": title,
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
            "color": "Attention" if has_urgent else "Default",
        },
        {
            "type": "TextBlock",
            "text": subtitle,
            "size": "Small",
            "isSubtle": True,
            "spacing": "None",
        },
    ]

    for m in matches:
        prefix = "🚨 " if m.is_brief_match else ""
        body.append(
            {
                "type": "Container",
                "separator": True,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"{prefix}[{m.item.title}]({m.item.url})",
                        "wrap": True,
                    },
                    {
                        "type": "TextBlock",
                        "text": f"via {_source_label(m.item.source)}",
                        "size": "Small",
                        "isSubtle": True,
                        "spacing": "None",
                    },
                ],
            }
        )

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }


def _post(card: dict) -> bool:
    url = _webhook_url()
    if not url:
        return False
    try:
        # The Power Automate flow reads the entire body as the Adaptive Card.
        # In the flow's "Post card" action, set the Adaptive Card field to:
        #   string(triggerBody())
        r = requests.post(url, json=card, timeout=_REQUEST_TIMEOUT)
        r.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Teams delivery failed: %s", exc)
        return False


def deliver_immediate(matches: list[MatchResult]) -> None:
    """Send matched items immediately, one Adaptive Card per client per run."""
    by_client: dict[str, list[MatchResult]] = defaultdict(list)
    for m in matches:
        by_client[m.client].append(m)

    for client, client_matches in by_client.items():
        has_urgent = any(m.is_brief_match for m in client_matches)
        prefix = "🚨 URGENT — " if has_urgent else ""
        timestamp = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
        card = _build_adaptive_card(
            title=f"{prefix}Coverage update — {client}",
            subtitle=timestamp,
            matches=client_matches,
        )
        if _post(card):
            logger.info("Delivered %d items for %s to Teams", len(client_matches), client)


def deliver_digest(matches: list[MatchResult]) -> None:
    """Morning digest: one Adaptive Card per client covering the last 24 h."""
    if not matches:
        logger.info("Digest: no matches to deliver")
        return

    by_client: dict[str, list[MatchResult]] = defaultdict(list)
    for m in matches:
        by_client[m.client].append(m)

    for client, client_matches in by_client.items():
        has_urgent = any(m.is_brief_match for m in client_matches)
        prefix = "🚨 URGENT — " if has_urgent else ""
        subtitle = f"{len(client_matches)} item{'s' if len(client_matches) != 1 else ''} in the past 24 hours"
        card = _build_adaptive_card(
            title=f"{prefix}Morning digest — {client}",
            subtitle=subtitle,
            matches=client_matches,
        )
        if _post(card):
            logger.info("Digest delivered %d items for %s", len(client_matches), client)
