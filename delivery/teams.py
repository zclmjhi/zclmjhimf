"""
Microsoft Teams delivery via Bot Framework proactive messaging.

When a user first messages the agent, the Managed Agents platform passes a
conversation reference in the event. We store that reference in user_profiles.
When the monitoring loop wants to alert someone, it loads their reference and
uses the Bot Framework REST API to post directly into their private 1:1
conversation with the bot — no shared channel involved.

Each person only ever sees their own alerts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

import config
import storage
from delivery.base import AlertItem, DigestBundle


def _truncate(text: str, max_len: int = 200) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


# ---------------------------------------------------------------------------
# Adaptive Card builders (unchanged from webhook version)
# ---------------------------------------------------------------------------

def _build_item_card(item: AlertItem) -> dict:
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


# ---------------------------------------------------------------------------
# Proactive messaging via Bot Framework REST API
# ---------------------------------------------------------------------------

async def _get_bot_token() -> str | None:
    """
    Exchange the bot's App ID and password for a Bearer token from Azure AD.
    Credentials come from environment variables set by the Managed Agents platform.
    """
    app_id = config.TEAMS_BOT_APP_ID
    app_password = config.TEAMS_BOT_APP_PASSWORD
    if not app_id or not app_password:
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": app_id,
                    "client_secret": app_password,
                    "scope": "https://api.botframework.com/.default",
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]
    except Exception as exc:
        print(f"[Teams] Failed to get bot token: {exc}")
        return None


async def _post_to_conversation(conversation_ref: dict, card: dict, token: str) -> bool:
    """
    Post an Adaptive Card into an existing conversation using the stored reference.
    The conversation reference was saved when the user first messaged the bot.
    """
    service_url = conversation_ref.get("serviceUrl", "https://smba.trafficmanager.net/uk/")
    conversation_id = conversation_ref["conversation"]["id"]
    url = f"{service_url}v3/conversations/{conversation_id}/activities"

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card,
        }],
    }

    try:
        async with httpx.AsyncClient(
            timeout=15,
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return True
    except Exception as exc:
        print(f"[Teams] Failed to post to conversation: {exc}")
        return False


async def deliver_teams(
    user_id: str,
    items: list[AlertItem] | None = None,
    bundle: DigestBundle | None = None,
) -> bool:
    """
    Deliver alerts or a digest to a specific user's private Teams conversation.

    Looks up the user's stored conversation reference. If they haven't yet
    messaged the bot (no reference stored), delivery is skipped and logged.
    """
    profile = storage.get_user_profile(user_id)
    if not profile or not profile.get("teams_conversation_ref"):
        print(f"[Teams] No conversation reference for {user_id} — user has not yet messaged the bot")
        return False

    conversation_ref = json.loads(profile["teams_conversation_ref"])

    token = await _get_bot_token()
    if not token:
        print("[Teams] Could not obtain bot token — check TEAMS_BOT_APP_ID and TEAMS_BOT_APP_PASSWORD")
        return False

    if bundle is not None:
        card = _build_digest_card(bundle)
        return await _post_to_conversation(conversation_ref, card, token)

    if items:
        success = True
        for item in items:
            card = _build_item_card(item)
            ok = await _post_to_conversation(conversation_ref, card, token)
            success = success and ok
        return success

    return False


# ---------------------------------------------------------------------------
# Capture conversation reference on first contact
# ---------------------------------------------------------------------------

def save_conversation_ref(user_id: str, conversation_ref: dict) -> None:
    """
    Call this from agent.py when handling a user_message event.
    The Managed Agents platform includes the Bot Framework conversation
    reference in the event payload whenever a user messages the bot.
    """
    storage.upsert_user_profile(
        user_id=user_id,
        teams_conversation_ref=json.dumps(conversation_ref),
    )
