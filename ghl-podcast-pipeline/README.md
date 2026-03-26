# GHL Podcast Pipeline

Automatically scrapes GoHighLevel help docs → generates podcast audio via NotebookLM → transcribes with Gemini → publishes to Transistor.fm with SEO metadata.

**Goal:** 20 episodes/day to drive GHL affiliate signups ($297/month plan).
**Status:** Running automatically via systemd service ✅

---

## The Pipeline Runs Itself

The scheduler is set up as a **systemd service** — it starts automatically every time you open your Linux terminal and runs forever without you doing anything.

Every 25 hours it:
1. Retries any failed episodes from the previous cycle
2. Runs a fresh batch of 20 new episodes
3. Emails a daily summary to your configured email
4. Sleeps 25 hours and repeats

**You will get one email per day.** If it says "All good" — do nothing. If it flags failures — check the log.

---

## Check What It's Doing

```bash
# Watch it live
tail -f ~/Claude_notebookLM_GHL_Podcast/ghl-podcast-pipeline/logs/scheduler.log

# Watch the detailed pipeline log
tail -f ~/Claude_notebookLM_GHL_Podcast/ghl-podcast-pipeline/logs/pipeline.log

# Quick count — how many published vs failed
cat ~/Claude_notebookLM_GHL_Podcast/ghl-podcast-pipeline/data/published.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
pub = len([x for x in d if x['status'] == 'published'])
fail = len([x for x in d if x['status'] == 'failed'])
print(f'{pub} published, {fail} failed, ~{1565 - pub} articles remaining')
"

# Is the service running?
systemctl --user status ghl-podcast
```

---

## Service Controls

```bash
# Start (if not already running)
systemctl --user start ghl-podcast

# Stop
systemctl --user stop ghl-podcast

# Restart
systemctl --user restart ghl-podcast

# See if it's running + last few log lines
systemctl --user status ghl-podcast
```

The service is set to **auto-restart** if it crashes and **auto-start** when Linux starts.

---

## Manual Override

```bash
cd ~/Claude_notebookLM_GHL_Podcast/ghl-podcast-pipeline

# Run one batch manually (doesn't affect scheduler)
venv/bin/python3 scripts/run-pipeline.py

# Manually retry failed episodes
venv/bin/python3 scripts/retry-failed.py
```

---

## How It Works

```
1. Scraper        — crawls help.gohighlevel.com (1565 articles, newest first)
                    Cache rebuilt once per day (articles-cache.json)
2. NotebookLM     — generates ~20min podcast audio
                    Pro account: 20/day limit (24hr rolling window)
3. Google Drive   — stores audio file + article body JSON + transcript text
4. SEO            — Claude Haiku writes title, description, tags (1 API call)
5. Gemini Flash   — transcribes audio (~35 seconds per episode)
6. Transistor.fm  — uploads audio + attaches transcript, schedules publish time
```

---

## Publish Schedule

- Episodes go live starting **8:00 AM Eastern**, every **45 minutes**
- 20 episodes/day covers 8am → 9:15pm
- Scheduler cycles every **25 hours** (1hr buffer so NotebookLM quota always resets)
- At 20/day with 1,565 articles = **~78 days of content**

---

## What's Stored Per Episode (published.json)

Each episode record contains:
- `articleId` — GHL help article ID
- `transistorEpisodeId` — numeric Transistor episode ID
- `transistorEmbedHash` — hash for embed URLs (e.g., `share.transistor.fm/e/{hash}`)
- `driveAudioId` — audio file on Google Drive
- `driveJsonId` — original article body on Google Drive (for future blog posts)
- `driveTranscriptId` — full transcript on Google Drive (for future use)
- `seoTitle`, `seoDescription`, `seoTags` — what listeners see
- `publishedAt` — when it goes live
- `streams` — play count (update manually from Transistor dashboard)
- `blogSlug` — matching blog post slug on globalhighlevel.com

---

## Files

```
scripts/
  scheduler.py        — 25hr cycle: retry → pipeline → email → sleep
  run-pipeline.py     — main pipeline (scrape → audio → SEO → upload)
  retry-failed.py     — recovers failed episodes without re-generating audio
  2-notebooklm.py     — NotebookLM audio generation + Drive upload
  3-seo.py            — SEO metadata (Claude Haiku, single call)
  4-upload.py         — Transistor upload + Gemini transcription

data/
  published.json      — master log of every episode (published + failed)
  articles-cache.json — cached list of GHL articles, rebuilt every 24hrs

logs/
  pipeline.log        — detailed log of every pipeline action
  scheduler.log       — scheduler start/stop/cycle activity
  scheduler-state.json — last run timestamp (keeps restarts safe)
  scheduler.pid       — process ID (used to stop the scheduler)
```

---

## API Keys (.env)

| Key | Service | Cost |
|-----|---------|------|
| ANTHROPIC_API_KEY | Claude Haiku (SEO) | ~$0.03/day |
| GOOGLE_AI_API_KEY | Gemini Flash (transcription) | ~$0.05/day |
| GMAIL_APP_PASSWORD | Daily summary email | Free |
| TRANSISTOR_API_KEY | Transistor.fm hosting | $19/month |
| GOOGLE credentials | Drive + NotebookLM auth | Free |
| NOTEBOOKLM account | your configured email (Pro, 20/day) | ~$20/month |

**Total running cost: ~$40-50/month**

---

## Troubleshooting

| Problem | What to do |
|---------|-----------|
| NotebookLM quota hit | Wait — scheduler handles it automatically next cycle |
| Episodes stuck as "failed" | Scheduler runs retry automatically. Or: `venv/bin/python3 scripts/retry-failed.py` |
| Service not running | `systemctl --user start ghl-podcast` |
| No daily email | Check GMAIL_APP_PASSWORD in .env. Make sure it's a Google App Password, not your login password |
| Scheduler restarted and waiting | Normal — it's waiting out remaining time from last cycle |

---

## Podcast

- **Name:** GoHighLevel Command Center
- **Platform:** Transistor.fm → Spotify, Apple Podcasts, Amazon Music
- **Affiliate link:** in every episode description + show notes
- **Target:** 84 signups/month × $297 = $10k MRR
