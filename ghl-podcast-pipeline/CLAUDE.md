# GHL Podcast Pipeline — Project Context (SOP)

## Project Goal
Drive GHL 30-day free trial signups via affiliate link.
Target: $10k/month (~84 signups on $297 Agency plan).

## Affiliate Link
https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12
- This IS the 30-day free trial (bootcamp = trial)
- Tracking: GHL affiliate dashboard only (can't use GA4 — it's GHL's domain)
- UTM params auto-added to show notes and blog posts by the pipeline

## Podcast
- Name: "Go High Level" on Spotify
- Hosted on: Transistor.fm (NOT Buzzsprout)
- Stats: 380 followers, 6,479 all-time streams, 25 avg streams/episode
- Top episode: "GoHighLevel Conversation AI Bot" — 492 streams
- Scheduled: 20 episodes/day, 45-min apart, 8am Eastern

## Pipeline — BUILT (Python)
Scripts in: `ghl-podcast-pipeline/scripts/`
Run with: `venv/bin/python3 scripts/run-pipeline.py`

| Script | What it does |
|---|---|
| 1-scraper.py | Scrapes GHL help articles from help.gohighlevel.com → saves JSON to data/articles/ |
| 2-notebooklm.py | Claude enriches articles → NotebookLM generates podcast audio → uploads to Google Drive |
| 3-seo.py | Claude Haiku writes SEO title, description, tags. Affiliate link baked into description here. |
| 4-upload.py | Downloads audio from Drive → uploads to Transistor.fm → schedules. Gemini Flash transcribes audio. |
| 5-blog.py | DuckDuckGo SERP + Reddit research → Claude Haiku writes SEO blog post → publishes to reiamplifi.com via GHL API |
| run-pipeline.py | Orchestrator — runs all 4 steps per episode. Blog failure is non-fatal. |
| analytics.py | Analytics tracking |
| scheduler.py | Scheduling |

## Pipeline Flow (run-pipeline.py orchestrates all steps)
```
GHL Help Article (scraped)
  → Step 1: 2-notebooklm.py  — Claude enriches → NotebookLM generates audio → Google Drive
  → Step 2: 3-seo.py         — Claude Haiku writes SEO title, description, tags + affiliate link
  → Step 3: 4-upload.py      — Audio → Transistor.fm → episode scheduled. Gemini transcribes.
  → Step 4: 5-blog.py        — SERP + Reddit research → Claude writes blog post → reiamplifi.com/blog
```
Blog failure is non-fatal — episode still publishes to Transistor if blog step fails.

## Blog Agent — How It Works (5-blog.py)
- **SERP:** DuckDuckGo HTML scrape (no API key) — top 5 results drive H2 structure
- **Reddit:** Searches r/GoHighLevel, r/marketing, r/automation, r/entrepreneur — only actual questions (containing ?) used in FAQ section
- **Claude Haiku:** Writes 800-1200 word SEO post. Structure: hook intro → logical H2 steps → FAQ → affiliate CTA
- **GHL Blog:** Blog ID `0KLFiNIFJ5OtlM836Gfi` | Author ID `680b01f0c55be738c7e7287a` | Category ID `680b01923c1c207691887512` (GoHighLevel Tutorials)
- **Affiliate UTMs:** `utm_source=blog&utm_medium=article&utm_campaign={slug}`
- **Publishes to:** reiamplifi.com/blog via GHL REST API

## Tech Stack
Python, playwright, anthropic SDK, notebooklm SDK, Google Drive API, Transistor.fm API, Gemini Flash (transcription), requests + BeautifulSoup (scraping)

## GHL / Website
- Website: reiamplifi.com (hosted in GHL)
- GHL location ID: VL5PlkLBYG4mKk3N6PGw
- GHL MCP server: ghl-podcast (available in Claude Code)

## .env Keys Required
- TRANSISTOR_API_KEY, TRANSISTOR_SHOW_ID
- ANTHROPIC_API_KEY
- GOOGLE_AI_API_KEY, GOOGLE_DRIVE_FOLDER_ID, GOOGLE_CREDENTIALS_FILE
- GHL_API_KEY, GHL_LOCATION_ID, GHL_AFFILIATE_LINK
- GMAIL_ADDRESS, GMAIL_APP_PASSWORD

## India Blog Agent — How It Works (6-india-blog.py)
3-agent pipeline targeting Indian GHL users (English). Runs independently of main podcast pipeline.

- **Researcher Agent:** DuckDuckGo SERP + Reddit (r/GoHighLevel, r/IndiaMarketing, r/marketing, r/automation, r/entrepreneur)
- **Writer Agent:** Claude Haiku — 1000-1500 word SEO post tailored for Indian businesses
- **Fact Checker Agent:** Claude Haiku — validates India-specific facts before publishing
- **GHL Blog:** Blog ID `ICGLk7OTn2N6jL6pgxgu` | Author ID `680b01f0c55be738c7e7287a` | Category ID `69b07af891669681ae873ae5` (GoHighLevel Tutorials India)
- **Affiliate UTMs:** `utm_source=blog&utm_medium=article&utm_campaign={slug}&utm_country=in`
- **Data files:** `data/india-published.json`, `data/india-topics.json`
- **Scheduler:** Runs 5 topics per cycle (Step 3 in scheduler.py)
- **CLI flags:** `--topic "Topic Name"` (single), `--limit N` (batch cap)

### India Fact-Check Rules (hardcoded in INDIA_FACT_RULES)
- WhatsApp NOT SMS (primary messaging in India)
- Razorpay / PayU / UPI NOT Stripe (payment gateways)
- ₹ rupees NOT $ dollars
- Zoho as primary CRM competitor (not Salesforce)
- DPDP Act (India privacy law) NOT GDPR
- GST compliance for Indian businesses
- GHL starts at $97/month (NOT $297)

### Phase 1-2 Topics (10 total)
1. How Indian Real Estate Agents Use GoHighLevel to Automate Follow-Ups
2. GoHighLevel for Indian Digital Marketing Agencies: Complete Setup Guide
3. How to Set Up WhatsApp Automation in GoHighLevel for Indian Businesses
4. GoHighLevel vs Zoho CRM: Which Is Better for Indian Agencies in 2025?
5. How Indian Coaches and Consultants Use GoHighLevel to Scale Their Business
6. Setting Up GoHighLevel Funnels for Indian E-Commerce Businesses
7. GoHighLevel Payment Integration for Indian Businesses: Razorpay, PayU & UPI Guide
8. How Indian Educational Institutes Use GoHighLevel to Manage Student Leads
9. GoHighLevel for Indian Healthcare Providers: Appointment Booking & Follow-Up Automation
10. How to Run WhatsApp Marketing Campaigns Using GoHighLevel in India

## Scheduler (scheduler.py)
Runs every 25 hours. Cycle order:
1. analytics.py — pull Transistor download data, update topic weights
2. retry-failed.py — recover partial failures
3. run-pipeline.py — generate + publish 20 podcast episodes (+ blog per episode)
4. 6-india-blog.py — publish 5 India blog topics
5. Send daily email summary to bill@reiamplifi.com
6. Sleep 25 hours, repeat

Daily email includes: episodes published, GHL blogs, India blogs, failed count, all-time totals, top categories, hot keywords.

## User Context
- Not a developer — explain in plain English
- Chromebook with Linux (Crostini) — NOT a Mac
- IDE: VS Code
- Budget: ~$70/month
- Active GHL user — use native GHL features before third-party tools
