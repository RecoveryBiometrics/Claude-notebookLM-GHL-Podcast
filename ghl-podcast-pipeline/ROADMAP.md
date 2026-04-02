# GHL Podcast Pipeline — Roadmap

Goal: fully automated content engine driving GHL affiliate signups via podcast + blog + static site.

---

## ✅ Pipeline — Fully Built & Running

- [x] Full automated pipeline (scrape → audio → SEO → transcript → publish)
- [x] Scheduler runs every 25 hours forever via systemd (survives reboots)
- [x] Daily email summary (start + completion) to configured in .env
- [x] Safe restarts — waits out remaining cycle time if restarted early
- [x] Retry agent for failed episodes (runs each cycle before main pipeline)
- [x] Full article discovery — 1,565 GHL help articles, newest first
- [x] Gemini Flash transcription attached to every episode
- [x] Article body + transcript saved to Google Drive (Audio/, Transcripts/, Articles/ subfolders)
- [x] Blog agent (5-blog.py) — DuckDuckGo SERP + Reddit research → Claude Haiku writes SEO post → saves to globalhighlevel-site/posts/ → auto-deploys to globalhighlevel.com
- [x] Stopped dual-publishing — all new posts go to globalhighlevel.com only (reiamplifi.com blog stopped)
- [x] Affiliate UTM links auto-added to every blog post
- [x] Styled blog posts — Table of Contents, CTA boxes, Pro Tip callouts, FAQ section
- [x] FAQ schema (JSON-LD) on every post — enables Google rich results
- [x] India blog agent (6-india-blog.py) — culturally adapted (WhatsApp, Razorpay, INR, DPDP Act)
- [x] Analytics agent — pulls Transistor download data, updates topic weights

---

## ✅ globalhighlevel.com — Built & Live

