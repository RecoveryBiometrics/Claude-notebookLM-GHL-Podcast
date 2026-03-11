# GHL Podcast Pipeline — Roadmap

Goal: fully automated content engine driving GHL affiliate signups via podcast + blog + static site.

---

## ✅ Pipeline — Fully Built & Running

- [x] Full automated pipeline (scrape → audio → SEO → transcript → publish)
- [x] Scheduler runs every 25 hours forever via systemd (survives reboots)
- [x] Daily email summary (start + completion) to bill@reiamplifi.com
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

- [x] Domain purchased — globalhighlevel.com on Namecheap (wcw1985), Mar 11, 2026, ~$12/year
- [x] Netlify free hosting — auto-deploys from GitHub on every push
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

## 🔜 Next Up — In Priority Order

### globalhighlevel.com
- [ ] **Homepage redesign** — current design needs a full rethink. Reference Raycast.com, Resend.com, Framer.com. Write directly — do not use AI agents (token limit causes truncation). Amber accent, Instrument Serif, editorial layout are the right direction — execution needs work.
- [ ] **Migrate 48 existing GHL blog posts** — one-off script: fetch from GHL API → save as posts/{slug}.json → push → Netlify deploys. Do before reaching 100 posts.
- [ ] **301 redirects** — reiamplifi.com/blog/* → globalhighlevel.com/blog/* after migration
- [ ] **Google Analytics 4** — create GA4 property at analytics.google.com, get G-XXXXXXXXXX measurement ID, inject into build.py base template. Do after traffic starts coming in.
- [ ] **GSC Monitoring Agent** — weekly script using GSC API: checks pages indexed, flags crawl errors, includes report in daily email
- [ ] **GSC indexing check** — ⚠️ Visit search.google.com/search-console in 3-5 days to confirm globalhighlevel.com pages are indexed by Google

### SEO
- [ ] **Internal Linking Agent** — on each new post, search published.json for related posts, inject 2-3 internal links. Biggest SEO gap right now.
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
- Namecheap login: wcw1985 (stored in .env)
- Netlify site: courageous-taiyaki-2c1846.netlify.app → globalhighlevel.com
- GSC verified: TqqkuU1JDcd_0KnXbs_wGvyamJucFYVZiSLx9ICbeq4 (stored in .env)
