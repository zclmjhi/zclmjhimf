"""
Agent tool implementations.

Each function here corresponds to one tool the agent can call.
Tools are pure Python — they call storage, sources, and delivery modules.
The tool *definitions* (JSON schema for the Claude API) live in agent.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import storage
import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(data: Any = None, message: str = "") -> dict:
    result: dict = {"success": True}
    if message:
        result["message"] = message
    if data is not None:
        result["data"] = data
    return result


def _err(message: str) -> dict:
    return {"success": False, "error": message}


def _is_admin(user_id: str) -> bool:
    if not config.ADMIN_USER_IDS:
        return True  # no admin list configured — allow all (dev mode)
    return user_id in config.ADMIN_USER_IDS


# ---------------------------------------------------------------------------
# Client registry tools
# ---------------------------------------------------------------------------

def tool_list_clients() -> dict:
    clients = storage.list_clients()
    return _ok([
        {"name": c["name"], "keywords": json.loads(c["keywords"])}
        for c in clients
    ])


def tool_upsert_client(user_id: str, name: str, keywords: list[str]) -> dict:
    if not _is_admin(user_id):
        return _err("Only administrators can modify the client registry.")
    if not name.strip():
        return _err("Client name cannot be empty.")
    if not keywords:
        return _err("At least one keyword is required.")
    storage.upsert_client(name.strip(), [k.strip() for k in keywords if k.strip()])
    return _ok(message=f"Client '{name}' saved with keywords: {', '.join(keywords)}")


def tool_delete_client(user_id: str, name: str) -> dict:
    if not _is_admin(user_id):
        return _err("Only administrators can modify the client registry.")
    deleted = storage.delete_client(name)
    if not deleted:
        return _err(f"Client '{name}' not found in registry.")
    return _ok(message=f"Client '{name}' removed from registry.")


def tool_add_google_alert_feed(user_id: str, client_name: str, feed_url: str, label: str = "") -> dict:
    if not _is_admin(user_id):
        return _err("Only administrators can add feed URLs.")
    client = storage.get_client(client_name)
    if not client:
        return _err(f"Client '{client_name}' not found. Add the client first.")
    storage.add_google_alert_feed(client_name, feed_url, label)
    return _ok(message=f"Google Alerts feed added for {client_name}.")


# ---------------------------------------------------------------------------
# Brief management tools
# ---------------------------------------------------------------------------

def tool_create_brief(
    user_id: str,
    user_email: str | None,
    title: str,
    clients: list[str],
    extra_keywords: list[str],
    delivery_channel: str,
    delivery_schedule: str,
    schedule_cron: str | None,
    next_delivery_at: str | None,
    priority: bool,
    expires_at: str | None,
) -> dict:
    if not title.strip():
        return _err("Brief title cannot be empty.")
    if delivery_channel not in ("teams", "email"):
        return _err("delivery_channel must be 'teams' or 'email'.")
    if delivery_schedule not in ("immediate", "scheduled", "on_demand"):
        return _err("delivery_schedule must be 'immediate', 'scheduled', or 'on_demand'.")
    if delivery_channel == "email" and not user_email:
        return _err("Email delivery requires a user email address.")

    # Validate that clients exist in registry (warn but don't block)
    unknown = [c for c in clients if not storage.get_client(c)]
    warning = ""
    if unknown:
        warning = f" Note: {', '.join(unknown)} are not in the client registry — keyword matching will use the brief's extra_keywords only."

    brief_id = storage.create_brief(
        user_id=user_id,
        user_email=user_email,
        title=title,
        clients=clients,
        extra_keywords=extra_keywords,
        delivery_channel=delivery_channel,
        delivery_schedule=delivery_schedule,
        schedule_cron=schedule_cron,
        next_delivery_at=next_delivery_at,
        priority=priority,
        expires_at=expires_at,
    )
    return _ok(
        data={"brief_id": brief_id},
        message=f"Brief created (ID: {brief_id}).{warning}",
    )


def tool_list_active_briefs(user_id: str) -> dict:
    briefs = storage.list_active_briefs(user_id)
    result = []
    for b in briefs:
        result.append({
            "id": b["id"],
            "title": b["title"],
            "clients": json.loads(b["clients"]),
            "extra_keywords": json.loads(b["extra_keywords"]),
            "delivery_channel": b["delivery_channel"],
            "delivery_schedule": b["delivery_schedule"],
            "next_delivery_at": b["next_delivery_at"],
            "expires_at": b["expires_at"],
            "priority": bool(b["priority"]),
            "created_at": b["created_at"],
        })
    return _ok(result)


def tool_update_brief(user_id: str, brief_id: str, **changes: Any) -> dict:
    brief = storage.get_brief(brief_id)
    if not brief:
        return _err(f"Brief {brief_id} not found.")
    if brief["user_id"] != user_id:
        return _err("You can only update your own briefs.")
    if not brief["active"]:
        return _err("That brief is no longer active.")

    allowed_changes = {
        k: v for k, v in changes.items()
        if k in (
            "title", "clients", "extra_keywords", "delivery_channel",
            "delivery_schedule", "schedule_cron", "next_delivery_at",
            "priority", "expires_at",
        )
    }
    if not allowed_changes:
        return _err("No valid fields to update.")

    storage.update_brief(brief_id, **allowed_changes)
    return _ok(message=f"Brief updated.")


def tool_cancel_brief(user_id: str, brief_id: str) -> dict:
    brief = storage.get_brief(brief_id)
    if not brief:
        return _err(f"Brief {brief_id} not found.")
    if brief["user_id"] != user_id:
        return _err("You can only cancel your own briefs.")
    storage.deactivate_brief(brief_id)
    return _ok(message=f"Brief '{brief['title']}' cancelled.")


def tool_cancel_all_briefs(user_id: str) -> dict:
    count = storage.deactivate_all_briefs_for_user(user_id)
    if count == 0:
        return _ok(message="You have no active briefs to cancel.")
    return _ok(message=f"{count} brief{'s' if count != 1 else ''} cancelled.")


def tool_query_coverage(
    user_id: str,
    brief_id: str | None = None,
    since: str | None = None,
    client_name: str | None = None,
) -> dict:
    # Verify brief belongs to user if brief_id given
    if brief_id:
        brief = storage.get_brief(brief_id)
        if not brief or brief["user_id"] != user_id:
            return _err("Brief not found or does not belong to you.")

    items = storage.query_coverage_log(
        brief_id=brief_id,
        since=since,
        client_name=client_name,
    )
    return _ok(items)


# ---------------------------------------------------------------------------
# Noise filter tools
# ---------------------------------------------------------------------------

def tool_list_noise_terms() -> dict:
    return _ok(storage.list_noise_terms())


def tool_add_noise_term(user_id: str, term: str) -> dict:
    if not _is_admin(user_id):
        return _err("Only administrators can modify the noise filter.")
    storage.add_noise_term(term.strip().lower())
    return _ok(message=f"'{term}' added to noise filter.")


def tool_remove_noise_term(user_id: str, term: str) -> dict:
    if not _is_admin(user_id):
        return _err("Only administrators can modify the noise filter.")
    removed = storage.remove_noise_term(term)
    if not removed:
        return _err(f"'{term}' is not in the noise filter.")
    return _ok(message=f"'{term}' removed from noise filter.")


# ---------------------------------------------------------------------------
# Tool definitions for the Claude API (JSON schema format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "list_clients",
        "description": "List all clients and their keywords in the client registry.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "upsert_client",
        "description": (
            "Add a new client to the registry, or update the keywords of an existing one. "
            "Admin only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Client name"},
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of keywords to monitor for this client",
                },
            },
            "required": ["name", "keywords"],
        },
    },
    {
        "name": "delete_client",
        "description": "Remove a client from the registry. Admin only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Client name to remove"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "add_google_alert_feed",
        "description": (
            "Register a Google Alerts RSS feed URL for a client. "
            "The URL is obtained by setting up a Google Alert and choosing RSS delivery. "
            "Admin only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string"},
                "feed_url": {"type": "string", "description": "Google Alerts RSS feed URL"},
                "label": {"type": "string", "description": "Optional human-readable label for this feed"},
            },
            "required": ["client_name", "feed_url"],
        },
    },
    {
        "name": "create_brief",
        "description": (
            "Create a new monitoring brief for the current user. "
            "Use this when the user asks the agent to monitor/watch for coverage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short human-readable title for this brief"},
                "clients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Client names from the registry to monitor",
                },
                "extra_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional keywords not tied to a specific registered client (e.g. a person's name)",
                },
                "delivery_channel": {
                    "type": "string",
                    "enum": ["teams", "email"],
                    "description": "How to deliver alerts. Default is 'teams'.",
                },
                "delivery_schedule": {
                    "type": "string",
                    "enum": ["immediate", "scheduled", "on_demand"],
                    "description": (
                        "'immediate' = alert as each item arrives; "
                        "'scheduled' = digest at specified time(s); "
                        "'on_demand' = only deliver when user asks."
                    ),
                },
                "schedule_cron": {
                    "type": "string",
                    "description": "Cron expression for scheduled delivery (e.g. '0 8 * * 1-5' for weekdays at 8am). Only for delivery_schedule='scheduled'.",
                },
                "next_delivery_at": {
                    "type": "string",
                    "description": "ISO timestamp of next scheduled delivery. Used to track when to send the next digest.",
                },
                "priority": {
                    "type": "boolean",
                    "description": "Mark this brief as priority — alerts will carry an URGENT flag.",
                },
                "expires_at": {
                    "type": "string",
                    "description": "ISO timestamp when this brief should automatically expire. Null for open-ended.",
                },
                "user_email": {
                    "type": "string",
                    "description": "User's email address. Required if delivery_channel is 'email'.",
                },
            },
            "required": ["title", "clients", "extra_keywords", "delivery_channel", "delivery_schedule", "priority"],
        },
    },
    {
        "name": "list_active_briefs",
        "description": "List all active monitoring briefs for the current user.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "update_brief",
        "description": "Update one or more fields of an existing brief.",
        "input_schema": {
            "type": "object",
            "properties": {
                "brief_id": {"type": "string"},
                "title": {"type": "string"},
                "clients": {"type": "array", "items": {"type": "string"}},
                "extra_keywords": {"type": "array", "items": {"type": "string"}},
                "delivery_channel": {"type": "string", "enum": ["teams", "email"]},
                "delivery_schedule": {"type": "string", "enum": ["immediate", "scheduled", "on_demand"]},
                "schedule_cron": {"type": "string"},
                "next_delivery_at": {"type": "string"},
                "priority": {"type": "boolean"},
                "expires_at": {"type": "string"},
            },
            "required": ["brief_id"],
        },
    },
    {
        "name": "cancel_brief",
        "description": "Cancel a single active monitoring brief.",
        "input_schema": {
            "type": "object",
            "properties": {
                "brief_id": {"type": "string"},
            },
            "required": ["brief_id"],
        },
    },
    {
        "name": "cancel_all_briefs",
        "description": "Cancel all active monitoring briefs for the current user.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "query_coverage",
        "description": (
            "Query what coverage has been found and logged. "
            "Use this when the user asks what has come in for a brief or client."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "brief_id": {"type": "string", "description": "Filter by brief ID"},
                "since": {"type": "string", "description": "ISO timestamp — only return items logged after this time"},
                "client_name": {"type": "string", "description": "Filter by client name"},
            },
            "required": [],
        },
    },
    {
        "name": "list_noise_terms",
        "description": "List the current noise filter terms.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "add_noise_term",
        "description": "Add a term to the noise filter. Items whose title contains this term will be discarded. Admin only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "term": {"type": "string"},
            },
            "required": ["term"],
        },
    },
    {
        "name": "remove_noise_term",
        "description": "Remove a term from the noise filter. Admin only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "term": {"type": "string"},
            },
            "required": ["term"],
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatch: map tool name → function call
# ---------------------------------------------------------------------------

def dispatch_tool(name: str, inputs: dict, user_id: str) -> dict:
    """
    Route a tool call from the agent to the correct implementation function.
    `user_id` is injected server-side — never from the LLM's inputs.
    """
    if name == "list_clients":
        return tool_list_clients()
    if name == "upsert_client":
        return tool_upsert_client(user_id, inputs["name"], inputs["keywords"])
    if name == "delete_client":
        return tool_delete_client(user_id, inputs["name"])
    if name == "add_google_alert_feed":
        return tool_add_google_alert_feed(
            user_id, inputs["client_name"], inputs["feed_url"], inputs.get("label", "")
        )
    if name == "create_brief":
        return tool_create_brief(
            user_id=user_id,
            user_email=inputs.get("user_email"),
            title=inputs["title"],
            clients=inputs.get("clients", []),
            extra_keywords=inputs.get("extra_keywords", []),
            delivery_channel=inputs.get("delivery_channel", "teams"),
            delivery_schedule=inputs["delivery_schedule"],
            schedule_cron=inputs.get("schedule_cron"),
            next_delivery_at=inputs.get("next_delivery_at"),
            priority=inputs.get("priority", False),
            expires_at=inputs.get("expires_at"),
        )
    if name == "list_active_briefs":
        return tool_list_active_briefs(user_id)
    if name == "update_brief":
        brief_id = inputs.pop("brief_id")
        return tool_update_brief(user_id, brief_id, **inputs)
    if name == "cancel_brief":
        return tool_cancel_brief(user_id, inputs["brief_id"])
    if name == "cancel_all_briefs":
        return tool_cancel_all_briefs(user_id)
    if name == "query_coverage":
        return tool_query_coverage(
            user_id,
            brief_id=inputs.get("brief_id"),
            since=inputs.get("since"),
            client_name=inputs.get("client_name"),
        )
    if name == "list_noise_terms":
        return tool_list_noise_terms()
    if name == "add_noise_term":
        return tool_add_noise_term(user_id, inputs["term"])
    if name == "remove_noise_term":
        return tool_remove_noise_term(user_id, inputs["term"])

    return _err(f"Unknown tool: {name}")
