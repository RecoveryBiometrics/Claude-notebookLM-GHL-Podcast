# GHL Podcast Pipeline — Roadmap

Ideas and future builds. Goal: agents tackle this list automatically.

---

## In Progress / Done ✅

- [x] Full automated pipeline (scrape → audio → SEO → transcript → publish)
- [x] Scheduler runs every 25 hours forever
- [x] Systemd service (survives reboots, auto-restarts)
- [x] Daily email summary to bill@reiamplifi.com
- [x] Safe restarts (timestamp file)
- [x] Retry agent for failed episodes
- [x] Full article discovery (1,565 articles, newest first)
- [x] Gemini Flash transcription attached to every episode
- [x] Article body + transcript saved to Google Drive for future use
- [x] Blog agent (5-blog.py) — DuckDuckGo SERP + Reddit research → Claude Haiku writes SEO blog post → auto-publishes to reiamplifi.com/blog via GHL API
- [x] Blog wired into pipeline — runs automatically as Step 4 after every Transistor upload
- [x] Affiliate UTM links auto-added to every blog post (utm_source=blog&utm_medium=article&utm_campaign={slug})
- [x] Styled blog posts — Table of Contents, CTA boxes, Pro Tip callouts, FAQ section
- [x] FAQ schema (JSON-LD) injected into every post with a FAQ section — enables Google rich results
- [x] Google Drive organized into subfolders — Audio/, Transcripts/, Articles/
- [x] .env backed up to Google Drive (.env Backup — GHL Pipeline folder)

---

## ⚠️ PLATFORM MIGRATION — Move Blog to globalhighlevel.com on Netlify

**Decision made: Migrate blog off GHL to a dedicated static site before reaching 100 posts.**

### Why
- `reiamplifi.com` reads as a real estate site — confusing for GHL visitors, bad brand signal to Google
- GHL blog platform has a hard ceiling: poor Core Web Vitals, no SEO plugins, not built for 500+ posts
- Static hosting on Netlify = perfect page speed, free, full SEO control

### The Domain
- **`globalhighlevel.com`** ✅ PURCHASED — Mar 11, 2026, registered on Namecheap
- Clean, no confusion, exact search intent match, topically perfect for Google

### The Stack
- **Domain:** globalhighlevel.com (~$12/year — Namecheap)
- **Hosting:** Netlify (free — auto-deploys from GitHub on every pipeline push)
- **SEO:** Schema markup injected by pipeline (already doing FAQ schema), sitemap auto-generated
- **CMS:** None needed — the pipeline IS the CMS
- **GHL stays:** reiamplifi.com remains on GHL for funnels, CRM, contacts, automations

### Build Steps (execute in this order)
- [x] **Step 1** — Buy `globalhighlevel.com` on Namecheap ✅ DONE Mar 11, 2026
- [x] **Step 2** — Create free Netlify account ✅ DONE Mar 11, 2026
- [x] **Step 2b** — SSL certificate provisioning: DNS verified ✅ but "certificate parameter" error on provision button. Check back in 1-2 hours — Netlify auto-provisions in background. Visit Site configuration → Domain management → provision if still showing.
- [x] **Step 3** — Build static site structure ✅ DONE — homepage, post pages, categories, sitemap, 404
- [x] **Step 3b** — Two-agent homepage design system ✅ DONE — Designer + Manager agents built conversion-optimized landing page (design-homepage.py → homepage_hero.html). Re-run anytime to regenerate.
- [x] **Step 4** — 5-blog.py now saves every post to globalhighlevel-site/posts/{slug}.json ✅ DONE — pipeline auto-populates site on every run
- [x] **Step 5** — DNS pointed to Netlify ✅ DONE — CNAME records set in Namecheap Mar 11, 2026
- [ ] **Step 5b — CHECK SSL** — Visit Netlify → Site configuration → Domain management. If SSL still shows "could not provision" click Provision certificate. Should auto-resolve within 1-2 hrs of DNS propagation. Once green, globalhighlevel.com is fully live with HTTPS.
- [ ] **Step 6** — Migrate 48 existing GHL blog posts to the new site
      HOW: Run a one-off script to fetch HTML from GHL API for each published post → save as posts/{slug}.json → push → Netlify deploys
- [ ] **Step 7** — Set 301 redirects from old reiamplifi.com/blog URLs to globalhighlevel.com
- [ ] **Step 8** — Submit globalhighlevel.com sitemap to Google Search Console
      URL: https://globalhighlevel.com/sitemap.xml

### After Migration
- Every pipeline run pushes new HTML files to GitHub → Netlify auto-deploys in 30 seconds
- globalhighlevel.com becomes the SEO content hub for all countries/languages
- reiamplifi.com stays as the GHL business/funnel site

---

## Next Up 🔜