- [x] Domain purchased — globalhighlevel.com on Namecheap, Mar 11, 2026, ~$12/year
- [x] ~~Netlify free hosting~~ ⛔ HIT USAGE LIMIT — site paused. Migrating to Cloudflare Pages (see #1 priority)
- [x] Static site generator (build.py) — homepage, post pages, category pages, sitemap, 404, llms.txt
- [x] DNS pointed to Netlify — CNAME records set in Namecheap
- [x] SSL certificate live — HTTPS enabled on globalhighlevel.com ✅ Mar 11, 2026
- [x] 5-blog.py saves every post to globalhighlevel-site/posts/{slug}.json
- [x] Auto-deploy — scheduler Step 4 git pushes new posts → Netlify rebuilds site in 30 seconds
- [x] Homepage — dark theme, amber accent, Instrument Serif font, all sections complete
- [x] CLAUDE.md design standards — no generic AI aesthetics, affiliate link rules, verified facts only
- [x] All affiliate links use fp_ref=amplifi-technologies12 — no leaking commissions
- [x] Spotify podcast link live — https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV
- [x] llms.txt — auto-generated every build, lists all tutorials for AI model discoverability
- [x] robots.txt — explicitly allows GPTBot, ClaudeBot, PerplexityBot, Google-Extended
- [x] Google Search Console — globalhighlevel.com verified, sitemap submitted ✅ Mar 11, 2026
      ⚠️  ACTION: Check GSC in 3-5 days to confirm pages are being indexed

---

## ✅ Cloudflare Pages Migration — DONE (Mar 15, 2026)

- [x] Migrated from Netlify → Cloudflare Pages (free tier, unlimited bandwidth)
- [x] DNS moved from Namecheap BasicDNS → Cloudflare nameservers (kyrie.ns.cloudflare.com, lara.ns.cloudflare.com)
- [x] CNAME records pointed to claude-notebooklm-ghl-podcast.pages.dev
- [x] Custom domains: globalhighlevel.com + www.globalhighlevel.com
- [x] Build: root=globalhighlevel-site, command=python3 build.py, output=public
- [ ] Delete Netlify site (once Cloudflare fully verified)
- [ ] Update CLAUDE.md references from Netlify → Cloudflare

---

## 🔜 Next Up — In Priority Order


### 🚨 #1 — Google Analytics 4 (BLOCKING — no visibility into traffic or clicks)
- [ ] **Set up GA4** — create property at analytics.google.com, get G-XXXXXXXXXX measurement ID, inject gtag.js snippet into `globalhighlevel-site/build.py` base template `<head>`. This is the #1 priority — without it we can't tell if anyone is visiting, clicking CTAs, or where they drop off. Must be in place before scaling blog output.
- [ ] **Set up CTA click event tracking** — add GA4 custom events on all affiliate link clicks (nav CTA, inline CTA, end-of-post CTA, sidebar CTA). Lets us see which CTA placements actually convert.

### 🚨 #2 — Affiliate Tracker
- [ ] **Test affiliate-tracker.py** — script is built, needs first test run with `--headed` flag to verify browser navigation works correctly. Run: `venv/bin/python3 scripts/affiliate-tracker.py --headed`. If selectors miss, check screenshots in `logs/` and fix. Once working, wire into scheduler (runs daily before analytics.py). Scrapes: Referrals, Customers, Clicks, Unpaid Earnings → saves to `data/affiliate-stats.json`.

---

### globalhighlevel.com
- [ ] **Homepage redesign** — current design needs a full rethink. Reference Raycast.com, Resend.com, Framer.com. Write directly — do not use AI agents (token limit causes truncation). Amber accent, Instrument Serif, editorial layout are the right direction — execution needs work.
- [ ] **Migrate 48 existing GHL blog posts** — one-off script: fetch from GHL API → save as posts/{slug}.json → push → Netlify deploys. Do before reaching 100 posts.
- [ ] **301 redirects** — reiamplifi.com/blog/* → globalhighlevel.com/blog/* after migration
- [x] **Google Analytics 4** — moved to #1 priority above
- [ ] **GSC Monitoring Agent** — weekly script using GSC API: checks pages indexed, flags crawl errors, includes report in daily email
- [ ] **GSC indexing check** — ⚠️ Visit search.google.com/search-console in 3-5 days to confirm globalhighlevel.com pages are indexed by Google

### SEO

#### 🚨 GSC Intelligence Agent (7-gsc-agent.py) — NEW
Two-part system that turns Google Search Console data into automated content actions.

**Agent 1 — GSC Analyst (gsc-analyst.py)**
Connects to GSC API, runs weekly analysis:
- **Keyword gaps** — queries where site appears on page 2-3 (positions 11-30) that need dedicated content
- **Cannibalization** — multiple pages competing for the same query, killing each other's rankings
- **Declining pages** — posts losing impressions/clicks over 7/14/30 day windows
- **High-impression / low-CTR** — pages ranking but not getting clicks (title/description needs work)
- **Zero-click queries** — queries with impressions but 0 clicks (featured snippet opportunity)
- **New keyword opportunities** — queries driving traffic that don't have dedicated content yet
- **Content freshness** — pages that haven't been updated in 60+ days on competitive queries
- Outputs: `data/gsc-report.json` with prioritized action items + includes in daily email summary

**Agent 2 — Content Gap Builder (gsc-content-builder.py)**
Reads `data/gsc-report.json` and takes automated action:
- Creates new posts targeting keyword gaps (feeds into 5-blog.py)
- Rewrites titles/meta descriptions for low-CTR pages
- Merges or redirects cannibalized pages
- Refreshes stale content with updated info
- Builds new pillar pages when cluster of related gaps detected
- Logs all actions to `data/gsc-actions-log.json`

**Architecture note:** This is a reusable pattern — build it site-agnostic so every new site gets the same GSC intelligence automatically. Config per site: GSC property URL, posts directory, blog agent script.

---

- [x] **Internal Linking Agent** — `inject_internal_links()` in build.py: 5 contextual cross-links per post at build time, keyword matching from titles, same-category preferred. Applied to all 312 posts on next deploy.
- [ ] **Pillar pages** — 4-5 long-form hub pages (3,000+ words) that smaller posts link back to. Builds topical authority. Examples: "Complete GoHighLevel Guide for Agencies", "GoHighLevel Automation Masterclass"
- [ ] **Author + About page** — Google E-E-A-T rewards real author profiles. "About William Welch" page + author bio on every post.
- [ ] **Featured images** — each post should have a unique image (auto-generate with AI)
- [ ] **Article schema** — author, publish date, modified date on every post
- [ ] **Core Web Vitals** — run PageSpeed Insights on globalhighlevel.com, target 90+ score

### Content & Distribution
- [ ] **Social Media Agent** — auto-posts to X, LinkedIn, Instagram, Facebook per episode
- [ ] **YouTube** — upload audio as video (static image + audio). Each episode = YouTube search surface.
- [ ] **Email newsletter** — weekly roundup of that week's episodes
- [ ] **Content Gap Agent** — checks analytics every 7/14/30 days, identifies gaps, prioritizes scraper queue

### International Expansion
- [ ] **UK / Australia** — English, different examples (pounds/AUD, local context). High GHL adoption.
- [ ] **Philippines** — English. Massive digital agency market.
- [ ] **Brazil** — Portuguese. Huge digital agency market.
- [ ] **Mexico / Latin America** — Spanish.

### Pipeline Improvements
- [ ] **Log rotation** — archive pipeline.log weekly so it doesn't grow forever
- [ ] **Slack/Discord alert** — notify if scheduler stops unexpectedly
- [ ] **Duplicate detector** — ensure same article never gets published twice
- [ ] **GHL changelog monitor** — detect new GHL articles immediately instead of waiting for daily cache rebuild
- [ ] **Episode quality check** — flag episodes under X seconds (bad audio)
- [ ] **Email reliability** — Gmail SMTP failed once (Cycle #2, Mar 10). If it fails again, regenerate app password at myaccount.google.com → Security → App passwords

### Revenue & Analytics
- [ ] **Affiliate click tracking** — redirect page at reiamplifi.com/ghl logs every click with source
- [ ] **Stream tracker** — pull Transistor analytics weekly into published.json
- [ ] **Revenue dashboard** — simple page showing streams → projected affiliate revenue

---

## Bigger Ideas

- [ ] Replicate pipeline for other affiliate programs (Kajabi, ClickFunnels, HubSpot)
- [ ] Sell the pipeline as a service to other affiliates
- [ ] Build a second podcast in a different niche using same infrastructure
- [ ] Agent that monitors GHL community comments/reviews and responds with affiliate link

---

## Notes

- Article body stored as driveJsonId — ready for blog post agent
- Transcript stored as driveTranscriptId — ready for repurposing agent
- All episode data in published.json — single source of truth for all agents
- Pipeline is stable — good foundation to build agents on top of
- Namecheap login: stored in .env
- ~~Netlify site~~ — DEPRECATED, hit usage limit. Migrated to Cloudflare Pages.
- **Never use Netlify again** — bandwidth cap (100GB/mo) is incompatible with our content volume
- GSC verified: verification code stored in .env
