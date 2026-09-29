---
name: studio-week-plan
description: Build and book a week (or N-day) content plan for one or all studio brands — posts/reels/stories per day, times, topics and angles — from a request like "post about X for a week" or "plan next week". Always shows a dry run first.
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [instagram, studio, planning, calendar, campaign]
    category: studio
    requires_toolsets: [terminal]
---

# Studio week plan

## When to use
"Post about X for a week", "plan IPL week", "make next week's plan", "how many posts a day should we do?", the Sunday planning cron job.

## Procedure
1. Read the current cadence: `studio cadence` (default per brand per day: 1 reel, 1 carousel, 2 stories; BIZDESK 1 story). If the owner gave numbers ("2 reels a day"), pass them as flags.
2. Dry run first:
   - Campaign on a topic: `studio plan --brands <all|sportsdesk|techdesk|bizdesk,...> --days 7 --topic "<X>" --request "<owner's words>" --dry-run`
     (the planner researches the topic and gives every slot its own angle).
   - No topic ("plan next week"): `studio plan --brands all --days 7 --dry-run` — slots are "auto": the freshest story for that brand on that day is chosen when it is made.
   - Mixed: a campaign for one brand + auto for the others = two plan commands.
3. Send the owner a compact summary (max ~10 lines — Telegram is the owner's; the full plan is on https://studio.example.com/dash/): totals (reels/carousels/stories per brand per day, and how many carousels are animated vs still — the dry run marks each `[animated]`/`[still]`), the posting times, and the angles for campaign slots (group by day; keep it short). If the owner wants a different mix, `studio motion --share N` before booking, or `studio motion ID animated|still` after. Recommend changes if a day looks repetitive or overloaded. Ask: "Book it?"
4. On a yes: run the same command without `--dry-run`. Reply with the plan number and the first few items.
5. The owner can later remove/move single items (`studio remove`, `studio move`) or pause everything (`studio pause`).

## Guidance for good weeks
- Sports: match days carry results (carousel/story) the same evening and a reel on the day's hero moment; rest days carry previews and explainers.
- Tech: one big story per day as the reel, the week's explainer as carousels, quick launches as stories.
- BIZDESK: one strong brand story per reel; carousels for timelines and numbers; stories as teasers for the day's reel.
- Never plan the same story for a brand's reel and carousel on the same day.
- Plans are for the future only (slots less than 30 min away are skipped automatically).
