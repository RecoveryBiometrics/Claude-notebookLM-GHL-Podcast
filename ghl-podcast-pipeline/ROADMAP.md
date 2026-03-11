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

---

## Next Up 🔜

- [ ] Spanish language expansion — duplicate pipeline for Spanish blogs + podcasts
- [ ] Social Media Employee Agent — auto-posts to X, LinkedIn, Instagram, Facebook per episode
- [ ] Content Gap Optimization Agent — checks analytics every 7/14/30 days, identifies gaps, prioritizes scraper queue
- [ ] GA4 setup on reiamplifi.com — track blog traffic and user behavior

---

## Content & Distribution

- [ ] YouTube — upload audio as video (static image + audio)
      Each episode = YouTube video = more search surface
- [ ] Twitter/X auto-post when each episode goes live
      Pull seoTitle + affiliateLink, post automatically
- [ ] LinkedIn auto-post (agency owners are on LinkedIn)
- [ ] Email newsletter — weekly roundup of that week's episodes
- [ ] Show notes page — dedicated website pulling from published.json

---

## Revenue & Analytics

- [ ] Stream tracker — pull Transistor analytics weekly into published.json
      Update streams count per episode automatically
- [ ] Revenue dashboard — simple page showing streams → projected revenue
- [ ] A/B test SEO title formulas — track which formats get more streams
- [ ] Google Search Console integration — see which episodes rank on Google

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
