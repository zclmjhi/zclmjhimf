import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-opus-4-7"

# Teams bot credentials — provided by Azure when you register the bot.
# The Managed Agents platform injects these at runtime.
TEAMS_BOT_APP_ID = os.environ.get("TEAMS_BOT_APP_ID", "")
TEAMS_BOT_APP_PASSWORD = os.environ.get("TEAMS_BOT_APP_PASSWORD", "")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

DB_PATH = os.environ.get("DB_PATH", "montfort_coverage.db")

# Poll interval for the monitoring loop (seconds)
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))

# Admin user IDs allowed to modify the client registry
# Publication API keys — add one entry per source module.
# Leave unset for any source you are not using; the source will skip silently.
FT_API_KEY = os.environ.get("FT_API_KEY", "")

ADMIN_USER_IDS: list[str] = [
    uid.strip()
    for uid in os.environ.get("ADMIN_USER_IDS", "").split(",")
    if uid.strip()
]
