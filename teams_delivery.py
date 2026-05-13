"""Microsoft Teams delivery via Power Automate Workflows webhook.

Sends a markdown-formatted text payload as {"text": "..."}.
In the Power Automate flow, set the message body expression to:
    variables('Body')?['text']
"""
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


def _format_message(header: str, subtitle: str, matches: list[MatchResult]) -> str:
    """
    Build a Teams markdown message.

    [Title](url) renders as a clickable link.
    **text** renders as bold.
    _text_ renders as italic.
    """
    lines = [f"**{header}**", f"_{subtitle}_", ""]
    for m in matches:
        prefix = "🚨 " if m.is_brief_match else ""
        lines.append(f"{prefix}**[{m.item.title}]({m.item.url})**")
        lines.append(f"_via {_source_label(m.item.source)}_")
        lines.append("")
    return "\n".join(lines).strip()


def _post(text: str) -> bool:
    url = _webhook_url()
    if not url:
        return False
    try:
        r = requests.post(url, json={"text": text}, timeout=_REQUEST_TIMEOUT)
        r.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Teams delivery failed: %s", exc)
        return False


def deliver_immediate(matches: list[MatchResult]) -> None:
    """Send matched items immediately, one message per client per run."""
    by_client: dict[str, list[MatchResult]] = defaultdict(list)
    for m in matches:
        by_client[m.client].append(m)

    for client, client_matches in by_client.items():
        has_urgent = any(m.is_brief_match for m in client_matches)
        prefix = "🚨 URGENT — " if has_urgent else ""
        timestamp = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
        text = _format_message(
            header=f"{prefix}Coverage update — {client}",
            subtitle=timestamp,
            matches=client_matches,
        )
        if _post(text):
            logger.info("Delivered %d items for %s to Teams", len(client_matches), client)


def deliver_digest(matches: list[MatchResult]) -> None:
    """Morning digest: one message per client covering the last 24 h."""
    if not matches:
        logger.info("Digest: no matches to deliver")
        return

    by_client: dict[str, list[MatchResult]] = defaultdict(list)
    for m in matches:
        by_client[m.client].append(m)

    for client, client_matches in by_client.items():
        has_urgent = any(m.is_brief_match for m in client_matches)
        prefix = "🚨 URGENT — " if has_urgent else ""
        count = len(client_matches)
        subtitle = f"{count} item{'s' if count != 1 else ''} in the past 24 hours"
        text = _format_message(
            header=f"{prefix}Morning digest — {client}",
            subtitle=subtitle,
            matches=client_matches,
        )
        if _post(text):
            logger.info("Digest delivered %d items for %s", len(client_matches), client)
