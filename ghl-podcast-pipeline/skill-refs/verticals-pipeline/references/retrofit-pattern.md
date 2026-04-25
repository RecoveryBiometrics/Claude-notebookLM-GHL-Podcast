# Retrofit pattern (de-siloing inbound links)

When a new hub ships at `/{lang}/para/[vertical]/`, every existing cluster spoke must inject a contextual inbound link to the hub BEFORE Cloudflare crawls the new URL. This prevents the hub from being orphan-indexed.

## The injection paragraph (HTML template)

```html
<p style="background:#f8f6f0;border-left:3px solid #111520;padding:12px 16px;margin:24px 0;border-radius:4px;">
📚 <strong>{series_label}:</strong> {context_sentence}
Si quieres la <a href="{hub_url}" style="color:#111520;font-weight:600;">{anchor_text}</a>, 
{closing_sentence}.
</p>
```

Variables:
- `{series_label}` — `Serie completa` (ES) | `Full series` (EN) | etc.
- `{context_sentence}` — `Este post es parte del panorama general.` (ES) — frames why the link matters
- `{hub_url}` — full hub URL (e.g. `/es/para/agencias-de-marketing/`)
- `{anchor_text}` — varies, see below
- `{closing_sentence}` — `empezamos con por qué las agencias necesitan un CRM y terminamos con los errores más comunes en el setup` (ES Part 1 example)

## Anchor text variation rules

**Don't use the same anchor text on every spoke.** Same anchor 10× → looks like a link farm to Google. Vary by spoke role/angle:

| Spoke angle | Anchor text (ES) | Anchor text (EN) |
|---|---|---|
| `core-pillar` | `la guía completa de GoHighLevel para agencias de marketing` | `the complete GoHighLevel guide for marketing agencies` |
| `platform-intro` | `el panorama de la serie completa sobre GoHighLevel para agencias` | `the full series on GoHighLevel for agencies` |
| `whatsapp-flow` | `la serie de 9 partes sobre cómo escalar tu agencia con GoHighLevel` | `the 9-part series on scaling your agency with GoHighLevel` |
| `pricing` | `la guía paso a paso de GoHighLevel para agencias` | `the step-by-step GoHighLevel guide for agencies` |
| `setup` | `cómo construir un sistema completo en GoHighLevel para agencias` | `how to build a complete system in GoHighLevel for agencies` |
| `errors` | `los errores comunes que las agencias evitan con esta guía` | `common mistakes agencies avoid with this guide` |
| `comparison` | `el manual definitivo de GoHighLevel para agencias` | `the definitive GoHighLevel manual for agencies` |
| `case` | `nuestra serie completa sobre GoHighLevel para agencias` | `our full series on GoHighLevel for agencies` |

If the spoke's `angle` field doesn't match a row above, default to the `core-pillar` anchor text but ONLY if no other spoke is using it.

## Injection point (where in the article)

Inject **after the first H2 closing tag**. This places the link in the article body where contextual relevance is highest. NOT at top (looks like a banner ad) and NOT at bottom (most readers don't reach it).

## Idempotency

If the spoke's HTML already contains a link to `{hub_url}`, SKIP that spoke. Don't add a second.

## Failure modes

- Spoke file doesn't exist → log warning, skip
- No H2 in spoke article → inject after first paragraph instead
- All anchor variations exhausted (more spokes than rows above) → reuse `core-pillar` anchor with a note in the log

## Why this matters

A new hub URL with zero inbound links from the same site = treated as orphan content by Google. Cloudflare crawls, indexes thinly, won't rank. Retrofit before deploy means the hub launches WITH internal authority signals already in place.

Per `seo-deploy-gate` rule (planned #9): every new hub URL must have ≥3 inbound internal links from existing published pages BEFORE deploy. Current implementation: this retrofit is the one-time enforcement for Part 1. When Part 2 ships, this should become a gate rule that blocks deploy if not satisfied.
