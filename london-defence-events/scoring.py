"""
Relevance scoring for discovered events using Claude.
"""

import json
import logging
from datetime import date

import anthropic

import config

logger = logging.getLogger(__name__)


def _build_scoring_prompt(event: dict) -> str:
    today = date.today().isoformat()
    weights = config.SCORING_WEIGHTS
    return f"""You are scoring the relevance of a defence/security event for a strategic communications consultancy that works with defence tech companies and defence-adjacent PE firms, based in London.

Today's date is {today}.

Event details:
- Name: {event.get('name', 'Unknown')}
- Date: {event.get('date', 'Unknown')}
- Venue: {event.get('venue', 'Unknown')}
- Organiser: {event.get('organiser', 'Unknown')}
- Description: {event.get('description', 'No description')}
- Speakers: {event.get('speakers', 'Not announced')}
- URL: {event.get('url', 'N/A')}

Score this event on four dimensions (each 1-10):

1. **sector_fit** (weight {weights['sector_fit']}): Is this specifically about defence, national security, defence technology, or defence industrial policy? Score higher for defence tech, AI in defence, sovereign capability, transatlantic defence cooperation, European defence spending.

2. **seniority_speaker_quality** (weight {weights['seniority_speaker_quality']}): Are speakers C-suite, senior military (2-star+), ministers, or senior civil servants? Are they from organisations we'd want to be in the room with?

3. **networking_value** (weight {weights['networking_value']}): Is this the kind of event where a strategic comms consultancy working with defence tech companies and defence-adjacent PE firms would find prospects or deepen client relationships?

4. **timeliness** (weight {weights['timeliness']}): Is the event within the next {config.TIMELINESS_WINDOW_WEEKS} weeks? Closer events score higher. Events that have already passed score 1.

Return ONLY a JSON object with these fields:
- "sector_fit": integer 1-10
- "seniority_speaker_quality": integer 1-10
- "networking_value": integer 1-10
- "timeliness": integer 1-10
- "weighted_score": float rounded to 1 decimal (the weighted average)
- "summary": a 2-sentence explanation of why this event is or isn't relevant

No markdown fences, no commentary – just the JSON object."""


def score_events(events: list[dict]) -> list[dict]:
    """Score each event and return events augmented with scoring data."""
    client = anthropic.Anthropic()
    scored: list[dict] = []

    for i, event in enumerate(events, 1):
        name = event.get("name", "Unknown")
        logger.info("Scoring event %d/%d: %s", i, len(events), name)
        try:
            response = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": _build_scoring_prompt(event)}],
            )

            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text

            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[1:])
            if cleaned.endswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[:-1])
            cleaned = cleaned.strip()

            scores = json.loads(cleaned)
            event["scores"] = scores
            event["weighted_score"] = scores.get("weighted_score", 0)
            event["relevance_summary"] = scores.get("summary", "")
            scored.append(event)

        except (json.JSONDecodeError, anthropic.APIError) as exc:
            logger.warning("Failed to score event '%s': %s", name, exc)
            event["scores"] = {}
            event["weighted_score"] = 0
            event["relevance_summary"] = "Scoring failed."
            scored.append(event)

    scored.sort(key=lambda e: e.get("weighted_score", 0), reverse=True)
    logger.info("Scored %d events", len(scored))
    return scored
