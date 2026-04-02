"""
Relevance scoring for discovered events using Claude.
"""

import json
import logging
import time
from datetime import datetime

import anthropic

import config

logger = logging.getLogger(__name__)

SCORING_PROMPT = """\
You are a scoring assistant for a strategic communications consultancy that works \
with defence tech companies and defence-adjacent private equity firms. Today's date \
is {today}.

Score the following event on four dimensions, each from 1 to 10:

1. **sector_fit**: Is this specifically about defence, national security, defence \
technology, or defence industrial policy? Score higher for: defence tech, AI in \
defence, sovereign capability, transatlantic defence cooperation, European defence \
spending. Score lower for generic tech or policy events with only a tangential \
defence angle.

2. **seniority_speaker_quality**: Are speakers C-suite, senior military (2-star+), \
ministers, or senior civil servants? Are they from organisations we'd want to be in \
the room with? If no speakers are listed, score 5 (neutral).

3. **networking_value**: Is this the kind of event where a strategic comms \
consultancy working with defence tech companies and defence-adjacent PE firms would \
find prospects or deepen client relationships? Consider audience size, exclusivity, \
and attendee profile.

4. **timeliness**: Is the event soon enough to still register? Events 1-4 weeks \
out score 8-10; 4-8 weeks out score 5-7; more than 8 weeks out score 3-4; past \
events score 1.

Also provide a 2-sentence "relevance_summary" explaining why this event matters \
to our firm.

Return ONLY a JSON object with these fields:
- "sector_fit": int 1-10
- "seniority_speaker_quality": int 1-10
- "networking_value": int 1-10
- "timeliness": int 1-10
- "relevance_summary": string

EVENT DATA:
{event_json}
"""


def score_events(events: list[dict]) -> list[dict]:
    """Score each event and attach scores + weighted total."""
    client = anthropic.Anthropic()
    today = datetime.now().strftime("%Y-%m-%d")
    scored = []

    for i, event in enumerate(events, 1):
        if i > 1:
            logger.info("Waiting 8s for rate limit...")
            time.sleep(8)
        logger.info("Scoring event %d/%d: %s", i, len(events), event.get("name", "?"))
        try:
            scores = _score_single(client, event, today)
            event["scores"] = scores
            event["relevance_score"] = _weighted_score(scores)
            event["relevance_summary"] = scores.get("relevance_summary", "")
        except Exception:
            logger.exception("Error scoring event: %s", event.get("name"))
            event["scores"] = {}
            event["relevance_score"] = 0
            event["relevance_summary"] = "Scoring failed."
        scored.append(event)

    scored.sort(key=lambda e: e.get("relevance_score", 0), reverse=True)
    return scored


def _score_single(client: anthropic.Anthropic, event: dict, today: str) -> dict:
    event_json = json.dumps(event, indent=2, default=str)
    for attempt in range(5):
        try:
            response = client.messages.create(
                model=config.ANTHROPIC_SCORING_MODEL,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                    "content": SCORING_PROMPT.format(today=today, event_json=event_json),
                }
            ],
            )
            break
        except anthropic.RateLimitError:
            wait = 20 * (attempt + 1)
            logger.warning("Rate limited (attempt %d/5), waiting %ds...", attempt + 1, wait)
            time.sleep(wait)
    else:
        raise anthropic.RateLimitError("Exhausted retries")

    text = ""
    for block in response.content:
        if block.type == "text":
            text = block.text

    return _parse_scores(text)


def _parse_scores(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse scoring JSON")
    return {}


def _weighted_score(scores: dict) -> float:
    total = 0.0
    for dimension, weight in config.SCORING_WEIGHTS.items():
        value = scores.get(dimension, 5)
        if isinstance(value, (int, float)):
            total += value * weight
    return round(total, 1)
