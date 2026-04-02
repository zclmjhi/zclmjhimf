"""
Configuration for London Defence Events Tracker.
Adjust search queries, scoring weights, thresholds, and sources here.
"""

# ---------------------------------------------------------------------------
# Search queries – rotated across runs for broader coverage
# ---------------------------------------------------------------------------
SEARCH_QUERIES = [
    "defence conference London 2026",
    "defence technology event UK upcoming",
    "RUSI event schedule 2026",
    "national security conference London 2026",
    "defence innovation event UK 2026",
    "military technology summit London",
    "DSEI fringe events 2026",
    "defence investment forum UK",
    "Chatham House defence security event 2026",
    "IISS defence event London",
    "techUK defence security event",
    "ADS Group defence event UK",
    "DIANA accelerator defence event UK",
    "NATO public event London 2026",
    "defence AI conference UK 2026",
    "European defence spending conference London",
    "defence industrial policy event UK",
    "defence startup event London",
    "MOD industry event 2026",
    "defence private equity investment event UK",
]

# How many queries to run per execution (picked at random without replacement)
QUERIES_PER_RUN = 8

# ---------------------------------------------------------------------------
# Source categories (informational – used in prompts sent to Claude)
# ---------------------------------------------------------------------------
SOURCE_CATEGORIES = {
    "Think tanks & policy institutes": [
        "RUSI", "Chatham House", "IISS", "Policy Exchange", "Henry Jackson Society",
    ],
    "Industry bodies & trade groups": [
        "ADS Group", "techUK (defence/security strand)", "DSEI / Clarion Events", "UKDSC",
    ],
    "Defence tech & startup ecosystem": [
        "Defence Innovation Network", "Defence BattleLab",
        "DIANA accelerator events", "Defence Tech Connect",
    ],
    "Professional networks": [
        "LinkedIn Events (defence + London)", "Eventbrite (defence technology London)",
    ],
    "Government & institutional": [
        "MOD industry events", "Defence and Security Exports (DSIT)",
        "NATO-adjacent public events",
    ],
    "Investor & PE-adjacent": [
        "BVCA", "British Private Equity Awards",
        "VC / growth equity firms active in defence tech",
    ],
}

# ---------------------------------------------------------------------------
# Scoring weights (must sum to 1.0)
# ---------------------------------------------------------------------------
SCORING_WEIGHTS = {
    "sector_fit": 0.40,
    "seniority_speaker_quality": 0.25,
    "networking_value": 0.25,
    "timeliness": 0.10,
}

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
HIGH_RELEVANCE_MIN_SCORE = 6   # Included in main digest section
RADAR_MIN_SCORE = 4            # Included in "on the radar" section
TIMELINESS_WINDOW_WEEKS = 8    # Events further out get lower timeliness scores

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_SUBJECT = "Defence Events Digest – London & UK"

# ---------------------------------------------------------------------------
# Anthropic model
# ---------------------------------------------------------------------------
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
SEEN_EVENTS_FILE = "seen_events.json"
LOG_FILE = "tracker.log"
