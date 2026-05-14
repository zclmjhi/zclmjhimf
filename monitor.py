"""
Monitoring loop — called on every scheduled trigger.

Steps:
1. Fetch items from all registered sources
2. Clean and deduplicate URLs
3. Apply noise filter
4. Match items against active briefs
5. For each match:
   a. If item is new → mark seen, log, queue for delivery
   b. If item URL is known but content changed → flag as update, log, queue for delivery
   c. If item is already seen with same hash → skip
6. Dispatch queued items per brief's delivery preferences
7. For scheduled briefs whose next_delivery_at has passed, send digest and advance schedule
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import storage
from delivery.base import AlertItem, DigestBundle
from delivery.teams import deliver_teams
from delivery.email import deliver_email
from sources import REGISTERED_SOURCES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _next_cron_time(cron_expr: str, after: datetime) -> datetime | None:
    """
    Compute the next fire time for a cron expression after `after`.
    Supports the subset used by this agent:
      "0 8 * * *"       — every day at 08:00 UTC
      "0 8 * * 1-5"     — weekdays at 08:00 UTC
      "0 17 * * *"      — every day at 17:00 UTC
      "*/5 * * * *"     — every 5 minutes (for testing)
    Uses a simple forward scan (max 8 days) for correctness without a cron library.
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return None
    minute_s, hour_s, _dom, _month, dow_s = parts

    def _parse_field(field: str, lo: int, hi: int) -> list[int]:
        if field == "*":
            return list(range(lo, hi + 1))
        if field.startswith("*/"):
            step = int(field[2:])
            return list(range(lo, hi + 1, step))
        if "-" in field:
            a, b = field.split("-")
            return list(range(int(a), int(b) + 1))
        return [int(field)]

    minutes = _parse_field(minute_s, 0, 59)
    hours = _parse_field(hour_s, 0, 23)
    dows = _parse_field(dow_s, 0, 6)  # 0=Sunday, 6=Saturday

    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(8 * 24 * 60):  # scan up to 8 days
        if candidate.weekday() in [d - 1 for d in dows if d > 0] or 0 in dows:
            if candidate.hour in hours and candidate.minute in minutes:
                return candidate
        candidate += timedelta(minutes=1)
    return None


def _is_noisy(headline: str, noise_terms: list[str]) -> bool:
    lower = headline.lower()
    return any(term in lower for term in noise_terms)


def _keywords_for_brief(brief: dict) -> list[str]:
    """Collect all keywords this brief should match against."""
    keywords: list[str] = []
    for client_name in json.loads(brief["clients"]):
        keywords.extend(storage.get_client_keywords(client_name))
    keywords.extend(json.loads(brief["extra_keywords"]))
    return [k.lower() for k in keywords if k.strip()]


def _matches(item_text: str, keywords: list[str]) -> str | None:
    """Return the first matching keyword, or None."""
    lower = item_text.lower()
    for kw in keywords:
        if kw in lower:
            return kw
    return None


# ---------------------------------------------------------------------------
# Delivery dispatch
# ---------------------------------------------------------------------------

async def _deliver_item(item: AlertItem, brief: dict) -> None:
    channel = brief["delivery_channel"]
    user_email = brief.get("user_email")

    if channel == "teams":
        await deliver_teams(items=[item])
    elif channel == "email" and user_email:
        await deliver_email(to_email=user_email, items=[item])

    storage.log_coverage(
        brief_id=item.brief_id,
        client_name=item.client_name,
        keyword_matched=item.keyword_matched,
        headline=item.headline,
        url=item.url,
        source_name=item.source_name,
        published_at=item.published_at,
        delivery_channel=channel,
        is_update=item.is_update,
    )


async def _deliver_digest(brief: dict, items: list[AlertItem]) -> None:
    if not items:
        return
    channel = brief["delivery_channel"]
    user_email = brief.get("user_email")

    bundle = DigestBundle(
        brief_id=brief["id"],
        brief_title=brief["title"],
        user_id=brief["user_id"],
        user_email=user_email,
        delivery_channel=channel,
        items=items,
        period_label="since last digest",
    )

    if channel == "teams":
        await deliver_teams(bundle=bundle)
    elif channel == "email" and user_email:
        await deliver_email(to_email=user_email, bundle=bundle)

    for item in items:
        storage.log_coverage(
            brief_id=item.brief_id,
            client_name=item.client_name,
            keyword_matched=item.keyword_matched,
            headline=item.headline,
            url=item.url,
            source_name=item.source_name,
            published_at=item.published_at,
            delivery_channel=channel,
            is_update=item.is_update,
        )


