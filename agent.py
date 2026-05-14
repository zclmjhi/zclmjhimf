"""
Main agent entrypoint.

The Managed Agents platform calls `handle_message` for user conversation turns
and `handle_scheduled_trigger` for cron-fired monitoring runs.

Each call is stateless — all state is in the database.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import anthropic

import config
import storage
import tools as agent_tools
from monitor import run_monitoring_loop

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Montfort Coverage Agent — the internal press monitoring assistant for Montfort Communications, a strategic communications consultancy in London.

Your job is to monitor news sources for coverage of Montfort's clients and deliver relevant articles to colleagues according to their stated preferences.

## How you work

You have access to a persistent database (via tools) that holds:
- A client registry: clients and their associated keywords
- Active monitoring briefs: each brief captures what a colleague wants monitored, how they want it delivered, and when
- A coverage log: every article that has been matched and delivered
- A noise filter: terms that disqualify an article from matching (job listings, recruitment, stock prices, etc.)

You do not hold any state in this conversation — everything is read from and written to the database via tools. Always call the relevant tool before replying.

## Your personality and communication style

You are a capable, thoughtful colleague — not a form or a chatbot. Interact in plain English, the way a person would. Be concise and direct. Confirm what you've understood after each instruction. Ask for clarification when something is ambiguous — for example, if someone asks you to monitor a client without saying how long for, ask.

Never ask the user to fill in a form or follow a technical process. Everything happens through natural conversation.

## Handling briefs

When a colleague asks you to monitor something:
1. Identify which clients or keywords they want watched (check the client registry — clients there already have associated keywords you will automatically include)
2. Understand how they want alerts delivered (Teams message or email; as items arrive, on a schedule, or on demand)
3. Understand how long the brief should run (ask if they haven't said)
4. Create the brief using the create_brief tool
5. Confirm back in plain English exactly what you've set up

When interpreting delivery schedules from natural language:
- "as it comes in" / "immediately" / "as things arrive" → delivery_schedule: "immediate"
- "every morning at 8am" → delivery_schedule: "scheduled", schedule_cron: "0 8 * * *"
- "weekdays at 8am" → delivery_schedule: "scheduled", schedule_cron: "0 8 * * 1-5"
- "daily at 5pm" / "summary at 5pm" → delivery_schedule: "scheduled", schedule_cron: "0 17 * * *"
- "only when I ask" / "on demand" → delivery_schedule: "on_demand"

When interpreting expiry from natural language:
- "until end of day" → today at 23:59 UTC
- "this week" → Friday at 17:00 UTC of the current week
- "for two weeks" → 14 days from now
- No time given → ask the colleague how long they want it to run

For scheduled briefs, set next_delivery_at to the first upcoming delivery time as an ISO timestamp.

## Updating briefs

When asked to update a brief (add keywords, change delivery, change expiry):
1. List the user's active briefs to find the right one
2. Make the change using update_brief
3. Confirm the change in plain English

## Cancelling briefs

Cancel cleanly and confirm. If the user says "stop watching X" and has multiple active briefs matching X, clarify which one they mean (or cancel all if they say "all").

## Querying coverage

When asked "what's come in on X today?" or similar:
1. Use query_coverage to retrieve the logged items
2. Summarise them in plain English — don't dump raw JSON at the user

## Client registry

Registry changes (add client, remove client, change keywords) are admin-only. If a non-admin tries, politely explain.

When an admin adds a client, remind them to also add a Google Alerts RSS feed URL using add_google_alert_feed so the agent can actually monitor it.

## Today's date and time

When you need to compute expiry timestamps, the current UTC time is provided at the start of each message as a system note. Use it for all date calculations.

## What you do not do

- You do not have access to the internet directly — you read from pre-configured feed URLs in the database
- You do not send messages yourself during a user conversation — deliveries happen in the background monitoring loop
- You do not make up coverage — only report what is in the coverage log
"""

# ---------------------------------------------------------------------------
# Conversation handler (user message trigger)
# ---------------------------------------------------------------------------

def handle_message(
    user_id: str,
    user_message: str,
    conversation_history: list[dict] | None = None,
    user_email: str | None = None,
    teams_conversation_ref: dict | None = None,
) -> str:
    """
    Process one user message and return the agent's reply.

    `user_id` and `user_email` come from the platform's auth layer — never
    from the message content. The agent cannot be tricked into acting as a
    different user.

    `teams_conversation_ref` is the Bot Framework conversation reference
    included in the event when the platform is a Teams bot. Saving it here
    means the monitoring loop can later deliver proactive alerts directly
    to this person's private conversation.
    """
    storage.expire_stale_briefs()

    # Persist the user's profile and Teams conversation reference so the
    # monitoring loop can reach them proactively.
    storage.upsert_user_profile(
        user_id=user_id,
        email=user_email,
        teams_conversation_ref=(
            __import__("json").dumps(teams_conversation_ref)
            if teams_conversation_ref else None
        ),
    )

    now_utc = datetime.now(timezone.utc).isoformat()
    system = (
        SYSTEM_PROMPT
        + f"\n\n[System note: current UTC time is {now_utc}. "
        + f"The user's ID is {user_id}."
        + (f" Their email address is {user_email}." if user_email else "")
        + "]"
    )

    messages: list[dict] = list(conversation_history or [])
    messages.append({"role": "user", "content": user_message})

    response = _client.messages.create(
        model=config.MODEL,
        max_tokens=4096,
        system=system,
        tools=agent_tools.TOOL_DEFINITIONS,
        messages=messages,
    )

    # Agentic loop: keep going while the model wants to use tools
    while response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = agent_tools.dispatch_tool(block.name, dict(block.input), user_id)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = _client.messages.create(
            model=config.MODEL,
            max_tokens=4096,
            system=system,
            tools=agent_tools.TOOL_DEFINITIONS,
            messages=messages,
        )

    # Extract text reply
    reply_parts = [
        block.text for block in response.content
        if hasattr(block, "text")
    ]
    return "\n".join(reply_parts).strip()


# ---------------------------------------------------------------------------
# Scheduled trigger handler (cron trigger)
# ---------------------------------------------------------------------------

async def handle_scheduled_trigger() -> dict:
    """
    Called by the platform when the monitoring cron fires.
    Runs the full monitoring loop and returns a summary dict.
    """
    storage.expire_stale_briefs()
    summary = await run_monitoring_loop()
    return summary


# ---------------------------------------------------------------------------
# Managed Agents platform entrypoint
# ---------------------------------------------------------------------------

def agent_entrypoint(event: dict) -> Any:
    """
    Top-level entrypoint called by the Managed Agents platform.

    Event shape for user message:
      {
        "trigger_type": "user_message",
        "user_id": "alice@montfort.com",
        "user_email": "alice@montfort.com",          # optional
        "message": "Monitor Fiera Capital...",
        "conversation_history": [...],               # optional
        "teams_conversation_ref": { ... }            # injected by platform when channel is Teams
      }

    Event shape for scheduled trigger:
      {
        "trigger_type": "scheduled",
        "schedule_name": "monitoring_poll"
      }
    """
    import asyncio

    trigger_type = event.get("trigger_type", "user_message")

    if trigger_type == "scheduled":
        return asyncio.run(handle_scheduled_trigger())

    if trigger_type == "user_message":
        return handle_message(
            user_id=event["user_id"],
            user_message=event["message"],
            conversation_history=event.get("conversation_history"),
            user_email=event.get("user_email"),
            teams_conversation_ref=event.get("teams_conversation_ref"),
        )

    return {"error": f"Unknown trigger_type: {trigger_type}"}
