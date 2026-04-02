#!/usr/bin/env python3
"""
London Defence Events Tracker – main entry point.

Run:  python main.py           # full discover + score + email run
      python main.py --dry-run # discover + score, print results, skip email
"""

import argparse
import json
import logging
import os
import sys

from dotenv import load_dotenv

import config
from discovery import search_events
from scoring import score_events
from deduplication import filter_new
from email_sender import build_html, send_digest

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

SCORED_EVENTS_FILE = "scored_events.json"


def _save_scored_events(new_events: list[dict]) -> None:
    """Append scored events to the persistent scored_events.json."""
    existing = []
    if os.path.exists(SCORED_EVENTS_FILE):
        try:
            with open(SCORED_EVENTS_FILE, "r") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = []
    # Dedupe by name+date
    seen = {(e.get("name", ""), e.get("date", "")) for e in existing}
    for ev in new_events:
        key = (ev.get("name", ""), ev.get("date", ""))
        if key not in seen:
            existing.append(ev)
            seen.add(key)
    existing.sort(key=lambda e: e.get("relevance_score", 0), reverse=True)
    with open(SCORED_EVENTS_FILE, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    logger.info("Saved %d scored events to %s", len(existing), SCORED_EVENTS_FILE)


def main(dry_run: bool = False) -> None:
    logger.info("=== Defence Events Tracker – starting run ===")

    # 1. Discover events
    logger.info("Phase 1: Event discovery")
    raw_events = search_events()
    total_scanned = len(raw_events)
    logger.info("Discovered %d raw events", total_scanned)

    if not raw_events:
        logger.info("No events found – exiting")
        return

    # 2. Deduplicate
    logger.info("Phase 2: Deduplication")
    new_events = filter_new(raw_events)
    logger.info("%d new events after deduplication", len(new_events))

    if not new_events:
        logger.info("All events already seen – exiting")
        return

    # 3. Score
    logger.info("Phase 3: Scoring %d events", len(new_events))
    scored_events = score_events(new_events)

    # 3b. Persist scored events for dashboard
    _save_scored_events(scored_events)

    # 4. Partition into headline / radar / filtered-out
    headline = [e for e in scored_events if e.get("relevance_score", 0) >= config.MIN_SCORE_HEADLINE]
    radar = [
        e
        for e in scored_events
        if config.MIN_SCORE_ON_RADAR <= e.get("relevance_score", 0) < config.MIN_SCORE_HEADLINE
    ]
    filtered_out = total_scanned - len(headline) - len(radar)

    logger.info(
        "Results: %d headline, %d on-radar, %d filtered out",
        len(headline),
        len(radar),
        filtered_out,
    )

    # Print summary to console
    print("\n" + "=" * 70)
    print(f"  HEADLINE EVENTS ({len(headline)})")
    print("=" * 70)
    for e in headline:
        print(f"  [{e.get('relevance_score', 0):.1f}] {e.get('name')}  –  {e.get('date')}")
        print(f"         {e.get('venue', 'Venue TBC')}")
        print(f"         {e.get('relevance_summary', '')}")
        print(f"         {e.get('url', '')}")
        print()

    if radar:
        print("-" * 70)
        print(f"  ON THE RADAR ({len(radar)})")
        print("-" * 70)
        for e in radar:
            print(f"  [{e.get('relevance_score', 0):.1f}] {e.get('name')}  –  {e.get('date')}")
            print(f"         {e.get('relevance_summary', '')}")
            print()

    print(f"Total scanned: {total_scanned} | Filtered out: {filtered_out}")
    print("=" * 70 + "\n")

    # 5. Email
    if dry_run:
        logger.info("Dry run – skipping email. Writing preview to digest_preview.html")
        html = build_html(headline, radar, total_scanned, filtered_out)
        with open("digest_preview.html", "w") as f:
            f.write(html)
        print("HTML preview saved to digest_preview.html")
    else:
        if headline or radar:
            sent = send_digest(headline, radar, total_scanned, filtered_out)
            if not sent:
                logger.info("Email not sent (SMTP not configured or error). Writing preview.")
                html = build_html(headline, radar, total_scanned, filtered_out)
                with open("digest_preview.html", "w") as f:
                    f.write(html)
                print("HTML preview saved to digest_preview.html")
        else:
            logger.info("No events above threshold – no email sent")

    logger.info("=== Run complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="London Defence Events Tracker")
    parser.add_argument("--dry-run", action="store_true", help="Skip email, print results only")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
