# Coverage Monitoring Agent

Automated media coverage agent that polls Google Alerts RSS feeds and a Microsoft 365 newsletter inbox, matches articles against a client keyword registry and urgent briefs, deduplicates results, and delivers matches to Microsoft Teams.

---

## File structure

```
agent.py                  Main orchestrator
handlers/
  base.py                 Abstract base class for all source handlers
  google_alerts.py        Google Alerts RSS handler
  inbox.py                M365 IMAP inbox handler
  rest_api_example.py     Template for adding a new REST API source
config/
  registry.json           Client keywords, feed URLs, newsletter senders
  briefs.json             Active urgent briefs (edit manually)
data/
  seen_items.json         Deduplication store (auto-managed)
  coverage_log.json       Append-only match log (auto-managed)
deduplicator.py           URL-hash deduplication
matcher.py                Keyword matching against registry and briefs
teams_delivery.py         Teams webhook delivery (immediate + digest)
requirements.txt
.env                      Credentials (never commit)
```

---

## Setup

### 1. Python environment

Requires **Python 3.11+**.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Credentials — `.env`

Edit `.env` with real values:

```
IMAP_USER=monitoring@yourcompany.com
IMAP_PASS=your-app-password          # Use an App Password, not your main password
IMAP_SERVER=outlook.office365.com    # Default; change for other hosts
IMAP_PORT=993

TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...
```

**M365 App Password**: sign in to https://mysignins.microsoft.com/security-info, add a new App Password, and paste the generated password as `IMAP_PASS`. Modern Auth / OAuth is not required — IMAP with App Passwords works on M365 when basic auth is enabled for the specific mailbox by your admin.

**Teams webhook**: In Teams, open the channel → Manage channel → Connectors → Incoming Webhook → Configure. Copy the URL and paste as `TEAMS_WEBHOOK_URL`.

### 3. Configure `config/registry.json`

- Replace `REPLACE_WITH_YOUR_FEED_ID` in `google_alerts_feeds` with your real Google Alerts RSS feed URLs.
  - In Google Alerts, when creating or editing an alert, set **Deliver to → RSS feed**. Copy the feed URL from the RSS icon.
- Add all newsletter sender addresses to `newsletter_senders`.
- Add one entry per client in `clients` with relevant keywords and the Teams channel name.

### 4. Configure `config/briefs.json`

Add time-limited urgent briefs manually. The `expires_at` field is ISO 8601. Expired briefs are silently skipped.

---

## Running the agent

```bash
# Standard run — fetch, deduplicate, match, and deliver immediately
python agent.py

# Morning digest — deliver last 24 h from the log, grouped by client
python agent.py --digest

# Dry run — fetch and match but do not post to Teams or update data files
python agent.py --dry-run
```

---

## Windows Task Scheduler — automated scheduling

You need **two scheduled tasks**:

### Task 1 — Standard run every 20 minutes

1. Open **Task Scheduler** → **Create Task**
2. **General** tab:
   - Name: `Coverage Agent — Standard`
   - Run whether user is logged on or not
   - Run with highest privileges
3. **Triggers** tab → New:
   - Begin the task: **On a schedule**
   - Daily, starting today
   - Repeat task every **20 minutes** for a duration of **1 day**
4. **Actions** tab → New:
   - Action: **Start a program**
   - Program/script: `C:\path\to\your\.venv\Scripts\python.exe`
   - Add arguments: `C:\path\to\your\agent.py`
   - Start in: `C:\path\to\your\` (the project root)
5. **Settings** tab:
   - If the task is already running, do not start a new instance

### Task 2 — Morning digest at 07:30

1. **Create Task** → Name: `Coverage Agent — Morning Digest`
2. **Triggers** tab → New:
   - Daily at **07:30**
3. **Actions** tab → New:
   - Program/script: `C:\path\to\your\.venv\Scripts\python.exe`
   - Add arguments: `C:\path\to\your\agent.py --digest`
   - Start in: `C:\path\to\your\`

> Tip: export both tasks as XML (right-click → Export) after creation so they can be re-imported on a new machine.

---

## Adding a new source handler

The pattern requires **one new file** and **one line change** in `agent.py`.

### Step 1 — Copy the template

```bash
cp handlers/rest_api_example.py handlers/green_street.py
```

### Step 2 — Implement the handler

Open `handlers/green_street.py` and:

1. Rename the class to `GreenStreetHandler`
2. Set `name = "green_street"`
3. Replace `_BASE_URL` with the real endpoint
4. Adjust `_fetch_page()` to use the correct auth headers / params
5. Map the response keys in `_parse_item()` to `NormalisedItem` fields

Everything else (deduplication, matching, logging, Teams delivery) is handled automatically by the orchestrator.

### Step 3 — Register the handler

In `agent.py`, add two lines:

```python
# at the top, with other imports
from handlers.green_street import GreenStreetHandler

# in HANDLER_CLASSES list
HANDLER_CLASSES: list[type[BaseHandler]] = [
    GoogleAlertsHandler,
    InboxHandler,
    GreenStreetHandler,   # <- new line
]
```

### Step 4 — Add config / credentials (if needed)

- Add any API keys to `.env`
- Add any per-client config (e.g. `"green_street_categories": [...]`) to `config/registry.json`
- Read them in your handler via `os.environ.get(...)` and `self.config`

That's the complete pattern. No other file changes.

---

## Data files

| File | Purpose | Safe to edit? |
|---|---|---|
| `config/registry.json` | Client config, feed URLs, senders | Yes |
| `config/briefs.json` | Urgent briefs | Yes |
| `data/seen_items.json` | Dedup hashes | Do not edit manually |
| `data/coverage_log.json` | Match log | Read-only; append-only by agent |

---

## Troubleshooting

| Symptom | Check |
|---|---|
| No Teams messages | Verify `TEAMS_WEBHOOK_URL`; run `--dry-run` to confirm matches exist |
| Inbox handler skipped | Check `IMAP_USER` / `IMAP_PASS` are set; confirm App Password is active |
| All items deduplicated | Delete `data/seen_items.json` to reset the dedup store |
| Brief matches not flagged urgent | Check `expires_at` hasn't passed; confirm keyword casing |
| Google Alerts feed empty | Verify the feed URL is accessible in a browser |