# ---------------------------------------------------------------------------
# Per-brief match accumulator
# ---------------------------------------------------------------------------

class _BriefAccumulator(NamedTuple):
    brief: dict
    immediate_items: list[AlertItem]
    queued_items: list[AlertItem]   # for scheduled digests, held until delivery time


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run_monitoring_loop() -> dict:
    """
    Fetch all sources, match against active briefs, deliver.
    Returns a summary dict for logging.
    """
    now = _now()
    noise_terms = storage.list_noise_terms()
    active_briefs = storage.list_active_briefs()

    if not active_briefs:
        return {"status": "ok", "message": "No active briefs", "items_processed": 0, "items_delivered": 0}

    # Fetch from all sources concurrently
    fetch_tasks = [src.fetch() for src in REGISTERED_SOURCES]
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    all_items = []
    for result in results:
        if isinstance(result, Exception):
            print(f"[monitor] Source fetch error: {result}")
        else:
            all_items.extend(result)

    items_processed = len(all_items)
    items_delivered = 0

    # Per-brief accumulators for scheduled digests
    scheduled_queues: dict[str, list[AlertItem]] = {
        b["id"]: [] for b in active_briefs if b["delivery_schedule"] == "scheduled"
    }

    for raw_item in all_items:
        # Noise filter
        if _is_noisy(raw_item.headline, noise_terms):
            continue

        # Seen-item check
        existing = storage.get_seen_item(raw_item.url)
        is_update = False

        if existing:
            if not storage.has_content_changed(raw_item.url, raw_item.content_hash):
                # Already seen, no change — skip entirely
                continue
            # Content changed — it's an update
            is_update = True

        # Mark/update the seen record
        storage.mark_seen(raw_item.url, raw_item.content_hash, raw_item.last_modified)

        # Determine the canonical client name for this item
        # Feed items from Google Alerts carry client_name in extra{}
        feed_client = raw_item.extra.get("client_name", "")

        # Match against every active brief
        for brief in active_briefs:
            keywords = _keywords_for_brief(brief)
            if not keywords:
                continue

            search_text = raw_item.headline + " " + raw_item.summary
            matched_kw = _matches(search_text, keywords)
            if not matched_kw:
                continue

            # Determine client name for this match
            client_name = feed_client or matched_kw

            alert = AlertItem(
                brief_id=brief["id"],
                client_name=client_name,
                keyword_matched=matched_kw,
                headline=raw_item.headline,
                url=raw_item.url,
                source_name=raw_item.source_name,
                published_at=raw_item.published_at,
                is_update=is_update,
                is_priority=bool(brief.get("priority")),
                summary=raw_item.summary,
            )

            schedule = brief["delivery_schedule"]

            if schedule == "immediate":
                await _deliver_item(alert, brief)
                items_delivered += 1

            elif schedule == "scheduled":
                scheduled_queues[brief["id"]].append(alert)

            # on_demand: do not deliver; items are only in coverage log when
            # the monitoring loop calls log_coverage. For on_demand briefs we
            # log without delivering so query_coverage can return them.
            elif schedule == "on_demand":
                storage.log_coverage(
                    brief_id=alert.brief_id,
                    client_name=alert.client_name,
                    keyword_matched=alert.keyword_matched,
                    headline=alert.headline,
                    url=alert.url,
                    source_name=alert.source_name,
                    published_at=alert.published_at,
                    delivery_channel="on_demand",
                    is_update=alert.is_update,
                )

    # Handle scheduled digest delivery
    for brief in active_briefs:
        if brief["delivery_schedule"] != "scheduled":
            continue

        next_delivery = _parse_iso(brief.get("next_delivery_at"))
        if next_delivery is None or now < next_delivery:
            continue

        # Time has come — deliver queued items
        queued = scheduled_queues.get(brief["id"], [])
        if queued:
            await _deliver_digest(brief, queued)
            items_delivered += len(queued)

        # Advance next_delivery_at
        cron = brief.get("schedule_cron")
        if cron:
            next_time = _next_cron_time(cron, now)
            next_iso = next_time.isoformat() if next_time else None
        else:
            next_iso = None  # one-shot; don't reschedule

        storage.update_brief(brief["id"], next_delivery_at=next_iso)

    return {
        "status": "ok",
        "timestamp": now.isoformat(),
        "items_processed": items_processed,
        "items_delivered": items_delivered,
        "active_briefs": len(active_briefs),
    }
