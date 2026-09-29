---
name: studio-scout
description: Proactively find fresh, post-worthy stories for SPORTS DESK, TECHDESK and BIZDESK and pitch them to the owner on Telegram ("I saw this — want it posted like this?"). Used by the scout cron job and whenever the owner asks "anything good today?".
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [instagram, studio, news, trends, scouting]
    category: studio
    requires_toolsets: [terminal]
---

# Studio scout: "I saw this — post it like this?"

## When to use
The scheduled scout run (a few times a day), or the owner asks what's trending / what we should post.

## Procedure
1. `studio status` — if the studio is PAUSED, stop and send nothing.
2. `studio list --all --days 14` — know what's already covered, booked or suggested (never pitch a duplicate).
3. For each brand, look for 0–2 genuinely strong, fresh stories:
   - SPORTS DESK: results and big moments in the last 12–24 h (cricket first, then football, hockey, kabaddi, badminton, athletics, chess, Olympic sports), India-first. Official sources: BCCI, ICC, AIFF, FIH, league/federation sites, plus major outlets (ESPNcricinfo, The Hindu, Indian Express, NDTV Sports, Reuters).
   - TECHDESK: the day's biggest tech stories (AI launches, big-tech rulings, phones/chips, Indian tech/startups, security incidents). Company blogs/newsrooms, The Verge, TechCrunch, Reuters, Mint, Economic Times Tech.
   - BIZDESK: a brand story with a fresh hook (results, price moves, launches, anniversaries, founder moves) — Indian brands first. Company releases, Mint, ET, Business Standard, Moneycontrol.
   Use your RSS feeds and web search. Only pitch a story that is ALREADY confirmed by two independent reputable outlets
   (not aggregators, blogs or AI-summary sites) or by one official source (the company, league, federation, regulator). The
   studio's research desk rejects anything less, so a single-outlet scoop is not a pitch yet — wait for confirmation.
4. Record each pitch: `studio suggest <brand> <kind> "<topic>" --angle "<hook>" --source "<best url>" --why "<why now + the two sources, one line>"` (it prints the item number; it refuses duplicates).
5. The owner keeps Telegram for their own asks (28 Sep): do NOT list the pitches in the chat. Your whole reply is ONE line:
   `💡 N new ideas for you → https://studio.example.com/dash/approve.html`
   (they decide there, or reply "yes 31" / "no 31"). If the owner asked you directly ("anything good today?"), the same one
   line, plus at most one sentence on the strongest idea.
6. Nothing strong? Reply with only `[SILENT]` (in a scheduled run that sends nothing). Never spam. Max 5 pitches per run.

## Pitfalls
- Quality over quantity: a pitch must be something the brand would be proud to post today.
- Respect the cadence — if a brand already has today's slots full (`studio status`), pitch for tomorrow or as a replacement.
- Don't auto-accept your own pitches; the owner decides (unless the owner has told you "you decide" for a brand — then `studio accept ID` and tell them).
