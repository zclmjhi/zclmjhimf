"""
Microsoft Teams delivery via Incoming Webhook.
Formats each alert as an Adaptive Card.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

import config
from delivery.base import AlertItem, DigestBundle


def _truncate(text: str, max_len: int = 200) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _build_item_card(item: AlertItem) -> dict:
    """Adaptive Card body for a single coverage item."""
    header_parts = [f"**{item.client_name}**"]
    if item.is_priority:
        header_parts.append("🔴 URGENT")
    if item.is_update:
        header_parts.append("_(update to previously seen article)_")

    facts = [{"title": "Source", "value": item.source_name or "Unknown"}]
    if item.keyword_matched:
        facts.append({"title": "Matched", "value": item.keyword_matched})
    if item.published_at:
        facts.append({"title": "Published", "value": item.published_at[:10]})

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": " · ".join(header_parts),
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": f"[{_truncate(item.headline, 160)}]({item.url})",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": facts,
                "separator": True,
            },
        ],
    }
    if item.summary:
        card["body"].insert(2, {
            "type": "TextBlock",
            "text": _truncate(item.summary, 200),
            "isSubtle": True,
            "wrap": True,
            "size": "Small",
        })
    return card


def _build_digest_card(bundle: DigestBundle) -> dict:
    """Adaptive Card body for a scheduled digest."""
    now = datetime.now(timezone.utc).strftime("%d %b %Y")
    body = [
        {
            "type": "TextBlock",
            "text": f"**Coverage digest — {bundle.brief_title}** · {now}",
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": f"{len(bundle.items)} item{'s' if len(bundle.items) != 1 else ''} found {bundle.period_label}",
            "isSubtle": True,
        },
    ]
    for item in bundle.items:
        flags = []
        if item.is_priority:
            flags.append("🔴 URGENT")
        if item.is_update:
            flags.append("_(update)_")
        flag_str = ("  " + "  ".join(flags)) if flags else ""
        body.append({"type": "TextBlock", "text": "---", "separator": True})
        body.append({
            "type": "TextBlock",
            "text": f"**{item.client_name}**" + flag_str,
            "weight": "Bolder",
            "wrap": True,
        })
        body.append({
            "type": "TextBlock",
            "text": f"[{_truncate(item.headline, 160)}]({item.url})",
            "wrap": True,
        })
        body.append({
            "type": "FactSet",
            "facts": [
                {"title": "Source", "value": item.source_name or "Unknown"},
                {"title": "Matched", "value": item.keyword_matched},
            ],
        })
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }


async def deliver_teams(
    items: list[AlertItem] | None = None,
    bundle: DigestBundle | None = None,
    webhook_url: str | None = None,
) -> bool:
    """
    Send one or more alerts to Teams via Incoming Webhook.
    Pass `items` for immediate per-item delivery, or `bundle` for a digest.
    Returns True on success.
    """
    url = webhook_url or config.TEAMS_WEBHOOK_URL
    if not url:
        print("[Teams] No webhook URL configured — skipping delivery")
        return False

    if bundle is not None:
        card = _build_digest_card(bundle)
        payload = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}
        return await _post(url, payload)

    if items:
        # For immediate delivery, post one card per item
        success = True
        for item in items:
            card = _build_item_card(item)
            payload = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}
            ok = await _post(url, payload)
            success = success and ok
        return success

    return False


async def _post(url: str, payload: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return True
    except Exception as exc:
        print(f"[Teams] Delivery failed: {exc}")
        return False
