# Hub page structure (the 8 elements)

The series hub lives at `/{lang}/para/[vertical]/` (or `/for/[vertical]/` for EN/IN, `/ar/لـ/[vertical]/` for AR) and acts as topical authority for a 9-part series. Every hub MUST contain these 8 elements in this exact order.

## 1. Primary CTA (top — first line, before pre-intro)

```html
<p style="background:#111520;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:4px;color:#eef2ff;">
<strong>🚀 {primary_cta_headline}</strong> {primary_cta_subhead} 
<a href="{trial_url}" style="color:#f59e0b;" target="_blank">{primary_cta_link_text} →</a>
</p>
```

Per language:
- ES: `🚀 Prueba GoHighLevel GRATIS por 30 días` / `Sin tarjeta de crédito.` / `Empieza tu prueba gratis aquí`
- EN: `🚀 Try GoHighLevel FREE for 30 days` / `No credit card required.` / `Start your free trial here`
- IN: `🚀 Try GoHighLevel FREE for 30 days` / `No credit card. Razorpay UPI accepted.` / `Start your free trial here`
- AR: `🚀 جرّب GoHighLevel مجاناً لمدة 30 يوماً` / `بدون بطاقة ائتمان.` / `ابدأ تجربتك المجانية`

## 2. Pre-intro (1 paragraph, max 100 words, no heading)

Names the reader concretely (their role + situation). Names the problem in concrete terms. Promises what the SERIES (all 9 parts) explains. Does NOT mention GoHighLevel yet — that comes in the body.

Style follows `references/article-template.md` § "Pre-intro framing" rules: no "in this post we will explore", no "in today's fast paced world", no em-dash.

## 3. "What you'll learn in this series" (highlighted box)

```html
<p style="background:#f5f5f0;border-left:4px solid #111520;padding:16px;">
<strong>{learning_objectives_headline}</strong>
</p>
<ol><li>...</li><li>...</li></ol>
```

5-7 numbered objectives covering the whole series (not just Part 1). Per language:
- ES: `Al terminar esta serie entenderás:`
- EN: `By the end of this series you will understand:`
- IN: `By the end of this series you will understand (with India context):`
- AR: `بنهاية هذه السلسلة ستفهم:`

## 4. The 9 parts list (H2 + numbered list)

```html
<h2>{parts_list_heading}</h2>
<ol>
  <li><strong>Parte 1.</strong> {part_1_title} — {part_1_one_line_summary}</li>
  <li><strong>Parte 2.</strong> {part_2_title} — {part_2_summary} <em>(próximamente)</em></li>
  ... (Parts 3-9 ALL marked "próximamente")
</ol>
```

**Hard rule:** ONLY Part 1 is unmarked. Parts 2-9 ALWAYS get the "próximamente" / "coming soon" / equivalent marker until they actually ship. When a new part ships, remove that part's marker.

Per language headings:
- ES: `Las 9 partes de la serie` / `(próximamente)`
- EN: `The 9 parts of the series` / `(coming soon)`
- IN: `The 9 parts of the series` / `(coming soon)`
- AR: `الأجزاء التسعة للسلسلة` / `(قريباً)`

## 5. Related reading (existing cluster spokes)

```html
<h2>{related_reading_heading}</h2>
<p>{related_intro_paragraph}</p>
<ul>
  <li><a href="{spoke_url}">{spoke_title}</a> — {spoke_one_line_angle}</li>
  ... (every spoke from the cluster, real article URLs)
</ul>
```

Lists every existing cluster spoke with a real internal link. The intro paragraph names that the series isn't fully written yet but these existing posts cover specific angles.

## 6. Secondary CTA — Extendly (mid-hub)

```html
<p style="background:#fefbf0;border:1px solid #f59e0b;padding:16px;border-radius:4px;">
<strong>{extendly_headline}</strong> {extendly_pitch_paragraph}
<a href="{extendly_url}" target="_blank" rel="nofollow noopener">{extendly_cta} →</a>
</p>
```

Help-needed framing. Targets readers who don't want to set up GHL themselves. Per language:
- ES: `¿Prefieres implementación hecha por expertos?` / `Extendly maneja el onboarding de GoHighLevel, soporte white-label 24/7 en español, y snapshots pre-construidos para {vertical_plural}.` / `Ver Extendly`
- EN: `Prefer expert implementation?` / `Extendly handles GoHighLevel onboarding, 24/7 white-label support, and pre-built snapshots for {vertical_plural}.` / `See Extendly`

`extendly_url`: `https://extendly.com/gohighlevel/?deal=vqzoli`

## 7. "Why this series exists" (H2 + 1-2 paragraphs)

States the unique angle motivating the series. Concrete pain. Why not other CRMs. Why 9 parts. Why now.

Pulls directly from the `hub_intro_angle` parameter passed to the generator.

## 8. Primary CTA (bottom — closes the hub)

```html
<p style="background:#111520;border-left:4px solid #f59e0b;padding:16px;border-radius:4px;color:#eef2ff;text-align:center;">
<strong>{primary_close_headline}</strong><br>
{primary_close_subhead}<br>
<a href="{trial_url}" style="color:#f59e0b;font-weight:bold;" target="_blank">{primary_close_cta} →</a>
</p>
```

Same trial URL as element 1. Different framing — closes rather than opens.

Per language:
- ES: `Empieza tu prueba de 30 días de GoHighLevel` / `Sin tarjeta de crédito. Cancela cuando quieras.` / `Empezar prueba gratis`
- EN: `Start your 30-day GoHighLevel trial` / `No credit card. Cancel anytime.` / `Start free trial`

## Length and meta rules

- Total hub length: **800-1500 words**
- Meta description: **150-158 chars**, must include "GoHighLevel" and `{vertical_plural}` in first 80 chars
- Title: H1 in target language, must include `GoHighLevel` and `{vertical_plural}`

## Output JSON schema

```json
{
  "html_content": "Full HTML of the hub with all 8 elements in order",
  "meta_description": "150-158 char meta",
  "title": "H1 of the hub in target language"
}
```
