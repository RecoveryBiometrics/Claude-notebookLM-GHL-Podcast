# GHL Podcast Pipeline — Project Brain

## What This Project Does
Fully automated pipeline:
1. Scrapes every help article from help.gohighlevel.com (Playwright)
2. Each article → its own NotebookLM audio overview (notebooklm-py)
3. Downloads the MP4
4. SEO Writer Agent generates title, description, tags (Claude API)
5. SEO Reviewer Agent checks and corrects the output (Claude API)
6. Uploads to Buzzsprout
7. Buzzsprout RSS auto-distributes to Spotify, Apple Podcasts, Amazon Music

Zero manual work after setup. Dashboard tracks everything.

---

## The Goal
Drive listeners to a GoHighLevel 30-day free trial affiliate link.
40% recurring monthly commission. Target: $10,000/month.

**Affiliate link:** https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12
**Podcast name:** "Go High Level" on Spotify
**Buzzsprout plan:** $12/month (unlimited episodes)

---

## Tech Stack
| Tool | Purpose |
|------|---------|
| Python | Primary language for all scripts |
| Playwright | Scrapes GHL help docs (headless Chromium, never Claude Chrome) |
| notebooklm-py | Calls NotebookLM's internal API to generate + download audio |
| Anthropic Python SDK | Two Claude agents: SEO Writer + SEO Reviewer |
| Transistor.fm API | Uploads episodes, provides RSS feed ($19/mo unlimited) |
| Flask | Local dashboard to monitor pipeline |
| python-dotenv | Loads .env variables |
| schedule | Runs pipeline on a cron-style schedule |

---

## Folder Structure
```
ghl-podcast-pipeline/
├── Claude_notebookLM_GHL_Podcast.md
├── .env                     # API keys — never commit
├── .env.template            # Safe template
├── requirements.txt
├── scripts/
│   ├── 1-scraper.py         # Scrapes GHL articles via Playwright
│   ├── 2-notebooklm.py      # Generates + downloads audio per article
│   ├── 3-seo.py             # SEO Writer Agent then SEO Reviewer Agent
│   ├── 4-upload.py          # Uploads to Buzzsprout
│   └── run-pipeline.py      # Orchestrates all steps on a schedule
├── dashboard/
│   ├── app.py               # Flask server
│   └── templates/
│       └── index.html
├── data/
│   ├── articles/            # One JSON file per scraped article
│   ├── audio/               # Downloaded MP4 files
│   └── published.json       # Master status log for all episodes
└── logs/
    └── pipeline.log
```

---

## Environment Variables (.env)
```
BUZZSPROUT_PODCAST_ID=your_podcast_id_here
BUZZSPROUT_API_TOKEN=your_api_token_here
ANTHROPIC_API_KEY=your_anthropic_key_here
GHL_AFFILIATE_LINK=https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12
```
- Transistor: transistor.fm → Settings → API Key
- Anthropic: console.anthropic.com
- NotebookLM: run `notebooklm login` once to authenticate with Google

---

## requirements.txt
```
playwright
notebooklm-py
anthropic
requests
python-dotenv
flask
schedule
```

---

## Step 1 — Scraper (1-scraper.py)

**Tool:** Playwright (headless Chromium). Never use Claude Chrome browser instance.
**Target:** https://help.gohighlevel.com/support/solutions

- Crawls index → all categories → all articles
- Extracts: title, body, category, subcategory, URL, last-modified date
- Saves to data/articles/{article-id}.json
- Skips articles that already exist in data/articles/
- Re-scrapes if last-modified date has changed
- 2–3 second delay between requests

**Article JSON:**
```json
{
  "id": "155000001234",
  "title": "Setting Up Conversation AI Bot",
  "url": "https://help.gohighlevel.com/support/solutions/articles/...",
  "category": "Conversations",
  "subcategory": "AI Features",
  "body": "Full article text...",
  "lastModified": "2025-11-15",
  "scraped": "2026-03-04"
}
```

**Processing priority (highest affiliate conversion first):**
1. AI Features
2. Automation & Workflows
3. CRM & Contacts
4. Funnels & Websites
5. Email & SMS Marketing
6. Calendars & Appointments
7. Payments & Commerce
8. Reporting & Analytics
9. Agency Settings
10. Integrations

---

## Step 2 — NotebookLM Audio (2-notebooklm.py)

**One article = one NotebookLM audio overview = one episode. No grouping.**

**Library:** notebooklm-py (pure Python HTTP — no browser automation)
**One-time setup (ChromeOS Linux):**
```bash
pip install notebooklm-py playwright
playwright install-deps chromium   # installs system dependencies on ChromeOS Linux
playwright install chromium
notebooklm login
```

**Host instructions passed to every generation:**
```
Open by telling listeners they can get a FREE 30-day GoHighLevel trial —
double the standard trial — and that the link is in the show notes.
Cover the topic with practical takeaways for agency owners.
Close by reminding listeners the free 30-day trial link is in the show notes.
```

