"""
Event discovery via Anthropic API with web search.
"""

import json
import logging
import random
from datetime import date

import anthropic

import config

logger = logging.getLogger(__name__)


def _build_search_prompt(query: str) -> str:
    today = date.today().isoformat()
    sources_block = "\n".join(
        f"- {cat}: {', '.join(orgs)}"
        for cat, orgs in config.SOURCE_CATEGORIES.items()
    )
    return f"""Today is {today}. Search the web for: "{query}"

Find upcoming defence, national security, and defence-technology events in London and the UK.

Relevant source organisations include:
{sources_block}

For every event you find, return a JSON array where each element has these fields:
- "name": event name
- "date": event date or date range (ISO format or human-readable)
- "venue": venue / location (or "Online" / "TBC")
- "url": registration or info link
- "organiser": who is hosting it
- "description": 2-3 sentence summary of the event
- "speakers": notable speakers if listed (comma-separated string, or "Not announced")

Return ONLY the JSON array – no markdown fences, no commentary. If you find no events, return an empty array: []"""


def discover_events() -> list[dict]:
    """Run a batch of web-search queries and return raw event dicts."""
    client = anthropic.Anthropic()

    queries = random.sample(
        config.SEARCH_QUERIES,
        min(config.QUERIES_PER_RUN, len(config.SEARCH_QUERIES)),
    )
    logger.info("Running %d search queries this run", len(queries))

    all_events: list[dict] = []

    for query in queries:
        logger.info("Searching: %s", query)
        try:
            response = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=4096,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
                messages=[{"role": "user", "content": _build_search_prompt(query)}],
            )

            # Extract text from the response
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text

            if not text.strip():
                logger.warning("Empty response for query: %s", query)
                continue

            # Strip markdown fences if present
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[1:])
            if cleaned.endswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[:-1])
            cleaned = cleaned.strip()

            events = json.loads(cleaned)
            if isinstance(events, list):
                logger.info("Found %d events for query: %s", len(events), query)
                all_events.extend(events)
            else:
                logger.warning("Response was not a list for query: %s", query)

        except json.JSONDecodeError:
            logger.warning("Could not parse JSON from response for query: %s", query)
            logger.debug("Raw text: %s", text[:500] if text else "(empty)")
        except anthropic.APIError as exc:
            logger.error("API error for query '%s': %s", query, exc)

    logger.info("Total raw events discovered: %d", len(all_events))
    return all_events