- [x] **Buy globalhighlevel.com** — purchased Mar 11, 2026 ✅
- [x] **Build globalhighlevel.com static site** — ✅ DONE Mar 11, 2026 — live at courageous-taiyaki-2c1846.netlify.app
- [ ] **NEXT SESSION — Pick up here:** Check SSL on Netlify (Step 5b above), then run Step 6 (migrate 48 existing posts), then Step 7 (301 redirects), then Step 8 (Google Search Console)
- [ ] **Google Search Console** — Verify reiamplifi.com/blog in GSC, submit sitemap. Check SafePath workspace — may already be connected. Without this, posts may not be indexed.
- [ ] **Internal Linking Agent** — When publishing a new blog post, search published.json for related posts and inject 2-3 internal links. Biggest SEO gap right now. Use RankMath's suggestions post-migration.
- [ ] Social Media Employee Agent — auto-posts to X, LinkedIn, Instagram, Facebook per episode
- [ ] Content Gap Optimization Agent — checks analytics every 7/14/30 days, identifies gaps, prioritizes scraper queue
- [ ] GA4 setup on reiamplifi.com — track blog traffic and user behavior

---

## SEO Foundation Checklist (build these out systematically)

- [ ] **Pillar pages** — 4-5 long-form hub pages (3,000+ words) that smaller posts link back to
      Examples: "Complete GoHighLevel Guide for Agencies", "GoHighLevel Automation Masterclass"
      These build topical authority — Google sees the site as THE source on GHL
- [ ] **Author + About page** — Google E-E-A-T rewards real author profiles. "About William Welch" page + author bio on every post improves trust signals
- [ ] **Featured images** — Currently every post uses the same stock GHL image. Each post should have a unique relevant image (can be auto-generated with AI)
- [ ] **Breadcrumb schema** — Helps Google understand site structure, shows breadcrumbs in search results
- [ ] **Article schema** — Marks up each post with author, publish date, modified date — trust signals for Google
- [ ] **Core Web Vitals** — Post-WordPress migration, run PageSpeed Insights and fix any issues. Target 90+ score.

---

## International Expansion (Country-by-Country)

GHL is growing globally. Each market needs localized content, not just translated posts.

- [x] India — 6-india-blog.py live, culturally adapted (WhatsApp, Razorpay, INR, DPDP Act)
- [ ] **UK / Australia** — Same English, different examples (pounds/AUD, local business context). High GHL adoption.
- [ ] **Brazil** — Portuguese. Huge digital agency market. GHL growing fast there.
- [ ] **Mexico / Latin America** — Spanish. Same pipeline as Spanish expansion below.
- [ ] **Philippines** — English. Massive digital agency market. Very GHL-friendly.

For each country:
- Separate blog category with country tag
- Affiliate UTM: `utm_country=XX` appended
- Localized affiliate link if GHL offers country-specific ones
- Cultural adaptation (payment methods, local CRM competitors, local regulations)

---

## Content & Distribution

- [ ] YouTube — upload audio as video (static image + audio)
      Each episode = YouTube video = more search surface
- [ ] Twitter/X auto-post when each episode goes live
      Pull seoTitle + affiliateLink, post automatically
- [ ] LinkedIn auto-post (agency owners are on LinkedIn)
- [ ] Email newsletter — weekly roundup of that week's episodes
- [ ] Spanish language expansion — duplicate pipeline for Spanish blogs + podcasts

---

## Revenue & Analytics

- [ ] Stream tracker — pull Transistor analytics weekly into published.json
      Update streams count per episode automatically
- [ ] Revenue dashboard — simple page showing streams → projected revenue
- [ ] A/B test SEO title formulas — track which formats get more streams
- [ ] Google Search Console integration — see which blog posts and podcast pages rank on Google
- [ ] Affiliate click tracking — custom redirect page at reiamplifi.com/ghl logs every click with source

---

## Pipeline Improvements

- [ ] Email reliability — Gmail SMTP failed once (Cycle #2, Mar 10) with 535 credentials error despite valid app password. Keep an eye on summary emails each cycle — if it happens again, regenerate the app password at myaccount.google.com → Security → App passwords
- [ ] Log rotation — archive pipeline.log weekly so it doesn't grow forever
- [ ] Slack/Discord alert if scheduler stops unexpectedly
- [ ] Episode quality check — flag episodes under X seconds (bad audio)
- [ ] Duplicate detector — make sure same article never gets published twice
- [ ] GHL changelog monitor — detect new articles as soon as GHL publishes them
      Instead of waiting for daily cache rebuild

---

## Bigger Ideas

- [ ] Replicate pipeline for other affiliate programs
      Same system, different help docs (e.g. Kajabi, ClickFunnels, HubSpot)
- [ ] Sell the pipeline as a service to other affiliates
- [ ] Build a second podcast in a different niche using same infrastructure
- [ ] Agent that monitors comments/reviews and responds with affiliate link

---

## Notes

- Article body stored as driveJsonId — ready for blog post agent
- Transcript stored as driveTranscriptId — ready for repurposing agent
- All episode data in published.json — single source of truth for all agents
- Pipeline is stable — good foundation to build agents on top of
- At 48 posts (Mar 2026) — migration window to WordPress is still easy. Don't wait.
