"""
Event discovery via Anthropic API with web search.
"""

import json
import logging
import random
from datetime import datetime

import anthropic

import config

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
You are an expert research assistant specialising in UK defence, national security, \
and defence technology events.

Today's date is {today}.

Using the web search results, extract every upcoming defence and defence-tech event \
in London or elsewhere in the UK that you can find. Focus on events from these source \
categories: {sources}

For EACH event, return a JSON object with these fields:
- "name": event title (string)
- "date": event date or date range as written (string, e.g. "15 May 2026" or "12-14 June 2026")
- "date_iso": best-effort ISO date for sorting, use the start date (string, YYYY-MM-DD or null)
- "venue": venue name and city (string or null)
- "organiser": hosting organisation (string or null)
- "url": registration or info link (string or null)
- "description": 1-2 sentence factual description (string)
- "speakers_noted": any notable speakers mentioned (list of strings, can be empty)
- "source_category": which category this came from (string)

Return ONLY a JSON array of event objects. If you find no events, return an empty array [].
Do not include any commentary outside the JSON array.
"""


def _build_source_summary() -> str:
    parts = []
    for category, sources in config.SOURCE_CATEGORIES.items():
        parts.append(f"{category.replace('_', ' ').title()}: {', '.join(sources)}")
    return "; ".join(parts)


def _select_queries() -> list[str]:
    """Randomly sample queries for this run to vary coverage."""
    n = min(config.QUERIES_PER_RUN, len(config.SEARCH_QUERIES))
    return random.sample(config.SEARCH_QUERIES, n)


def search_events() -> list[dict]:
    """Run multiple web-search-backed queries and return de-duplicated raw events."""
    client = anthropic.Anthropic()
    today = datetime.now().strftime("%Y-%m-%d")
    source_summary = _build_source_summary()
    queries = _select_queries()

    all_events: list[dict] = []
    seen_names: set[str] = set()

    for query in queries:
        logger.info("Searching: %s", query)
        try:
            events = _run_search_query(client, query, today, source_summary)
            for ev in events:
                norm = (ev.get("name") or "").strip().lower()
                if norm and norm not in seen_names:
                    seen_names.add(norm)
                    all_events.append(ev)
            logger.info("  -> found %d new events (total so far: %d)", len(events), len(all_events))
        except Exception:
            logger.exception("Error during search query: %s", query)

    logger.info("Discovery complete: %d unique events from %d queries", len(all_events), len(queries))
    return all_events


def _run_search_query(
    client: anthropic.Anthropic,
    query: str,
    today: str,
    source_summary: str,
) -> list[dict]:
    """Execute a single web-search query and parse the resulting events."""
    user_message = (
        f"Search the web for: {query}\n\n"
        "Find all upcoming defence, national security, and defence technology "
        "events in London and the UK. Include conferences, summits, roundtables, "
        "panel discussions, networking events, and webinars."
    )

    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=4096,
        system=EXTRACTION_PROMPT.format(today=today, sources=source_summary),
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": user_message}],
    )

    # Extract the final text block from the response
    text = ""
    for block in response.content:
        if block.type == "text":
            text = block.text

    return _parse_events_json(text)


def _parse_events_json(text: str) -> list[dict]:
    """Best-effort extraction of a JSON array from model output."""
    # Try direct parse first
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Try to find a JSON array in the text
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start : end + 1])
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse events JSON from response (length=%d)", len(text))
    return []