**Python flow:**
```python
async with await NotebookLMClient.from_storage() as client:
    nb = await client.notebooks.create(article["title"])
    await client.sources.add_text(nb.id, article["title"], article["body"])
    status = await client.artifacts.generate_audio(
        nb.id,
        instructions=NOTEBOOKLM_INSTRUCTIONS,
        audio_format=AudioFormat.DEEP_DIVE,
    )
    final = await client.artifacts.wait_for_completion(nb.id, status.task_id, timeout=300)
    await client.artifacts.download_audio(nb.id, f"data/audio/{article['id']}.mp4")
```

- Retry once on failure after 60 seconds
- Log failures to pipeline.log, continue to next article
- Max 20 generations/day

---

## Step 3 — SEO Agents (3-seo.py)

Two agents run in sequence. Never upload without reviewer approval.

### Agent 1 — SEO Writer
**Model:** claude-sonnet-4-6
**Input:** article title + body
**Output:**
- Episode title (under 70 chars, includes "GoHighLevel")
- Show notes description (below)
- 8 tags

**Title formula:**
```
How to [Action] in GoHighLevel — [Specific Benefit]
```

**Show notes description formula:**
```
Paragraph 1: What this episode covers (2–3 sentences, "GoHighLevel" used naturally)
Paragraph 2: What you'll learn (3–4 bullet points)
Paragraph 3 (CTA — required, always last):

"Ready to try GoHighLevel yourself? Get a FREE 30-day trial — double the standard
14-day trial — and see why thousands of agencies run their entire business on one
platform: https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12"
```

**Required tags:** gohighlevel, go high level, GHL, CRM, marketing automation, agency software, [feature], [use case]

### Agent 2 — SEO Reviewer
**Model:** claude-sonnet-4-6
**Input:** Agent 1 output
**Checks:**
- Title under 70 characters and contains "GoHighLevel"
- "GoHighLevel" appears 3–4 times in description (natural, not spammy)
- Affiliate link present and exact: https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12
- CTA is the last paragraph of description
- Required tags all present
- Title follows the formula

**Output:** Approved output or corrected version with change notes

---

## Step 4 — Transistor.fm Upload (4-upload.py)

**API:** `https://api.transistor.fm/v1`
**Auth header:** `x-api-key: {API_KEY}`
**Plan:** $19/month — unlimited episodes, unlimited storage

**Three-step upload process:**
1. `POST /v1/episodes` — create episode draft, get S3 upload URL
2. `PUT {s3_url}` — stream audio file directly to S3
3. `PATCH /v1/episodes/{id}` — set title, description, tags, publish time

- 20 episodes/day, spread in 45-minute intervals from 8am Eastern
- Log each upload to published.json with Transistor episode ID

---

## Step 5 — Scheduler (run-pipeline.py)

```
6:00am  → 1-scraper.py      (new/updated GHL articles)
7:00am  → 2-notebooklm.py   (generate audio for pending articles)
          3-seo.py           (SEO Writer → Reviewer, runs inline)
8:00am+ → 4-upload.py       (20 episodes spread across the day)
```

---

## Dashboard (dashboard/app.py)

Run: `python dashboard/app.py` → open http://localhost:5000

| Panel | Shows |
|-------|-------|
| Pipeline status | Running / idle / last run |
| Articles | Scraped / pending audio / audio ready / published |
| Today | Episodes published today |
| Top performers | Top 10 episodes by Buzzsprout stream count |
| Failed | Articles that failed NotebookLM generation |
| Live log | Last 50 lines of pipeline.log |

---

## published.json — Master Status Log

```json
[
  {
    "articleId": "155000001234",
    "title": "Setting Up Conversation AI Bot",
    "category": "AI Features",
    "status": "published",
    "buzzsproutEpisodeId": "12345678",
    "publishedAt": "2026-03-04T08:00:00",
    "streams": 492,
    "audioFile": "data/audio/155000001234.mp4",
    "seoTitle": "How to Set Up GoHighLevel AI Bot...",
    "affiliateLinkIncluded": true
  }
]
```

**Status flow:** `scraped` → `audio_ready` → `seo_ready` → `published` / `failed`

---

## Hard Rules

1. Each article is its own episode — no grouping, no clustering
2. Always use Playwright for scraping — never Claude Chrome browser
3. Never upload without SEO Reviewer approval
4. Affiliate link must appear in every show notes description, exact URL
5. NotebookLM audio must open and close with free trial mention
6. Never hardcode API keys — always use .env
7. Log everything to pipeline.log
8. Check published.json before processing — no duplicate episodes
9. 20 episodes/day max

---

## Context

- Podcast: "Go High Level" on Spotify — 380 followers, 6,479 all-time streams
- Top episode: "GoHighLevel Conversation AI Bot" — 492 streams → process AI articles first
- Budget: ~$70/month | Buzzsprout: $12/month unlimited
- Chromebook with Linux (Crostini) enabled — ChromeOS
- Owner is not a developer — explain steps in plain English

---

## Starting a New Session

```
Read Claude_notebookLM_GHL_Podcast.md. That's the full brief.
Current task: [DESCRIBE WHAT YOU WANT TO DO]
```
