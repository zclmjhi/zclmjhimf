"""Microsoft Teams delivery via Power Automate Workflows webhook."""
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


def _format_message(header: str, matches: list[MatchResult]) -> str:
    """Build a plain-text message string for the Workflows webhook."""
    lines = [header, ""]
    for m in matches:
        prefix = "🚨 URGENT" if m.is_brief_match else f"🔵 {m.keyword}"
        lines.append(f"{prefix} — {m.item.title}")
        lines.append(f"   {m.item.url}")
        lines.append(f"   Source: {m.item.source}")
        lines.append("")
    return "\n".join(lines).strip()


def _post(text: str) -> bool:
    url = _webhook_url()
    if not url:
        return False
    try:
        # Power Automate Workflows webhook expects {"text": "..."}
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
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        prefix = "🚨 URGENT — " if has_urgent else ""
        header = f"{prefix}Coverage update — {client} ({timestamp})"
        text = _format_message(header, client_matches)
        if _post(text):
            logger.info("Delivered %d items for %s to Teams", len(client_matches), client)


def deliver_digest(matches: list[MatchResult]) -> None:
    """Morning digest: group last 24 h matches by client, one message per client."""
    if not matches:
        logger.info("Digest: no matches to deliver")
        return

    by_client: dict[str, list[MatchResult]] = defaultdict(list)
    for m in matches:
        by_client[m.client].append(m)

    for client, client_matches in by_client.items():
        has_urgent = any(m.is_brief_match for m in client_matches)
        prefix = "🚨 URGENT — " if has_urgent else ""
        header = f"{prefix}Morning digest — {client} ({len(client_matches)} items, past 24 h)"
        text = _format_message(header, client_matches)
        if _post(text):
            logger.info("Digest delivered %d items for %s", len(client_matches), client)
