# Article template (Peter Attia "Straight Dope" model)

This template governs every trade post the pipeline produces. Do not deviate without Bill's written approval. The reference point is Peter Attia's [The Straight Dope on Cholesterol – Part I](https://peterattiamd.com/the-straight-dope-on-cholesterol-part-i/) and its 9 part series.

Study that post before writing. The style is not optional decoration. It is the moat.

## The 12 elements every part must contain

### 1. Pre-intro framing (1 short paragraph, before any heading)

One paragraph. No heading. Sets the scene. Names the reader directly by role and situation.

Example opening for "Why plumbers need a CRM in 2026":
> If you run a plumbing business with one truck or fifteen, you already know the math. The first call to a lead beats the second. The appointment reminder beats the no show. The follow up beats the quiet quote. This post is about the specific system that closes those loops, how it works, and why the trades are the ones adopting it fastest right now.

What the opening does:
- Names who the reader is ("run a plumbing business with one truck or fifteen")
- Names the problem in concrete terms ("first call beats the second")
- Promises what the post explains
- Does not introduce GoHighLevel yet. That happens in the body.

Rules:
- Maximum 80 words
- No "in this post we will explore"
- No "in today's fast paced world"
- No em-dash anywhere

### 2. Learning objectives (numbered, Attia style)

Immediately after the pre-intro. A box or list styled to stand out.

Example:
> **By the end of this post you will understand:**
> 1. Why the standard "missed call" pattern is the single biggest leak in a small trade business.
> 2. How a CRM built around SMS and voice, not just email, changes that math.
> 3. The specific automations plumbing shops run that produce measurable recovery of lost leads.
> 4. What the current alternative tools do differently and where they fall short.
> 5. What a reasonable first month of using one of these tools looks like for a two truck shop.

Rules:
- 5 to 8 bullets
- Numbered, not bulleted
- Each item is a concrete thing the reader will know, not a vague promise
- Mirrors the buyer journey intent of this part

### 3. "Concepts to grasp" block

Short section. Not a glossary. These are the 3 to 5 mental models the reader needs to carry through the whole post.

Example for Part 1:
> **Concepts to grasp**
>
> **Lead-to-close window.** The time between a prospect first contacting a business and the business confirming the appointment or quote. Every hour this window stays open, conversion rate drops.
>
> **First touch channel.** The channel the prospect used to reach the business (phone, form, text, review site). Matters because automations have to match the channel the lead came in on.
>
> **Recovery path.** The pre-built sequence of messages that runs when a human response does not happen within a target time.

Rules:
- 3 to 5 concepts
- Bold the concept name on first use
- One sentence definition, one sentence on why it matters
- No jargon dump. Only concepts used later in the post.

### 4. Body sections (H2 + H3 hierarchy)

H2 sections cover the post's main arguments. H3 sections carry questions and sub-topics within each H2.

Rules:
- H2 count: 5 to 8 for a 2,500 to 4,000 word post
- Every H2 uses either a direct statement ("The missed call is the biggest leak") or a query phrase ("What does a lead-to-close window actually look like")
- H3 inside H2 as questions ("Why does SMS beat email for this") or sub-claims
- No H4 or deeper
- No skipping levels (no H2 -> H4)

### 5. One sustained analogy per part

Peter Attia teaches complex biochem by analogy. Trucks carry cargo. Traffic moves through pipes. Do the same.

Rules:
- One primary analogy per part
- Introduced by mid-post
- Referenced again in at least two later sections
- Does not stretch past its fit
- Plumber series can use plumbing analogies for tech
- Electrician series can use electrical analogies for automation
- Pick an analogy that actually makes the technical idea clearer, not just cute

### 6. Q&A embedded in sections

Inside body sections, use question headings when a reader would naturally ask that question.

Example:
> ### Why does SMS beat email for service trade leads
>
> Because the people who need a plumber at 9pm on a Tuesday are not checking email. They are holding their phone and looking at the last person who texted them back. The channel the lead used to reach you tells you which channel they want the response on.

Rules:
- At least 2 Q&A style H3s per part
- Questions phrased how a reader would actually think them, not how marketing would phrase them
- Answers are 1 to 3 paragraphs, not bullet points

### 7. Bold on first use of a technical term

First time a term appears in the body, bold it. Do not bold the same term twice. This shows expertise without belaboring.

Examples:
- First mention of **workflow automation** in bold
- First mention of **A2P 10DLC** in bold if the post gets into SMS compliance
- First mention of **two-way SMS** in bold

Rules:
- Only on first use
- Only for actual technical terms, not generic marketing words
- Never bold entire sentences for emphasis

### 8. Footnotes for factual claims

Every number, every percentage, every cited spec, every feature claim must have a footnote that links to the primary source.

Format:
> The GoHighLevel Starter plan includes unlimited contacts and unlimited users.[^1]
>
> [^1]: Pricing page, GoHighLevel.com, current as of [month year].

Rules:
- 2 to 5 footnotes per part
- Sources must be primary (GHL docs, trade association publications, government data), not blog posts
- If a number cannot be footnoted to a primary source, rewrite the sentence to remove the number
- All external links open in new tab with `rel="nofollow noopener"` when appropriate

### 9. Mid-post CTA block (three-tier routing)

Every trade post uses the same three-tier CTA pattern. See memory `feedback_no_done_for_you_work.md` for the canonical routing rule. Every tier has its own CTA on every post.

**Primary CTA (top and bottom of post).** Boxed, branded, links to `/trial/` with UTM campaign `trades-[trade]-part[N]-[position]`. The link goes to the GHL affiliate via your domain's redirect or direct affiliate URL. Target reader: self-service buyer.

Copy pattern:
> "Start your free 30-day GoHighLevel trial. No credit card required. [Button: Start Free Trial]"

**Secondary CTA (mid-post, between H2 #3 and H2 #4).** Boxed, branded differently (softer amber border), links to Extendly affiliate URL with the appropriate `deal=vqzoli` parameter. Target reader: help-needed buyer.

Copy pattern:
> "Prefer done-for-you setup? Extendly handles GoHighLevel onboarding, 24/7 white-label support, and pre-built snapshots for [trade] businesses. We recommend them for anyone who wants the system running without doing the setup themselves. [Button: Check out Extendly]"

**Tertiary CTA (gated, in footer).** Small link or collapsed section, visible only to qualified inbound. Target reader: enterprise.

Copy pattern:
> "Running a $5M+ [trade] business and want GoHighLevel embedded as core infrastructure? Enterprise engagement starts at $7,500/month with a 12-month minimum. [Small link: Inquiry form]"

**Rules:**
- Never write "book a call with Bill"
- Never write "1-on-1 coaching"
- Never write generic "work with us"
- Never imply that REI Amplifi delivers implementation work below the enterprise floor
- Fact checker verifies all three CTAs are present and correctly worded before publish

### 10. Up next teaser

Every part except the last in a series closes with an "Up next" block. One paragraph. Names the next part. Tells the reader why it matters.

Example at the end of Part 1:
> **Up next in Part 2**
>
> Part 2 looks at the actual CRM options a plumbing shop considers in 2026. The candidates, the tradeoffs, and the one factor that decides between them for most trade businesses. If Part 1 convinced you the problem is real, Part 2 picks the tool.

Rules:
- One paragraph, 50 to 80 words
- Internal link to the next part's URL
- No clickbait. Actually summarize.
- The last part in a series instead closes with a "Start your 30 day trial" CTA box.

### 11. Footer CTA

After the body content and before the standard site footer. Boxed, branded, larger than the mid-post CTA. Links to `/trial/` with a UTM campaign of `trades-[trade]-part[N]-footer`.

Rules:
- Direct copy: "Start your 30 day GoHighLevel trial"
- Three lines of support text maximum
- One button
- No fabricated social proof

### 12. Author byline and schema

Every part ends with:
- Author line: "Written by William Welch | globalhighlevel.com"
- Schema block (generated, not hand written): Article, BreadcrumbList, FAQPage for any embedded Q&A, isPartOf linking to the series hub

Use the canonical William bio from `reference_william_welch_bio.md` memory. Do not add credentials or experience claims.

## Length

| Tier | Part length |
|---|---|
| Tier 1 | 2,500 to 4,000 words per part |
| Tier 2 | 1,800 to 2,500 words per part |
| Tier 3 | 2,500 to 3,500 words (single flagship post covers everything) |

Under means padding. Over means the fact checker stripped claims and the writer did not rewrite.

## Title and meta rules

H1 and meta title are usually the same, with the site name appended to meta title only.

H1 format for each part:
| Part | H1 template |
|---|---|
| 1 | "Why [trade plural] need a CRM in 2026" |
| 2 | "The best CRM for [trade plural] this year" |
| 3 | "GoHighLevel vs [competitor] for [trade plural]: honest comparison" |
| 4 | "How to set up GoHighLevel for a [trade singular] business" |
| 5 | "The GoHighLevel workflows [trade plural] actually use" |
| 6 | "GoHighLevel pricing for a [trade] business: the real numbers" |
| 7 | "What changes in month 1 when a [trade] adopts GoHighLevel" |
| 8 | "Is GoHighLevel worth it for a solo [trade singular]?" |
| 9 | "Common mistakes [trade plural] make in their GoHighLevel setup" |

Meta description: 150 to 158 characters. Contains the primary keyword within the first 80 characters. Contains one buyer signal (pricing, trial, specific outcome category).

## Forbidden structural elements

- Table of contents sidebars (breaks the flow)
- Emoji in headings
- Auto generated "Key takeaways" at the top (duplicate of learning objectives)
- Comparison tables longer than 6 rows (Attia uses prose comparisons)
- Exit intent popups
- Floating CTAs that follow the scroll
- "In conclusion" or "To conclude" as the final H2

## Banned AI tell phrases

These kill the style. Fact checker strips every occurrence. Writer prompt includes this list.

- "leverage"
- "utilize" (use "use")
- "harness"
- "unlock" (unless literally unlocking something)
- "elevate"
- "take it to the next level"
- "dive into"
- "deep dive"
- "let's dive in"
- "in this blog post, we'll explore"
- "the world of [topic]"
- "streamline your workflow"
- "game-changer"
- "revolutionize"
- "empower"
- "seamlessly"
- "it's important to note"
- "whether you're a beginner or an expert"
- "in today's fast-paced world"
- "In conclusion"
- "To wrap up"
- "To conclude"
- All em-dashes (use comma, period, or paren)

## Fact check rules specific to trades content

In addition to the universal "Never fabricate" and "Never claim about William" rules:

- No fabricated case studies
- No named specific customer unless Bill has provided the name in writing
- Pricing numbers must match current GHL pricing YAML
- Any trade specific stat (e.g. "plumbers spend X hours on admin") must footnote to a primary source or get cut
- No "trusted by" or "used by" claims
- No invented feature names (e.g. if GHL does not have a "Plumber Portal", do not invent one)
- Comparison tables (if used) must match current competitor pricing pages

## Author voice checklist the writer must hit

- First paragraph names a concrete reader ("If you run a plumbing business with one truck...")
- Short sentences mixed with medium ones
- Specific numbers over abstract words
- Direct address (you, your)
- Concrete examples clearly marked as hypothetical
- No marketing adjectives (revolutionary, cutting edge, world class)
- No vague intensifiers (really, very, extremely) unless intentional
