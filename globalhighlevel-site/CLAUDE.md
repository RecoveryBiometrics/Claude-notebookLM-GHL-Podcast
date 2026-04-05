# Frontend Design Standards — GlobalHighLevel.com

## Brand & Audience
- Site: GlobalHighLevel.com — free GoHighLevel tutorials and affiliate site
- Audience: Digital marketing agency owners, freelancers, business owners
- Tone: Confident expert talking to a peer. Not a salesperson. Not a blogger.
- Goal: Affiliate signups for GHL 30-day free trial

## Design Rules — Non-Negotiable

### NO generic AI aesthetics:
- No purple/violet gradients
- No Inter or Roboto as the primary display font
- No "glassmorphism" cards with blur effects
- No generic blue (#3b82f6) as the accent
- No grid-of-3-feature-cards with emoji icons as the only layout idea

### DO use distinctive choices:
- Pick ONE unexpected accent color (amber, coral, lime, copper — not blue, not purple)
- Use DM Sans 800 for headlines (loaded via Google Fonts)
- DM Sans for body copy — clean and readable
- Asymmetric layouts, pull-quotes, editorial treatments
- CSS animations: entrance fades, scroll reveals (CSS only, no JS deps)
- Generous whitespace — let the content breathe

### Typography hierarchy:
- Headlines: DM Sans 800, clamp(2rem, 4vw, 3.5rem), line-height 1.15, letter-spacing -.5px
- Section headlines: DM Sans 800, 1.5rem
- Body: 19px, DM Sans 400, line-height 1.75
- Labels/eyebrows: 13px, uppercase, letter-spacing .5px

### Color palette:
- Background: Near-black (#07080a)
- Surface cards: #111520
- Accent: Amber (#f59e0b) or another non-generic choice — decide before building
- Text: #eef2ff (primary), #7c8aab (secondary), #3d4a63 (muted)
- Do NOT use blue as the primary accent

## Affiliate Link Rules — NEVER Break These

- **Every single link to GoHighLevel.com MUST use the affiliate link** — no exceptions
- Affiliate link: `https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12`
- Always append UTM params: `&utm_source=globalhighlevel&utm_medium={location}&utm_campaign={context}`
- This includes: pricing pages, feature pages, sign-up pages, help links — ANYTHING on gohighlevel.com
- NEVER link to `gohighlevel.com/pricing` or any GHL URL without `fp_ref=amplifi-technologies12`
- All affiliate links: `target="_blank" rel="nofollow noopener"`
- **No placeholder `#` links** — if the real URL isn't known, link to `/category/gohighlevel-tutorials/` or `/`
- Spotify podcast link: `https://open.spotify.com/show/28LLaXVbmnHUMNBFGdgdlV`

## Verified Facts (use ONLY these — invent nothing)
- Site: GlobalHighLevel.com — free GHL tutorials
- Podcast: "Go High Level" on Spotify
- Podcast stats: 380+ followers
- Top episode: "GoHighLevel Conversation AI Bot"
- Content: 490+ published posts (English, India, Spanish)
- Offer: GoHighLevel 30-day FREE trial (double the standard 14-day trial)
- GHL starts at $97/month
- Affiliate link: https://www.gohighlevel.com/highlevel-bootcamp?fp_ref=amplifi-technologies12
- Do NOT hardcode stream counts or follower numbers — they change. Check analytics if needed.

## DO NOT invent:
- Testimonials or reviews
- Income claims or revenue numbers
- Student counts or community sizes
- Awards, press mentions, certifications
