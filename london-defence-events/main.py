#!/usr/bin/env python3
"""
London Defence Events Tracker – main entry point.

Usage:
    python main.py              # Full run: discover, score, deduplicate, email
    python main.py --no-email   # Run without sending email (prints digest to stdout)
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

import config
from discovery import discover_events
from scoring import score_events
from deduplication import filter_new
from email_sender import build_html, send_digest

# ---------------------------------------------------------------------------
# Logging setup
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


def main() -> None:
    parser = argparse.ArgumentParser(description="London Defence Events Tracker")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email")
    args = parser.parse_args()

    load_dotenv()

    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set. Exiting.")
        sys.exit(1)

    # 1. Discover events
    logger.info("=== Starting event discovery ===")
    raw_events = discover_events()
    total_raw = len(raw_events)

    if not raw_events:
        logger.info("No events found. Exiting.")
        return

    # 2. Deduplicate
    logger.info("=== Deduplicating ===")
    new_events, duplicates = filter_new(raw_events)

    if not new_events:
        logger.info("All events already seen. Nothing new to report.")
        return

    # 3. Score
    logger.info("=== Scoring %d new events ===", len(new_events))
    scored_events = score_events(new_events)

    # 4. Bucket by relevance
    high = [e for e in scored_events if e.get("weighted_score", 0) >= config.HIGH_RELEVANCE_MIN_SCORE]
    radar = [
        e for e in scored_events
        if config.RADAR_MIN_SCORE <= e.get("weighted_score", 0) < config.HIGH_RELEVANCE_MIN_SCORE
    ]
    below = total_raw - len(high) - len(radar)

    logger.info(
        "Results: %d high-relevance, %d on-radar, %d below threshold, %d duplicates",
        len(high), len(radar), below, duplicates,
    )

    # 5. Email or print
    if args.no_email:
        html = build_html(high, radar, total_raw, duplicates)
        print("\n" + "=" * 60)
        print("DIGEST PREVIEW (HTML saved to digest_preview.html)")
        print("=" * 60)
        with open("digest_preview.html", "w") as f:
            f.write(html)
        # Also print a plain-text summary
        for section, events in [("HIGH RELEVANCE", high), ("ON THE RADAR", radar)]:
            print(f"\n--- {section} ---")
            for e in events:
                print(f"  [{e.get('weighted_score', '?')}/10] {e.get('name', '?')}")
                print(f"         Date: {e.get('date', '?')}  |  Venue: {e.get('venue', '?')}")
                print(f"         {e.get('relevance_summary', '')}")
                print(f"         {e.get('url', '')}")
                print()
        if not high and not radar:
            print("\n  No events met the minimum score threshold.")
    else:
        sent = send_digest(high, radar, total_raw, duplicates)
        if not sent:
            logger.warning("Email not sent – printing digest to stdout instead")
            html = build_html(high, radar, total_raw, duplicates)
            with open("digest_preview.html", "w") as f:
                f.write(html)
            logger.info("HTML digest saved to digest_preview.html")

    logger.info("=== Run complete ===")


if __name__ == "__main__":
    main()
