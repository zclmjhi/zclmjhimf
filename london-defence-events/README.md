# London Defence Events Tracker

Automatically discovers, scores, and alerts you to upcoming defence and defence tech events in London and the UK.

## Setup

### 1. Install dependencies

```bash
cd london-defence-events
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your Anthropic API key and SMTP credentials
```

**Required variables:**

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `SMTP_HOST` | SMTP server (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port (default: `587`) |
| `SMTP_USER` | SMTP username / email |
| `SMTP_PASS` | SMTP password or app password |
| `RECIPIENT_EMAIL` | Where to send the digest |

### 3. Run

```bash
# Full run (discover + score + email)
python main.py

# Dry run (discover + score, print results, save HTML preview, skip email)
python main.py --dry-run
```

### 4. Daily cron job

Add to your crontab (`crontab -e`):

```cron
# Run defence events tracker at 7:00 AM daily
0 7 * * * cd /path/to/london-defence-events && /path/to/python main.py >> cron.log 2>&1
```

## Configuration

Edit `config.py` to adjust:

- **Search queries** – add or remove queries for broader/narrower coverage
- **Queries per run** – how many queries to sample each run (default: 8)
- **Scoring weights** – relative importance of sector fit, speaker quality, networking value, and timeliness
- **Score thresholds** – minimum scores for headline (default: 6) and "on the radar" (default: 4) sections
- **Anthropic model** – which Claude model to use

## How it works

1. **Discovery**: Uses the Anthropic API with web search to find events across multiple queries
2. **Deduplication**: Hashes event name + date, stores in `seen_events.json`, skips duplicates
3. **Scoring**: Each event is scored 1-10 on sector fit, speaker quality, networking value, and timeliness
4. **Email**: Sends an HTML digest with headline events (score >= 6) and "on the radar" events (score 4-5)

## Project structure

```
├── main.py              # Entry point
├── config.py            # All tuneable parameters
├── discovery.py         # Event search via Anthropic API + web search
├── scoring.py           # Relevance scoring via Claude
├── deduplication.py     # Seen-event tracking
├── email_sender.py      # HTML email formatting and SMTP sending
├── seen_events.json     # Persistent store (auto-created)
├── tracker.log          # Log file (auto-created)
├── .env.example         # Template for environment variables
├── requirements.txt
└── README.md
```
