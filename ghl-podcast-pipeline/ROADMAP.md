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

---

## Next Up 🔜

- [ ] Create podcast-specific GHL affiliate tracking link
      Replace link in .env so revenue from podcast is tracked separately

- [ ] Blog post generator
      Use saved article body (driveJsonId) + transcript (driveTranscriptId)
      → Claude writes SEO blog post per episode
      → Publish to website or Medium
      → More surface area for affiliate link

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
