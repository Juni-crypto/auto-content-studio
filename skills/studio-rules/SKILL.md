---
name: studio-rules
description: The frozen production rules of the owner's Instagram studio (voice, scripts, editing, facts, official assets, per-brand identity). Read before judging, describing or changing any studio content, and when the owner asks "what are our rules".
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [instagram, studio, rules, brand]
    category: studio
---

# Studio rules (frozen 27 Sep 2026)

The full rule text the writers and the committee use is `/opt/studio/app/prompts/rules.md`. The owner's sources of truth:
`/opt/studio/rules/PLAN.md` ("Final production format"), `/opt/studio/rules/EDITING-RULES.md` (safe zones, sizes, spacing,
pacing, captions) and `/opt/studio/rules/memory/*.md` (content rules, official-assets rule, latest-data rule, Codex full-design rule).
Read them with `cat` when you need detail. These rules are frozen: do not change them unless the owner explicitly says so,
and then change the files, not your memory alone.

## Short version
- **Voice:** Qwen3-TTS "Aiden", creator style, one continuous take, best of several takes, ~175 wpm.
- **Script:** conversational, like telling a friend. Opens "Hey champ!/Hey buddy!/Hey boss! So today…" with the hook in the same breath; real reactions ("Hmmm, bit sad… but hey", "Haha", "But guess what? Our hero didn't…"); ends "Follow <brand> for more, and catch you later, <champ|buddy|boss>!".
- **Picture:** hook on screen at frame 0 with the greeting tag; one bonded centred column; never a blank centre; captions don't repeat on-screen words; real 3D emojis float on reactions; tap-to-Follow end card.
- **Stories differ:** a brand's reel is a different story from its carousel/story that day.
- **Facts:** latest (2025–26) data only; two independent sources or one official source per fact; history framed as history.
- **Assets:** official logos, seals, flags and press images, unaltered; REAL photos of players/people/places from open-licence collections (Wikimedia, Flickr CC), credited in the caption; never agency/wire/news-site photos or broadcast footage; no AI-drawn real people unless the owner switches it on (`studio draw-people`), then only the real event, never called a photo, captioned 'Illustration: AI-generated.'; generic things get generated object images.
- **Designs:** carousel slides and cards are complete Codex designs (no text overlaid by code).
- **Captions:** hook first, a question at the end, "<Brand> is a trademark of <Company>. Not affiliated." for real brands shown, "AI voice · real facts." on voiced posts.
- **English only** (SPORTS DESK strictly; BIZDESK may use everyday Hindi words).

## Brand cards
- SPORTS DESK — ink black, hot magenta #E6007E, marigold #FFB300, cream; poster energy; kicker "First. Every time."; hyped sports-mad voice.
- TECHDESK — near-black, hazard orange #FF5B1F, off-white italic condensed headlines; "PATCH MMDD" tape; playful cheeky tech voice.
- BIZDESK — sunflower yellow, parrot green, signal red, royal blue; hand-painted signboard/truck-art type; "BRAND KAHANI"; warm witty storyteller.
