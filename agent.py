"""
Coverage monitoring agent — main orchestrator.

Usage:
    python agent.py              # standard run: immediate delivery
    python agent.py --digest     # morning digest: group last 24 h by client
    python agent.py --dry-run    # fetch + match but do not post to Teams or update logs
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from deduplicator import deduplicate
from handlers.base import BaseHandler
from handlers.google_alerts import GoogleAlertsHandler
from handlers.inbox import InboxHandler
from matcher import MatchResult, match_items
from teams_delivery import deliver_digest, deliver_immediate

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agent")

_REGISTRY_PATH = Path(__file__).parent / "config" / "registry.json"
_LOG_PATH = Path(__file__).parent / "data" / "coverage_log.json"

# ─── Handler Registry ────────────────────────────────────────────────────────
# To add a new source: import the handler class and append it here.
# Nothing else in this file or elsewhere needs to change.
HANDLER_CLASSES: list[type[BaseHandler]] = [
    GoogleAlertsHandler,
    InboxHandler,
    # ThirdPartyApiHandler,  # <- add future handlers here
]
# ─────────────────────────────────────────────────────────────────────────────


def _load_registry() -> dict:
    with _REGISTRY_PATH.open() as fh:
        return json.load(fh)


def _load_log() -> list:
    if _LOG_PATH.exists():
        try:
            with _LOG_PATH.open() as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _append_log(matches: list[MatchResult], log: list, dry_run: bool) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for m in matches:
        log.append(
            {
                "timestamp": now,
                "source": m.item.source,
                "headline": m.item.title,
                "url": m.item.url,
                "matched_client": m.client,
                "matched_keyword": m.keyword,
                "is_brief_match": m.is_brief_match,
            }
        )
    if not dry_run:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("w") as fh:
            json.dump(log, fh, indent=2)


def _digest_matches_from_log(log: list) -> list[MatchResult]:
    """Reconstruct MatchResult objects from the last 24 h of the log for digest mode."""
    from datetime import timedelta
    from handlers.base import NormalisedItem

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    results: list[MatchResult] = []
    for entry in log:
        ts = datetime.fromisoformat(entry["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            continue
        item = NormalisedItem(
            title=entry["headline"],
            url=entry["url"],
            source=entry["source"],
            published_at=ts,
        )
        results.append(
            MatchResult(
                item=item,
                client=entry["matched_client"],
                keyword=entry["matched_keyword"],
                notify_channel="",
                is_brief_match=entry.get("is_brief_match", False),
            )
        )
    return results


def run(digest: bool = False, dry_run: bool = False) -> None:
    logger.info("=== Coverage agent starting (digest=%s, dry_run=%s) ===", digest, dry_run)

    registry = _load_registry()
    log = _load_log()

    if digest:
        # Digest mode: deliver from log, no new fetching required
        digest_matches = _digest_matches_from_log(log)
        logger.info("Digest: %d matches from the last 24 h", len(digest_matches))
        if not dry_run:
            deliver_digest(digest_matches)
        logger.info("=== Digest complete ===")
        return

    # ── Standard run ──────────────────────────────────────────────────────────
    all_items = []
    for HandlerClass in HANDLER_CLASSES:
        handler = HandlerClass(config=registry)
        try:
            items = handler.fetch()
            logger.info("%s returned %d items", HandlerClass.name, len(items))
            all_items.extend(items)
        except Exception as exc:
            logger.error("Handler %s raised an unexpected error: %s", HandlerClass.name, exc)

    logger.info("Total items before deduplication: %d", len(all_items))

    new_items = deduplicate(all_items) if not dry_run else all_items
    logger.info("New items after deduplication: %d", len(new_items))

    matches = match_items(new_items, registry)
    logger.info("Matches: %d", len(matches))

    if matches:
        _append_log(matches, log, dry_run)
        if not dry_run:
            deliver_immediate(matches)
    else:
        logger.info("No matches this run — nothing to deliver")

    logger.info("=== Run complete ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="Coverage monitoring agent")
    parser.add_argument(
        "--digest",
        action="store_true",
        help="Morning digest mode: deliver last 24 h from log grouped by client",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and match but do not post to Teams or persist data",
    )
    args = parser.parse_args()
    run(digest=args.digest, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
