"""
Configuration for London Defence Events Tracker.
Adjust search queries, scoring weights, thresholds, and email settings here.
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
    "Chatham House defence security event",
    "IISS defence event London",
    "Policy Exchange defence event",
    "Henry Jackson Society security event",
    "ADS Group defence industry event UK",
    "techUK defence security event",
    "UKDSC defence event",
    "Defence Innovation Network event",
    "Defence BattleLab event UK",
    "DIANA accelerator defence event UK",
    "Defence Tech Connect event",
    "defence technology Eventbrite London",
    "MOD industry event UK 2026",
    "NATO public event London",
    "defence private equity forum UK",
    "sovereign capability conference UK",
    "European defence spending event London",
    "AI defence summit UK 2026",
    "transatlantic defence cooperation event",
]

# How many queries to use per run (randomly sampled from the list above)
QUERIES_PER_RUN = 8

# ---------------------------------------------------------------------------
# Source categories (informational – used in prompts to Claude)
# ---------------------------------------------------------------------------
SOURCE_CATEGORIES = {
    "think_tanks": [
        "RUSI",
        "Chatham House",
        "IISS",
        "Policy Exchange",
        "Henry Jackson Society",
    ],
    "industry_bodies": [
        "ADS Group",
        "techUK (defence/security strand)",
        "DSEI / Clarion Events",
        "UKDSC",
    ],
    "defence_tech_ecosystem": [
        "Defence Innovation Network",
        "Defence BattleLab",
        "DIANA accelerator",
        "Defence Tech Connect",
    ],
    "professional_networks": [
        "LinkedIn Events (defence + London)",
        "Eventbrite (defence technology London)",
    ],
    "government_institutional": [
        "MOD industry events",
        "Defence and Security Exports (DSIT)",
        "NATO-adjacent public events",
    ],
    "investor_pe": [
        "BVCA",
        "British Private Equity Awards",
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
MIN_SCORE_HEADLINE = 6        # Events shown in headline section
MIN_SCORE_ON_RADAR = 4        # Events shown in "on the radar" section
TIMELINESS_WEEKS_MAX = 8      # Prefer events within this many weeks

# ---------------------------------------------------------------------------
# Email settings (credentials come from environment / .env)
# ---------------------------------------------------------------------------
EMAIL_SUBJECT = "Daily Defence Events Digest"
EMAIL_FROM_NAME = "Defence Events Tracker"

# ---------------------------------------------------------------------------
# Anthropic model
# ---------------------------------------------------------------------------
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
SEEN_EVENTS_FILE = "seen_events.json"
LOG_FILE = "tracker.log"
