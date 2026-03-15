# GHL Podcast Pipeline — Project Context (SOP)

## Project Goal
Drive GHL 30-day free trial signups via affiliate link.
Target: $10k/month (~84 signups on $297 Agency plan).

## Affiliate Link
https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12
- This IS the 30-day free trial (bootcamp = trial)
- Tracking: GHL affiliate dashboard only (can't use GA4 — it's GHL's domain)
- UTM params auto-added to show notes and blog posts by the pipeline
- **Every link to GoHighLevel.com MUST include fp_ref=amplifi-technologies12 — no exceptions**

## Podcast
- Name: "Go High Level" on Spotify
- URL: https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV
- Hosted on: Transistor.fm (NOT Buzzsprout)
- Stats: 380 followers, 6,479 all-time streams, 25 avg streams/episode
- Top episode: "GoHighLevel Conversation AI Bot" — 492 streams
- Scheduled: 20 episodes/day, 45-min apart, 8am Eastern

## Websites
- **globalhighlevel.com** — main SEO content hub (all new blog posts go here)
  - Hosted: **Cloudflare Pages** (free, auto-deploys from GitHub on push to main)
  - Cloudflare Pages URL: claude-notebooklm-ghl-podcast.pages.dev
  - DNS: Cloudflare (nameservers: kyrie.ns.cloudflare.com, lara.ns.cloudflare.com)
  - Registrar: Namecheap (login: wcw1985)
  - GitHub repo: https://github.com/RecoveryBiometrics/Claude-notebookLM-GHL-Podcast
  - Google Search Console: verified ✅ sitemap submitted ✅
  - GSC verification code: TqqkuU1JDcd_0KnXbs_wGvyamJucFYVZiSLx9ICbeq4
- **reiamplifi.com** — GHL-hosted site. Stays for funnels, CRM, automations. Blog stopped — 48 old posts still live there pending migration.

## All Active Agents

### Scheduler (scheduler.py)
Runs every 25 hours via systemd. Cycle order:
1. **analytics.py** — pulls Transistor download data, updates topic weights
2. **retry-failed.py** — recovers partial failures from previous cycle
3. **run-pipeline.py** — generates + publishes 20 podcast episodes + 1 blog post each
4. **6-india-blog.py** — publishes 5 India blog topics
5. **deploy_site()** — git pushes new posts/*.json → Cloudflare Pages rebuilds globalhighlevel.com
6. Sends daily email summary to bill@reiamplifi.com
7. Sleeps 25 hours, repeats

### Pipeline Scripts (run-pipeline.py orchestrates these per episode)

| Script | Agent Type | What it does |
|---|---|---|
| 1-scraper.py | Scraper | Scrapes GHL help articles from help.gohighlevel.com → saves JSON to data/articles/ |
| 2-notebooklm.py | Content Generator | Claude enriches articles → NotebookLM generates podcast audio → uploads to Google Drive (Audio/ subfolder) |
| 3-seo.py | SEO Writer | Claude Haiku writes SEO title, description, tags + bakes in affiliate link |
| 4-upload.py | Publisher | Downloads audio from Drive → uploads to Transistor.fm → schedules episode. Gemini Flash transcribes audio → saves to Drive (Transcripts/ subfolder) |
| 5-blog.py | Blog Writer | DuckDuckGo SERP + Reddit research → Claude Haiku writes SEO blog post → saves to globalhighlevel-site/posts/{slug}.json → auto-deploys to globalhighlevel.com |
| run-pipeline.py | Orchestrator | Runs steps 1-4 per episode. Blog failure is non-fatal. NotebookLM timeout/failure halts the entire cycle immediately — does NOT skip and continue. Failed episode saved for retry-failed.py next cycle. |
| retry-failed.py | Recovery | Retries failed episodes from previous cycle |
| analytics.py | Analytics | Pulls Transistor download data, updates topic weights |

### India Blog Agent (6-india-blog.py)
3-agent pipeline targeting Indian GHL users (English). Runs 5 topics per scheduler cycle.
- **Researcher Agent:** DuckDuckGo SERP + Reddit (r/GoHighLevel, r/IndiaMarketing, r/marketing)
- **Writer Agent:** Claude Haiku — 1000-1500 word SEO post tailored for Indian businesses
- **Fact Checker Agent:** Claude Haiku — validates India-specific facts before saving
- Saves to globalhighlevel-site/posts/ — auto-deploys same as main blog
- **Affiliate UTMs:** utm_source=blog&utm_medium=article&utm_campaign={slug}&utm_country=in
- **Data files:** data/india-published.json, data/india-topics.json
- **CLI flags:** --topic "Topic Name" (single run), --limit N (batch cap)

#### India Fact-Check Rules
- WhatsApp NOT SMS (primary messaging in India)
- Razorpay / PayU / UPI NOT Stripe
- ₹ rupees NOT $ dollars
- Zoho as primary CRM competitor (not Salesforce)
- DPDP Act NOT GDPR
- GST compliance for Indian businesses
- GHL starts at $97/month

### Site Builder (globalhighlevel-site/build.py)
Runs automatically on Cloudflare Pages on every GitHub push. Generates:
- public/index.html — homepage (uses homepage_hero.html if present)
- public/blog/{slug}/index.html — individual post pages
- public/category/{slug}/index.html — category pages
- public/sitemap.xml — auto-updated with every post
- public/llms.txt — AI model discoverability (lists all tutorials)
- public/robots.txt — copied from globalhighlevel-site/robots.txt

### Two-Agent Homepage Designer (globalhighlevel-site/design-homepage.py)
Run manually to regenerate homepage_hero.html:
```
cd globalhighlevel-site
../ghl-podcast-pipeline/venv/bin/python3 design-homepage.py
```
- **Designer Agent** (claude-opus-4-6) — writes full homepage HTML
- **Manager Agent** (claude-opus-4-6) — reviews against zero-tolerance checklist
- Uses verified facts only — see VERIFIED_FACTS block in the script
- Output: homepage_hero.html → picked up by build.py on next Cloudflare Pages deploy

## Blog Agent — How It Works (5-blog.py)
- **SERP:** DuckDuckGo HTML scrape (no API key) — top 5 results drive H2 structure
- **Reddit:** Searches r/GoHighLevel, r/marketing, r/automation, r/entrepreneur
- **Claude Haiku:** Writes 900-1300 word SEO post with TOC, CTA boxes, Pro Tip callouts, FAQ
- **Affiliate UTMs:** utm_source=blog&utm_medium=article&utm_campaign={slug}
- **Publishes to:** globalhighlevel.com ONLY (reiamplifi.com blog stopped Mar 11, 2026)

## Pipeline Flow
```
Every 25 hours (automated):
  analytics.py       → update stream counts + topic weights
  retry-failed.py    → recover any failed episodes
  run-pipeline.py (×20 episodes):
    1-scraper.py     → fetch GHL help article
    2-notebooklm.py  → generate podcast audio → Google Drive
    3-seo.py         → write SEO title/description/tags
    4-upload.py      → upload to Transistor.fm → transcribe
    5-blog.py        → write blog post → save to globalhighlevel-site/posts/
  6-india-blog.py    → write 5 India posts → save to globalhighlevel-site/posts/
  deploy_site()      → git push → Cloudflare Pages rebuilds globalhighlevel.com
  send email         → daily summary to bill@reiamplifi.com
  sleep 25 hours
```

## Tech Stack
Python, anthropic SDK, notebooklm SDK, Google Drive API, Transistor.fm API, Gemini Flash (transcription), requests + BeautifulSoup (scraping), Cloudflare Pages (static hosting), GitHub (auto-deploy trigger)

## .env Keys
- TRANSISTOR_API_KEY, TRANSISTOR_SHOW_ID
- ANTHROPIC_API_KEY
- GOOGLE_AI_API_KEY, GOOGLE_DRIVE_FOLDER_ID, GOOGLE_CREDENTIALS_FILE
- GOOGLE_DRIVE_AUDIO_FOLDER_ID, GOOGLE_DRIVE_TRANSCRIPTS_FOLDER_ID, GOOGLE_DRIVE_ARTICLES_FOLDER_ID
- GHL_API_KEY, GHL_LOCATION_ID, GHL_AFFILIATE_LINK
- GMAIL_ADDRESS, GMAIL_APP_PASSWORD
- SITE_DOMAIN, SITE_REGISTRAR, NAMECHEAP_USERNAME, SITE_HOST, SITE_REPO, SITE_NETLIFY_URL
- GOOGLE_SITE_VERIFICATION (GSC verification code)
- GA4_MEASUREMENT_ID (not yet set — pending GA4 setup)

## GHL Config
- Location ID: VL5PlkLBYG4mKk3N6PGw
- GHL MCP server: ghl-podcast (available in Claude Code)
- reiamplifi.com stays for funnels, CRM, contacts, automations only

## User Context
- Not a developer — explain in plain English
- Chromebook with Linux (Crostini) — NOT a Mac
- Budget: ~$70/month
- Active GHL user — use native GHL features before third-party tools
