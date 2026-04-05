# Podcast Pipeline — GlobalHighLevel.com

## Architecture
- **VPS:** IONOS at 74.208.190.10, SSH key `~/.ssh/ionos_ghl`, scripts at `/opt/ghl-pipeline/`
- **Site:** globalhighlevel.com on Cloudflare Pages, auto-deploys on git push
- **Repo:** RecoveryBiometrics/Claude-notebookLM-GHL-Podcast
- **Posts:** Two copies must stay in sync: `posts/` and `globalhighlevel-site/posts/`
- **Build:** `globalhighlevel-site/build.py` generates static HTML from post JSONs

## Pipeline Cycle (25 hours, runs on VPS via systemd)
```
0a. analytics.py        — Pull Transistor download data, update topic weights
0b. gsc-topics.py       — Analyze GSC data, flag low-CTR + almost-page-1 pages
0c. 8-seo-optimizer.py  — Weekly: rewrite titles/descriptions, expand content (10 pages/week)
1.  retry-failed.py     — Retry failed episodes from last cycle
2.  run-pipeline.py     — Generate 20 episodes (scrape → NotebookLM audio → SEO → upload → blog)
3.  6-india-blog.py     — 5 India-focused blog posts
4.  7-spanish-blog.py   — 5 Spanish blog posts
5.  deploy_site()       — git push posts/ → Cloudflare Pages rebuilds
    → Email summary, Slack reports, ops-log
```

## Output Per Cycle
- 20 podcast episodes + 20 English blogs
- 5 India blogs + 5 Spanish blogs
- SEO optimizer: up to 10 pages/week (title rewrites + content expansions)

## Teams (from agent-command-center)
- **Content Production Team** (24/7): Scheduler → Scraper → Audio → SEO → Upload → Blog
- **SEO Optimizer Team** (weekly): GSC Analyst → Researcher → Content Writer → Fact Checker → Engineer

## Slack Routing
- **#ops-log** (C0AQG0DP222): All pipeline events flow here via `ops_log.py`
- **#ceo** (C0AQAHSQK38): Daily CEO digest summarizing ops-log
- **#globalhighlevel** (C0AQ95LG97F): Detailed daily pipeline report
- Uses `SLACK_BOT_TOKEN` (Bot Token API), not webhooks, for channel posting
- `OPS_LOG_WEBHOOK_URL` in VPS .env as fallback

## SEO Optimizer (8-seo-optimizer.py)
- Runs weekly (gated by `seo-optimizer-state.json`)
- Reads flags from `gsc-topics.json` (low CTR pages, almost-page-1 pages)
- 5 roles: GSC Analyst → Researcher (SERP + Reddit) → Content Writer → Fact Checker → Engineer
- 28-day cooldown per page, auto-retries once if CTR didn't improve
- Changes logged to `data/seo-changelog.json` + Google Sheet (ID in projects.yml)
- Google Sheet: "SEO Changelog Tracker — GlobalHighLevel" in bill@reiamplifi.com Drive

## Key Gotchas
- **NotebookLM auth expires ~every 2 weeks.** Session at `~/.notebooklm/storage_state.json`. Re-login: `venv/bin/notebooklm login` locally, then `scp` to VPS `~/.notebooklm/`
- **public/ is gitignored.** Build output must never be tracked — causes deploy conflicts on VPS
- **VPS scripts are not a git checkout.** Sync manually via `scp` after changes
- **3-seo.py generates podcast SEO metadata** (title, description, tags for Transistor). **5-blog.py generates blog posts.** Different scripts, different outputs.
- **gsc-topics.py cooldown:** 28 days. Don't re-flag pages before changes take effect in Google.

## Key Data Files
```
data/
  published.json          — All episodes + blog status
  india-published.json    — India blog tracking
  spanish-published.json  — Spanish blog tracking
  gsc-stats.json          — Google Search Console data (28 days)
  gsc-topics.json         — Flagged pages for SEO optimizer
  seo-changelog.json      — Before/after log for all SEO optimizations
  seo-cooldown.json       — 28-day cooldown tracker per page
  seo-optimizer-state.json — Weekly gate (last run timestamp)
  topic-weights.json      — Hot keywords from download analytics
  ops-log.json            — Centralized ops-log entries
  ops-status.json         — Structured status for Pipeline Doctor
```

## Affiliate Link
All GHL links must include `fp_ref=amplifi-technologies12`. See `globalhighlevel-site/CLAUDE.md` for full rules.
