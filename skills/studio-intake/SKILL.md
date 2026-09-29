---
name: studio-intake
description: When the owner shares a link, screenshot, tweet, article or idea ("see this", "explore this", "post about this in the respective account") — explore it, choose brand(s) and format, and book it in the studio with the link as the lead source.
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [instagram, studio, intake, research]
    category: studio
    requires_toolsets: [terminal]
---

# Studio intake: "see this, post about it"

## When to use
The owner sends a URL, a forwarded message, a screenshot or a short idea and wants it explored and/or posted.

## Procedure
1. **Explore it.** Open the link (web extract / browser) or read the image. Get: what happened, when, who, the key numbers. Then run one or two web searches to confirm it from an independent reputable source and to check it's current (2025–26). If it's a rumour, satire, or older than a few days for sports/tech news, say so before booking.
2. **Decide where it belongs** (see studio-operator: sports → sportsdesk, tech → techdesk, brand/business story → bizdesk; "respective"/"across all" means every brand that has a genuine angle, each with its own angle).
3. **Decide the format**: reel for the big emotional/surprising story, carousel for numbers/timelines/explainers, story for a quick update. If the owner named a format, use it.
4. **Book it** — with the link as the source so the research desk reads it first:
   `studio add <brand> <kind> "<short topic>" --angle "<the hook/angle>" --source "<url>" --asap`
   (use `--at "YYYY-MM-DD HH:MM"` instead of `--asap` when the owner wants a time, or when a slot later today fits better; `--notes` for anything else they said).
5. **Reply** in 2–4 lines: what it is (one line), where it goes (brand + format + angle), item number(s), and "preview in ~20–40 min". If you think a different brand/format is better than what they asked, say so in one line but do what they asked.

## Pitfalls
- Screenshots: transcribe the key facts into `--notes` because the research desk can't see the image.
- Paywalled/blocked pages: don't try to get around the paywall or bot protection; use the headline + other sources.
- Never book something you couldn't confirm anywhere else — tell the owner it's unverified and ask.
- Don't duplicate: run `studio list --all --brand <b>` if it sounds familiar; if it's already booked, say which item.
