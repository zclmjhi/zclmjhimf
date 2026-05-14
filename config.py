import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-opus-4-7"

TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

DB_PATH = os.environ.get("DB_PATH", "montfort_coverage.db")

# Poll interval for the monitoring loop (seconds)
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))

# Admin user IDs allowed to modify the client registry
ADMIN_USER_IDS: list[str] = [
    uid.strip()
    for uid in os.environ.get("ADMIN_USER_IDS", "").split(",")
    if uid.strip()
]
