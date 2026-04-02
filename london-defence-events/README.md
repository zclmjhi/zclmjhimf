# London Defence Events Tracker

Automatically discovers, scores, and alerts you to upcoming defence and defence tech events in London and the UK. Uses the Anthropic API with web search to find events, Claude to score their relevance, and sends a formatted HTML digest email.

## Setup

### 1. Install dependencies

```bash
cd london-defence-events
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your API key and SMTP credentials
```

Required variables:
- `ANTHROPIC_API_KEY` – your Anthropic API key
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` – SMTP credentials for sending email
- `RECIPIENT_EMAIL` – where to send the daily digest

### 3. Run

```bash
# Full run with email
python main.py

# Preview mode – no email, prints results and saves HTML preview
python main.py --no-email
```

## Daily cron job

To run every morning at 7:00 AM:

```bash
crontab -e
```

Add:

```
0 7 * * * cd /path/to/london-defence-events && /path/to/python main.py >> cron.log 2>&1
```

## Configuration

Edit `config.py` to adjust:

- **Search queries**: add, remove, or reword the queries used for web search
- **Queries per run**: how many queries to execute each run (default: 8)
- **Scoring weights**: relative importance of sector fit, speaker quality, networking value, and timeliness
- **Score thresholds**: minimum scores for the main digest and "on the radar" sections
- **Anthropic model**: which Claude model to use
- **Source categories**: organisations and event sources to reference in search prompts

## Project structure

```
├── main.py              # Entry point
├── config.py            # All tuneable parameters
├── discovery.py         # Event search via Anthropic API + web search
├── scoring.py           # Relevance scoring via Claude
├── deduplication.py     # Seen-event tracking (JSON file)
├── email_sender.py      # HTML digest formatting and SMTP sending
├── seen_events.json     # Persistent store (auto-created)
├── tracker.log          # Log file (auto-created)
├── .env.example         # Template for environment variables
├── requirements.txt
└── README.md
```

## How it works

1. **Discovery**: Runs a random subset of search queries via the Anthropic API with web search enabled. Each query asks Claude to find upcoming defence events and return structured JSON.
2. **Deduplication**: Hashes each event by name + date and checks against `seen_events.json`. Only new events proceed.
3. **Scoring**: Each new event is scored 1–10 across four dimensions (sector fit, speaker quality, networking value, timeliness) with configurable weights.
4. **Digest**: Events scoring ≥6 appear in the main section; 4–5 appear in "On the Radar". The digest is sent as an HTML email or saved locally in preview mode.
