# Editing rules for kinetic reels (1080×1920)

Written 27 Sep 2026 for `kreel.py` (the HyperFrames kinetic news reels). It has three parts:

1. **Rulebook:** numbered rules with numbers for a 1080×1920 frame, each tied to its sources.
2. **Critique** of the four current reels (sportsdesk, techdesk, push, breakpoint). Frame times are cited, and the numbers were measured from the 1 fps frames.
3. **Change list** for `kreel.py`: which constants and behaviours to change, and to what values.

Sources, with URLs and dates, are at the end. `[S#]` points to that list and `[L#]` to the local skills.

## The short version (why the edits feel off)

- **Pacing is fine. Layout is the problem.** Something new lands every 1.0-1.3 s in all four reels.
- **The two blocks are far apart.** The headline block is only 295-528 px tall (15-27% of the frame, median) and floats around y 700-800. The caption is pinned alone at y 1410. Between them sits an empty band of 333-489 px (median), and up to 768 px. The eye sees two small islands with a hole between them. Most of the time the islands also say the same words.
- **Six causes, one fix each:**
  1. Stacks reveal top-down inside a block that is pre-centred for its final height, so line 1 floats high and alone. **Fix:** re-centre the block each time a line lands (Change C).
  2. Size comes from width only, so wide fonts shrink to 80-117 px cap height. **Fix:** wrap to 2 lines instead of shrinking (Change D).
  3. Logos and tags sit in a "top zone" 160-310 px away from their text. **Fix:** bond them into one column (Change B).
  4. Captions sit too low and far from the content. **Fix:** move them up to y 1260 and stop printing the headline words twice (Change F).
  5. Brand chrome sits under Instagram's top overlay. **Fix:** move it (Change A).
  6. Hook frames are blank or blurred at 0-0.5 s. **Fix:** land the first headline at frame 0 (Change G).

---

## Part 1: Rulebook (1080×1920)

### Rule 1. Instagram safe zones

| Area | Organic Reel (what we post) | Boosted Reel or ad | Sources |
|---|---|---|---|
| Top overlay: "Reels" header and camera icon | Measured at 108-220 px. **Use: no text above y 240** | 14% = **269 px** | Meta Ads Guide [S1]; Minta 108, Outfy 108, CampaignSwift 200, Ignite 220, Blitzcut 220 [S5-S11] |
| Bottom overlay: username, caption, audio (plus CTA on ads) | Measured at 310-480 px. **Use: no text below y 1440** (bottom 480 px) | 35% = **672 px** (nothing below y 1248) | [S1]; Minta 320, TryMyPost 420, Ignite 420, Blitzcut 480, Poster.ly 25% [S5-S12]; Hootsuite "bottom fifth" [S13] |
| Right action rail: like, comment, share, save, audio | 100-140 px wide. **Use: keep text at x ≤ 940 wherever it runs below y 1100** | same | TryMyPost 100, Minta, Outfy and Blitzcut 120, Poster.ly 140 [S5-S12]. No source gives the rail's vertical start; y 1100 is our conservative inference |
| Sides | **≥ 65 px** | 6% = 65 px | [S1]; Minta and Kreatli 60 [S5, S7]; EBU R95 graphics-safe 5% = 54 px [S20] |
| Profile grid thumbnail (3:4, since Jan 2025) | Shows **y 240-1680** only | same | Mosseri via The Verge, 17 Jan 2025; Buffer, 17 Mar 2026; Kapwing, 30 Dec 2025 [S14-S16] |
| Feed preview (4:5 centre crop) | Shows **y 285-1635** | same | TryMyPost, 24 Jan 2026 [S8] |
| Cross-post to TikTok | top 130, **bottom 484**, right 140 | TikTok Ads: same | Cadenus citing TikTok Ads help, 28 Jul 2026 [S17] |
| Cover frame | **Frame 0 is the default cover** (`thumb_offset` defaults to 0) | same | Meta for Developers, IG User Media reference [S2] |

Meta publishes safe zones only for ads (14/35/6%). The organic numbers come from third-party measurements of the live UI, and they vary by source.

**Our working box:**
- Key text: x 65-1015 and y 240-1440.
- Anything whose box runs below y 1100 stays at x ≤ 940.
- Hook, logos and CTA stay inside y 290-1200, which survives every crop and overlay above.
- Boost profile, if a reel will be boosted: move all key text and captions above y 1248 (see Change A).

### Rule 2. The layout grid we use

```
y    0 ┌──────────────────────────────┐
       │  IG top overlay (no text)    │
y  240 ├──────────────────────────────┤
       │  chrome row: brand bug + kicker   (y 244-320, bug ≤ 76 px tall)
y  350 ├──────────────────────────────┤
       │                              │
       │  CONTENT ZONE (870 px)       │  one bonded block, centred on y 785
       │  x 70-1010                   │  (x ≤ 940 below y 1100)
       │                              │
y 1220 ├──────────────────────────────┤  40 px
y 1260 │  CAPTION RAIL (≤ 2 lines)    │  x 90-910, centred on x 500
y 1420 ├──────────────────────────────┤
       │  IG bottom overlay:          │  background only (crowd plate,
       │  background only             │  ghost cards, tapes are fine)
y 1920 └──────────────────────────────┘
```

- **2.1.** One content block per beat, centred on **y 785** (≈0.41 H). HyperFrames puts the centred hero at 0.42 H ≈ 806 [L1, L6].
- **2.2.** The block's top and bottom breathing room must be equal within ±80 px. With block heights of 480-700 px, the gap to the caption rail is 85-255 px.
- **2.3.** Stack vertically in portrait. Do not place items side by side, except a number with its unit [L6].

### Rule 3. Text sizes (font-size in px at 1080 wide)

| Element | Size | Floor | Sources |
|---|---|---|---|
| Hero word or number alone on screen | 200-380 condensed (Anton, Barlow Condensed); 150-300 wide sans (Inter, M PLUS). Cap height ≥ 140 px. Width 60-90% of the frame (650-970 px) | 150 | Hero tier 150-240 px [G: audrey-560 cinematic-caption]; 9:16 titles 88-168 px [G: bang-motion]; climax 0.16-0.22 H [L5]; hero text 60-80% of width [L3] |
| Headline or stack line | 110-330 | **90** | Headline ≥ 84 [G: remotion-dev video-layout]; ≥ 90 in-feed [L4]; 72-96 min [S23] |
| Secondary line under a hero | 0.35-0.5 × hero | 64 | Hero-to-title ratio about 2.5:1 [G: Barty-Bart examples]; level jump ≥ 1.8-3× [L5, L6] |
| Label, gloss, mono or source line | 44-60, at most 2 lines, ≤ 30 characters per line | **44** | Body ≥ 44 [G: bang-motion; remotion-dev]; body 40-60 [S25] |
| Caption | 64-76 bold | 56 | Consensus 56-80, typical 60-72 [G: iart-ai, remotion template-tiktok, media-use]; 60-75 standard [S21] |
| Credits or legal (end card only) | 30-36 | 30 | "Nothing under 30 px" [G: bang-motion] |

- **3.1.** Never shrink a line below its floor to fit one line. **Wrap it into 2 balanced lines instead.** Measured with our fonts, wrapping takes "WHAT CHANGED?" from 99 to 158 px, "THAT NUMBER" from 122 to 205, "NEW SUBSCRIBERS" from 98 to 135, and "2 APPS: $24.98" from 116 to 230.
- **3.2.** Hero lines hold ≤ 16 characters. Labels hold ≤ 30 characters per line.
- **3.3.** Display tracking −0.02 to −0.04 em. Stack line-height 0.9-1.0 [L4; G: iart-ai kinetic-typography].
- **3.4.** "3 s on screen must be readable in 2" [L4]. A phone viewer should read it in under a second and be able to read it twice [S26].

### Rule 4. Margins and spacing

- **4.1.** Side margins: hero text ≥ 70 px; labels and body ≥ 90 px. Captions ≥ 90 px on the left and ≥ 170 px on the right, because of the rail. Nothing touches the frame edge, including during entry animations. Sources: Meta 65 px [S1]; ≥ 60 px [S7, S24]; title-safe 10% for captions [L2].
- **4.2.** Lines inside one stack: gap 0.08-0.12 × font (≈16-36 px). Builder contract gap 24 [L7]; support-to-hero 0.15-0.45 × support size [G: audrey-560].
- **4.3.** Bonded pairs sit **32-56 px** apart: logo and headline, number and label, tag and figure, photo and line. Composition-craft calls a 144 px setup-to-climax gap "disconnected" [L5].
- **4.4.** Two groups in one frame: 80-120 px apart. **Never more than 120 px of gap inside one beat.**
- **4.5.** Content block to caption rail: 40-260 px.
- **4.6.** No two boxes closer than 24 px unless they overlap on purpose (tape, stickers). Measure the painted box, including rotation, shadow and pop overshoot.

### Rule 5. Filling the frame: negative space versus dead space

- **5.1.** While a beat is on screen, the content block is **≥ 440 px tall** (≥ 50% of the 870 px zone). Target 480-700 px (55-80%). Sources: kinetic-type block 50-75% of height × 60-80% of width, primary visual ≥ 40% of the canvas [L6]; "fill the whole top-83% region… don't float one small cluster mid-frame" [L1].
- **5.2.** **Largest empty horizontal band** inside y 350-1420: target ≤ 300 px, hard limit **≤ 360 px (19% of H)**. It may last ≤ 0.5 s, and only during a cut.
- **5.3.** A single element alone on screen for > 0.6 s must be hero-sized: cap height ≥ 140 px, or a logo or photo ≥ 560 px wide. "Never a single text block floating in empty space" [L3]. "Text overlays… should span the full width of the frame, not float in small blocks" [S23].
- **5.4.** Negative space is space around one big hero: side margins, plus breathing room above and below of ≤ 250 px each, balanced. Dead space is a void between two things that belong together (headline and caption, logo and its name). Keep the first; remove the second.
- **5.5.** Background layers (crowd plate, ghost cards, code lines, tapes) do not count as content. They are what makes a frame read as intentionally filled, so keep them at 12-25% opacity [L3].
- **5.6.** Poster test: freeze any second and it should work as a designed still [L6, L8].

### Rule 6. Pacing and change frequency (30-40 s reel)

- **6.1.** **Frame 0 shows the hook headline already landed.** Frame 0 is the default cover [S2]. The hero must be visible by 0.5 s [L1]. Hook text should be on screen "by frame 1, no fade-up" [G: iart-ai]. Instagram's skip rate measures the first 3 s [S28].
- **6.2.** Something new every **0.8-2.0 s**: a line lands, a number rolls, an image enters. No static stretch over **2.2 s**; 2.5 s is a fail. Sources:
  - Gap > 2.2 s with no visual event fails [G: nateherkai student-kit].
  - A change every 1-4 s at uneven intervals, never more than about 3 s with nothing [G: consensus].
  - One change per spoken beat, about 0.4-1.2 s apart [G: Barty-Bart].
  - Interrupts every ~4 s: 58% vs 41% retention [S27].
- **6.3.** A new layout, meaning a clear and cut, every **3-6 s** (one per beat). No layout on screen longer than 6 s. "Cut every 2-4 s; no scene > 5 s" [G: DojoCodingLabs].
- **6.4.** Each landed element holds **≥ 0.5 s** before anything changes on top of it. The payoff or key number holds **1.0-1.5 s** [G: student-kit, claude-remotion].
- **6.5.** Loud accents (camera shake, flash, tape slap) come at most **once per 5 s**, so 6-8 per reel. Sources: one "jaw-dropper" per 5 s [G: student-kit]; shake or flash 1-3 per 30 s [G: reelforge]; "one kinetic moment per section" [S29].
- **6.6.** Break the rhythm once per ~30 s: a full-bleed image, a 2× word, or a silent beat [L8].
- **6.7.** Arc for 30-40 s:
  - hook 0-3 s
  - setup to ~10 s
  - 3-4 body beats
  - payoff at ~25-32 s
  - CTA in the last 3-5 s

  Sources: [G: boring-marketing, claude-remotion]; completion was highest at 21-34 s [S27].

### Rule 7. Captions

- **7.1.** **Position: top y 1260, bottom ≤ 1420 (2 lines), centred on x 500, max width 820.** Sources:
  - portrait rail "~600-700 px from the bottom" = y 1220-1320 [L5]
  - baseline 62-70% of height [G: iart-ai]
  - ~65% [G: claude-remotion]
  - y 1200-1550 [S21]
  - ≤ 1410 [S30]
  - organic bottom overlay from ~1440 [Rule 1]
- **7.2.** 1-3 words per chunk; one line preferred, ≤ 2 lines, ≤ 18 characters per line. Each chunk shows ≥ 0.4 s and ≤ 2.5 s. Sources: karaoke 1-3 words on a single line [S21]; words ≥ 0.4 s [L8]; page ≥ 0.3-0.5 s [G: remotion-captions-kit].
- **7.3.** 64-76 px bold, with an active-word highlight. A pop may go to ≤ 1.1× [L5; G: iart-ai].
- **7.4.** Legibility on busy backgrounds comes from text stroke and shadow, or from darkening the background band behind the rail. Do not use a card or box (see the owner's no-boxes rule in reel-motion-style). Source: stroke 2-6 px + shadow 0 4px 16px rgba(0,0,0,.55) [G: iart-ai].
- **7.5.** **Do not double-print.** When ≥ 60% of a chunk's words are already on screen as kinetic type, hide that chunk. Sources:
  - on-screen text is short motion-graphics copy, never the narration sentence, because the captions already show the words and "repeating them double-prints on screen" [L1]
  - "caption what adds, cut what restates" [L8]
  - Mayer's redundancy and coherence principles [S31]
- **7.6.** Captions have one home zone and never move between zones [L5].

### Rule 8. Elements on screen and hierarchy

- **8.1.** One focal point per frame. Squint test: blur the frame and the most important element should still be obvious [L6; S32].
- **8.2.** At most **3 content elements** per frame: 1 hero and ≤ 2 supporting. The caption and brand bug come on top of that. At most **2 text levels**, hero plus label [G: bang-motion]. At most 4 lines per stack and ≤ 7 words of kinetic text on screen [G: motion-graphics kinetic-type 3-7 words per scene].
- **8.3.** The hero is **≥ 2×** the next text level [L5, L6].
- **8.4.** Logos are **≥ 440 px wide when bonded** to text and **≥ 560 px when alone** (40-55% of the width). Product photos are 760-900 px wide. Official assets are used unaltered, per the brand-assets rule.
- **8.5.** Consecutive beats change layout: type-led, then image-led, then number-led. Use at least 3 framings per reel, never the same one twice in a row [L6].

### Rule 9. Motion

- **9.1.** Entrances take 0.25-0.5 s with power3 or expo ease-out. Exits take 60-70% of the entrance time with ease-in [L3; G: consensus].
- **9.2.** An entering element never goes outside the frame. The slam start scale is ≤ `1 + 260 / element width`.
- **9.3.** Re-layout moves (the block re-centring) take 0.25-0.3 s power3.out. Line stagger is 60-100 ms and word stagger 40-80 ms [G: iart-ai kinetic-typography].
- **9.4.** Transition flashes stay at ≤ 0.3 opacity and peak at the cut, not after the new text lands.
- **9.5.** In a swap, the old element leaves before the new one lands in the same slot (0.15 s ahead). Two counters or two cards never overlap.

### Rule 10. QA before publishing

- Run the build checks (Change H).
- Make the 1 fps contact sheet with a safe-zone overlay: lines at y 240, 1260, 1440 and x 940.
- Run the five positive checks [L8]: poster test, timid test, one-glance hierarchy, scene handshake, dead-air audit.

---

## Part 2: Critique of the current reels

### How this was measured

- Each 1 s frame from `ev-<name>/` (1080×1920) was thresholded for "ink": bright or saturated foreground. Theme backgrounds, background tapes, ghost cards and the crowd plate were excluded.
- Each frame was then scanned row by row. The content block is everything between y 260 and 1370, with chrome and captions excluded.
- End cards are left out of the stats.
- Scripts: `scratchpad/edit-audit/measure.py` and `holds.py`.

| Reel | Content block height (median) | Block top / bottom (median) | Void, block to caption (median / worst) | Frames with block < 300 px | Longest static hold | Camera shakes |
|---|---|---|---|---|---|---|
| sportsdesk (39.9 s) | 528 px (27% of frame) | 481 / 994 | 422 / 711 px | 10 of 36 | 7.5-9.5 s | **25** (one per 1.6 s) |
| techdesk (30.2 s) | 415 px (22%) | 477 / 1024 | 333 / 590 px | 5 of 27 | 16.5-18.5 s | **16** (one per 1.9 s) |
| push (34.5 s) | 511 px (27%) | 545 / 965 | 454 / 768 px | 10 of 31 (+ 0.5 s blank) | 8.5-11.5 s | 3 |
| breakpoint (34.9 s) | **295 px (15%)** | 605 / 909 | 489 / 728 px | **16 of 31** | 22.5-24.5 s | 5 |

- Captions sit at y 1408-1475 in every reel, and at 1412-1548 when a chunk wraps to 2 lines. Two-line captions therefore reach into the organic bottom overlay (from ~1440-1500).
- The content zone changes visibly in 24-32 of the ~30-38 sampled seconds, so the rate of change is not the problem.

### Problems common to all four

1. **Two islands with a dead band between them.** MID=800 centres the visual while the caption is fixed at 1400. That leaves a median void of about 400 px on every beat, well past Rule 5.2 (360 px). The best frames prove the fix, because their content reaches down to the caption:
   - sportsdesk 25.5 s: stack 421-1184, crowd below.
   - techdesk 11.5-12.5 s: photo 406-1323, caption 94 px below.
   - push 18.5 s: TV screenshot 550-1271.
2. **Stacks are top-heavy while they build** (Rule 5.3). `c_stack` centres the final block but reveals it from the top. For 0.5-1.5 s of every stack, line 1 sits alone at y 430-600 with 600-770 px of nothing below it.
3. **Width-only sizing makes wide fonts small** (Rule 3.1). `fit()` forces one line into 920-980 px, or 800 px on breakpoint. Anton survives this. Inter 800 and M PLUS drop to 80-117 px cap height: breakpoint "A GENERATION", "WHAT CHANGED?", "NOT FIRST."; push "NEW SUBSCRIBERS", "EVERYONE ELSE". That is subtitle size, not hero size.
4. **Labels shrink until they cannot be read** (Rule 3, floor 44). Label and mono lines are fitted to one line and end up at about 22-30 px, which is roughly 8-10 pt on a phone.
   - techdesk: 18.5 s "Taction makes haptics for headsets"; 25.5-26.5 s the Apple quote.
   - breakpoint: 10.5 s "the gate wraps the channel on every side"; 14.5-17.5 s "faster than 3nm"; 21.5 s "Qualcomm's claim…"; 31.5 s.
5. **Related pieces sit in different zones** (Rule 4.3). A logo or tag goes to the "top" zone (y 300) and its words to the "mid" zone (y ~700-800):
   - techdesk 19.5-21.5 s: "PER REUTERS" at 273-405, the figure at 717-890 (312 px apart).
   - breakpoint 29.5-31.5 s: the Mi logo at 300-592, "XIAOMI 18 PRO" at 756-836 (164 px apart).
   - push 6.5-11.5 s: the Disney+ card at 300-562, the price at 643-956.
6. **The hook frame is not readable** (Rule 6.1). At 0.5 s every first element is still entering. At 0.0 s (the default cover) only the chrome shows, because beat 1 starts at t = 0.4.
   - sportsdesk "INDIA" is blurred.
   - techdesk "APPLE OWES" is blurred and clipped at the left edge.
   - push "DISNEY+" is at low opacity, so the frame measures as empty.
   - breakpoint shows only a chip wiping in.
7. **Brand chrome sits under Instagram's top overlay** (Rule 1). The kicker is at y 120-175 and the tile at y 96-236 (x 794-1024). Both are inside the 108-220 px band that the "Reels" header and camera icon cover.
8. **The caption repeats the headline** (Rule 7.5). At most caption moments the headline and caption show the same words, about 400 px apart. That is clutter and dead space at the same time. Examples: sportsdesk 2.5, 3.5, 5.5, 13.5, 24.5 and 36.5 s; techdesk 1.5 s "APPLE OWES $5.7"; push 1.5 s "Disney+ and Hulu"; breakpoint 3.5 s "That number doesn't".
9. **Entries overflow and collide** (Rules 4.6, 9.2, 9.5):
   - The 1.6× slam start overflows both edges: sportsdesk 15.5 s "3 OCTOBER" spans x 0-1080; techdesk 0.5 s.
   - sportsdesk 6.5 s: the AIFF crest overlaps the "00'" counter.
   - sportsdesk 10.5 s: two counters are live at once and show half-digits ("37'", "6").
   - push 13.5-15.5 s: the hulu card touches the price pill, then the TV screenshot slides over the old pill.
   - techdesk 13.5 s: the transition tape crosses the watch photo.
   - sportsdesk 15.5 s and 22.5 s: the stadium flash (0.55 opacity, peaking 0.12 s after the cut) washes out the new headline.
10. **Too many loud accents** (Rule 6.5). Every slam and every non-push stack line pushes a camera shake: 25 in sportsdesk and 16 in techdesk, one every 1.6-1.9 s. When everything shakes, nothing is emphasised.
11. **Side margins are too tight** (Rule 4.1). push 21.5 s and 29.5 s ("+50¢", "SAVE $11.99/MO") run to x 30-1049. sportsdesk 25.5 s "IN THE SQUAD" reaches x 1019 at y 1100-1184, which is the right-rail band.

### sportsdesk (sports, 39.9 s)

- **0.5 s:** "INDIA" is blurred mid-slam, so the hook is not readable.
- **3.5, 12.5, 20.5, 26.5 s:** line 1 of a stack floats alone. For example, 12.5 s "PANAMA" sits at 435-701 with a 708 px void to the caption.
- **33.5-34.5 s:** "INDIA ?" sits alone for 2 s (412-698, 710 px void). This is the CTA and should carry the most weight, not the least.
- **6.5 s:** the crest overlaps the counter.
- **7.5-9.5 s:** crest, "41'" and a 49 px "RYAN WILLIAMS" label hold static for 3 s.
- **10.5 s:** the counter swap shows as a glitch.
- **15.5 s:** "3 OCTOBER" overflows both edges under a white flash. **22.5 s:** "VINI JR" is also washed out by the flash.
- **25.5 s:** this is the **reference frame**. The 3-line stack fills 421-1184 between chrome and crowd.
- **28.5 s:** the Uruguay flag (535 px) is alone. That is acceptable for 1 s, but it should be at least 560 px.
- **29.5-32.5 s:** "FORLÁN" holds for 4 s with one line added at 31.5 s. Needs a mid-hold event (Rule 6.2).
- **Throughout:** captions sit on the busy halftone crowd (1409-1474) with only a shadow. Darken the plate band behind the rail (Rule 7.4).
- 25 shakes in 40 s.

### techdesk (tech, 30.2 s)

- **0.5 s:** "APPLE OWES" is blurred and clipped at the left edge, and the caption is dim.
- **4.5 s** "FRIDAY" (590 px void) and **7.5-8.5 s** "TAPTIC ENGINE" (135 px tall, 549 px void) are lone lines.
- **9.5 s:** the "2 PATENTS", underline and patent-number group is well bonded, but sits only at 711-1056.
- **10.5-13.5 s:** **best stretch in the set.** The product photo fills 406-1323, "TAPS · BUZZES" sits under it, and the caption is 94 px below. Only flaw: at 13.5 s the transition tape crosses the watch.
- **16.5-18.5 s:** the Taction photo holds static for 3 s, and the label that arrives at 18.5 s is about 26 px.
- **19.5-21.5 s:** the source tag and the figure are 312 px apart, which breaks the link between the source and the number.
- **24.5-26.5 s:** the Apple logo tile (350 px) is paired with a quote at about 26 px, which cannot be read. "APPEAL." at 26.5 s is good.
- 16 shakes in 30 s.

### push (tech, 34.5 s)

- **0.5 s:** effectively blank. The weakest opening of the four.
- **Lone lines 80-150 px tall, voids of 543-768 px:** 3.5 s "THE BUNDLE", 12.5 s "WITH ADS", 20.5 s "BOTH APPS" (768 px, the worst in the set), 23.5 s, 25.5 s. At 27.5-28.5 s "2 APPS: $24.98" sits alone for 2 s.
- **6.5-11.5 s:** the Disney+ card uses only 39% of the width, sits in the top zone away from the price, and the group is near-static for 5 s.
- **13.5-15.5 s:** the price pill is caught mid-roll with digits cut, the hulu card touches the pill, and the TV screenshot slides over the old pill.
- **16.5-19.5 s:** the TV screenshot is a good size but holds for 4 s, with one line added at 18.5 s.
- **21.5 s and 29.5 s:** stack lines run to x 30-1049, with no side margin.
- **31.5 s:** the end card is mid-pop on a near-empty frame.
- **Background:** the ghost-card background is good texture, but at 0.5 s and 12.5 s it is the only thing on screen besides one line.

### breakpoint (tech, 34.9 s)

- The median block is **295 px, only 15% of the frame**, making this the emptiest reel. Inter 800 inside `room=800` never gets big.
- **Lone lines** float with voids of 690-728 px: 3.5 s "THAT NUMBER" (79 px tall), 6.5 s "A GENERATION", 8.5-9.5 s "WHAT CHANGED?", and 22.5-24.5 s "NOT FIRST." (alone for 3 s, the longest lone hold in the set).
- **10.5 s:** "GATE-ALL-AROUND" carries a 22-26 px mono gloss.
- **14.5-17.5 s and 20.5-21.5 s:** the counters (+15%, 5 GHz, about 310 px) are good, but their labels are 26-30 px.
- **18.5-19.5 s:** the chip render fills 549-1022. Good.
- **26.5-27.5 s:** the 4-line list (587-1025) is the right idea, but the lines are 60-100 px. Make it 110+.
- **29.5-31.5 s:** the Mi logo is about 270 px, and a 164 px void separates it from its name.
- **Gutter and minimap:** they are good texture, but `room=800` costs 100 px of type width the headlines need.

---

## Part 3: Change list for kreel.py

Ordered by visual impact. Line numbers refer to the current 582-line file. Research only: **kreel.py was not edited.**

### A. Grid constants and chrome (lines 17-19, CSS in `css()` lines 414-416, 465-466)

| Constant / CSS | Now | Change to | Rule |
|---|---|---|---|
| `TOP` | 290 | **350** | 2 |
| `BOTTOM` | 1340 | **1220** | 2 |
| `MID` | 800 | **785** (centre of 350-1220) | 2.1 |
| new `CAP_Y` (was hard-coded in `.cap{top:1400px}`) | 1400 | **1260** | 7.1 |
| `.cap` | `left:0; right:0` | **`left:60px; right:140px`** (centres the rail on x 500) | 1, 7.1 |
| `.capin max-width` | 960 | **820** | 7.1 |
| `SAFE` | 920 | **900** (x 90-990) | 4.1 |
| `WIDE` | 980 | **940** (x 70-1010) | 4.1 |
| breakpoint `room` (lines 191, 301) | 800 | **900** (the gutter dot ends at x 108) | 3 |
| `.tile` | `top:96px; right:56px; width:230px` | **`top:244px; right:70px; height:76px; width:auto`** | 1 |
| `.kicker` | `top:120px; left:64px; 34px` | **`top:262px; left:70px; 32px`**, or drop the kicker on tech reels | 1 |
| end card: `.endtile` `top:470`, tagline y 1000, "Follow" y 1160, note y 1250 | as listed | treat as one group centred on y 785: tile width 600, gap 40 to the tagline (110 px) and 32 to "Follow" (56 px). Legal note (30 px) at y ≤ 1400 | 5 |
| Boost profile (new flag) | none | chrome row y 272-330; `TOP 350, BOTTOM 1040, MID 695, CAP_Y 1080` (captions 1080-1240), so nothing sits above y 269 or below y 1248 | 1 |

### B. One bonded block per beat, re-laid out on every change (the core fix)

Replace the three fixed zones (`TOP+10`, `MID - size*0.55`, and `low_y()`, which is `mid_bottom+36` or 1150) with a single column:

1. Keep `self.block = [(id, height, gap_before)]` for everything live in the content zone. Chrome and captions are excluded.
2. `reflow(t)`:
   - total = Σ heights + Σ gaps.
   - `y0 = MID - total/2`, clamped to `TOP .. BOTTOM - total`.
   - For each element already on screen whose y changes, emit `tl.to("#id", {y: Δ, duration: 0.28, ease: "power3.out"}, t)`.
   - New elements enter straight into their final slot.
3. Gaps:
   - **0.1 × the smaller font, minimum 16 px**, between lines of one stack. This replaces the fixed 14 px.
   - **40 px** for bonded pairs: logo→headline, number→label, tag→figure, image→line.
   - **96 px** between groups.
4. Effect on the "PER REUTERS" tag (techdesk 19.5), the Mi logo (breakpoint 29.5) and the Disney+ card (push 6.5): they stack directly on their text, and the pair is centred on y 785.
5. `below_top()` (lines 112-114), `low_y()` (121-122), `mid_bottom` and `top_bottom` go away. `zone="top"` survives only as an ordering hint meaning "first in the column". `zone="low"` means "last".

### C. Stacks: line 1 never floats alone (`c_stack`, lines 299-325)

1. Call `reflow()` on every new line, so the growing block stays centred on y 785. Line 1 lands at the centre; later lines push earlier ones up.
2. **Lone-line floor:** while a stack line is the only content, render it at `max(size, 200)`. When line 2 arrives, scale it down to its slot size (0.25 s power3.out). This is the "big → small scale-down" move from kinetic-type-beats [L9].
3. Keep the per-line `max` at 330. Add a **floor of 110**, and wrap a line that would fall below it (see D).
4. At most 4 lines and 16 characters per line. Target block height 480-700 px.
5. CTA stacks (sportsdesk "INDIA ? / BRAZIL ? / DROP IT BELOW") land all at once at hero size, rather than dripping in over 3 s.

### D. Sizing: floors and wrap instead of shrink (`fit`, lines 69-72; `text`, lines 166-170; `c_line`, lines 207-214)

- Give `fit()` a `min_size` argument. When the text still overflows `room` at `min_size`, split at the word boundary that best balances the two halves.
  - Render it as a two-line `.word`: `white-space:normal; width:room; line-height:0.92`.
  - Return the combined height of both lines so `reflow` can use it.
- Floors (font px):
  - hero or slam: **150**, and **200** when alone
  - stack line: **110**
  - any head line: **90**
  - label or mono: **44**
  - caption: **56**
- `c_line` label default goes from 70 to **56**, floor 44, at most 2 lines, `max-width 900`. This fixes techdesk 18.5 and 25.5 and breakpoint 10.5, 14.5, 21.5 and 31.5.
- `c_count` size 380 stays. Its label follows the label floor. Bond the label 40 px under the number.

### E. Images and logos (`c_image`, lines 246-268)

- Drop the `maxh 320` rule for `zone=="top"`. Everything flows through `reflow`. `maxh` is **700** alone and **560** when bonded to text.
- The logo default `w` goes from 520 to **600** when alone and **440** when bonded. Today the AIFF crest, the Disney+ card and the Mi tile are 250-420 px wide.
- Add 30 px to `box_h` for collision checks, to cover the ±2-3° rotation, the `back.out(1.7)` overshoot and the shadow.

### F. Captions (`captions()`, lines 375-397; `.cap`, `.capin` and `.sw` CSS, lines 465-469)

1. Move `top` from 1400 to **CAP_Y = 1260**, with at most 2 lines, `max-width 820`, centred on x 500 (see A).
2. Keep font 66 (76 for sportsdesk). Keep line-height 1.12.
3. **Dedupe:**
   - Skip a chunk when ≥ 60% of its words (case-folded, punctuation stripped) are in a live slam or stack at `s0`.
   - Put it behind `spec.get("caption_dedupe", True)`.
   - Captions still carry every connective phrase and every beat whose hero is an image, logo or count.
4. sportsdesk only: darken the crowd plate behind the rail. Extend `.plate:after` with a dark stop around 1200-1440 (about `#111c`). Add `paint-order: stroke; -webkit-text-stroke: 6px #000` to `.capin` so there is no box.
5. Merge chunks shorter than **0.4 s** (the current merge threshold is 0.3 s, line 385).

### G. Hook and motion (`__init__` line 49, `slam_in` 152-156, `transition` 147-150, shakes line 561)

1. **Hook at frame 0.** Beat 1 start goes from `t = 0.4` to **0.0**.
   - This shifts the whole timeline 0.4 s earlier, and the VO starts at 0.0 too.
   - Pre-land the first cue: `tl.set` it to its final state at 0, then a 0.15 s scale pulse at 0.05. The headline is already on screen when the voice says it.
   - Do the same for the chrome: tile and kicker visible at frame 0 (the tile's `scale:0` pop at 0.1 s goes).
2. **No overflow on entry.** In `slam_in`, set `scale = min(c.get("scale", 1.6), 1 + 260/width)`. A 900 px word then starts at 1.29×.
3. **Shakes only on hero moments.** Push a shake only for `c_slam` in the mid zone and for stack line 1. Enforce at least 4 s between shakes, which gives ≤ 8 per reel (today 25 and 16).
4. **sportsdesk flash:** peak opacity goes from 0.55 to **0.3**, and it peaks at the cut (`t - 0.02`) instead of 0.12 s after it.
5. **Counter swap:** fade the old `.odo` out 0.15 s before the new one starts. Never keep two odometers live at once. This fixes sportsdesk 10.5 and push 13.5.
6. **Transition tape and scan line:** fire them only while the frame is cleared, or put them under live images. This fixes techdesk 13.5.

### H. Build-time checks (extend `blank_centre()`, lines 365-373)

Sample the `reflow` model every 0.1 s and print warnings next to the existing `BLANK CENTRE` line:

| Warning | Condition | Rule |
|---|---|---|
| `LONE LINE` | one text element with cap height < 140 px on screen for > 0.6 s | 5.3 |
| `DEAD BAND` | largest empty band in y 350-1420 is > 360 px for > 0.5 s | 5.2 |
| `THIN BLOCK` | block height < 440 px for > 1.0 s | 5.1 |
| `STATIC` | nothing added, removed or moved for > 2.2 s | 6.2 |
| `COLLISION` | two live boxes intersect with 24 px padding | 4.6 |
| `EDGE` | box outside x 65-1015, or right edge > 940 while its bottom is > 1100 | 1, 4.1 |
| `UI` | anything but chrome above y 240, or anything but background below y 1440 | 1 |
| `TINY` | text < 44 px (captions < 56; legal < 30) | 3 |
| `LOUD` | two shakes or flashes closer than 4 s | 6.5 |

### I. Spec-writing rules (for spec authors; no code change)

- Each beat has one hero and ≤ 2 supporting elements: logo + headline, number + label, or photo + line. Never a lone line for more than 0.6 s.
- A beat's words on screen are the key noun or number, not the sentence. The caption carries the sentence.
- Vary the lead from beat to beat: type-led, then image-led, then number-led (Rule 8.5).

---

## Sources

### Official and platform

- [S1] Meta Ads Guide, Instagram Reels video: "Consider leaving at least 14% of the top, 35% of the bottom, and 6% on each side of your asset free from text, logos, or other important creative elements." https://www.facebook.com/business/ads-guide/update/video/instagram-reels (undated, fetched 27 Sep 2026). The same numbers appear on the Reels image spec (…/image/instagram-reels) and the Stories video spec (…/video/instagram-story), both fetched 27 Sep 2026. Help Center 980593475366490, "About text overlays and the Safe Zone" (search snippet only; the page renders by JavaScript).
- [S2] Meta for Developers, IG User Media reference: `thumb_offset` "default value is 0, which is the first frame"; the feed cover uses the "middle most 1:1 square". https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/ (queried 27 Sep 2026 via Meta docs search).
- [S3] Meta, "The science of the hook", 15 Dec 2025. https://www.facebook.com/business/news/the-science-of-the-hook-how-to-supercharge-your-reels-performance
- [S4] Netflix Timed Text Style Guide (42 characters per line, 2 lines, 20 characters per second). https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977 (updated 19 Dec 2025).

### Safe-zone measurements (third-party, organic unless noted)

- [S5] Minta, 108/320/60/120 (undated): https://www.minta.ai/blog-post/instagram-safe-zone
- [S6] Outfy, 108 / 300-320 / 60 / 100-120 (16 Sep 2026): https://www.outfy.com/blog/instagram-safe-zone/
- [S7] Kreatli, 108/320/60/60 (5 Jan 2026): https://kreatli.com/guides/safe-zone-guide
- [S8] TryMyPost, top ~150, bottom ≥ 420, right 100, 4:5 feed crop (24 Jan 2026): https://www.trymypost.com/blog/instagram-reels-safe-zones-2026
- [S9] CampaignSwift, top 200; bottom 400 right / 270 left (18 Jun 2026): https://campaignswift.com/blog/instagram-safe-zone-sizes
- [S10] Ignite Social Media, box 220 top / 420 bottom (Jul 2026): https://www.ignitesocialmedia.com/content-creation/what-are-the-safe-zones-for-tiktoks-and-instagram-reels/
- [S11] Blitzcut, 220/480/90/120 (31 May 2026): https://blitzcutai.com/blog/best-caption-size-instagram-reels-2026
- [S12] Poster.ly visualiser, top 9% / bottom 25% / rail 13% (undated): https://www.poster.ly/tools/meta-ads-safe-zone-visualizer
- [S13] Hootsuite, "bottom fifth… caption" (12 Mar 2025): https://blog.hootsuite.com/instagram-video-sizes/
- Ads-value restatements of Meta's 14/35/6:
  - behaviour.digital (8 May 2026)
  - Lucid Media NZ (10 May 2026)
  - FrameExtractor (Aug 2026)
  - First Pier (11 Aug 2026)
  - Billo (16 Jun 2026), which claims Stories and Reels were unified in Mar 2026; no primary Meta source was found.
- Flagged as unreliable: Sprout Social (22 Aug 2025) gives old Stories numbers with bad maths. PostPlanify (Apr 2026) has internally inconsistent percentages.

### Grid, cross-posting, retention

- [S14] The Verge on Mosseri's 3:4 grid, 17 Jan 2025: https://x.com/verge/status/1880416715395461371
- [S15] Buffer, 17 Mar 2026: https://buffer.com/resources/instagram-image-size/
- [S16] Kapwing, 30 Dec 2025: https://www.kapwing.com/resources/instagrams-new-grid-layout-size-and-dimensions-2025/
- [S17] Cadenus, TikTok safe zone 130/484/44/140 (28 Jul 2026): https://cadenus.io/resources/blog/tiktok-safe-zone/
- [S27] OpusClip, 500-video study: interrupts every ~4 s gave 58% vs 41% retention; 21-34 s videos had the best completion (62%) (11 Nov 2025): https://www.opus.pro/blog/tiktok-length-format-retention-data
- [S28] Social Media Today: Instagram skip rate (first 3 s), 24 Aug 2025, https://www.socialmediatoday.com/news/instagram-adds-retention-insights-reels/758464/ ; Mosseri's ranking signals, 22 Jan 2025, https://www.socialmediatoday.com/news/instagram-shares-algorithm-insights-2025/738034/

### Editing practice and type

- [S20] EBU R95 v1.1 safe areas (Jun 2017): https://tech.ebu.ch/publications/r095
- [S21] Blitzcut, caption placement y 1200-1550 and sizes 60-75 / 75-95 px (1 Jun 2026): https://blitzcutai.com/blog/best-caption-placement-short-form-video
- [S22] OpusClip caption practices, bottom 25% and top 15% off-limits (11 Nov 2025): https://www.opus.pro/blog/tiktok-caption-subtitle-best-practices
- [S23] AdCreate, "span the full width… not float in small blocks", 72-96 px headlines (20 Feb 2026): https://adcreate.com/blog/vertical-video-ads-complete-guide
- [S24] RocketShip HQ, ≥ 60 px padding, first overlay within 0.5 s (8 Jun 2026): https://www.rocketshiphq.com/text-overlays-video-ads-mobile/
- [S25] legibility.info, body 40-60 px, titles 1.5× body (undated): https://legibility.info/rules-for-text-in-videos
- [S26] Envato, "read at phone size in under a second" (4 Aug 2026): https://elements.envato.com/learn/motion-graphics-for-short-form-video
- [S29] digitalsilk, one kinetic moment per section (3 Feb 2026). trydemotion, stagger 50-100 ms (6 May 2026).
- [S30] KreateFlo, captions y 250-1410, x 90-990 (18 Sep 2026). Cited by the research agent; URL not recorded.
- [S31] Mayer & Fiorella, "Principles for reducing extraneous processing" (coherence and redundancy), Cambridge Handbook of Multimedia Learning ch. 12, 2014 (history): https://www.cambridge.org/core/books/abs/cambridge-handbook-of-multimedia-learning/principles-for-reducing-extraneous-processing-in-multimedia-learning-coherence-signaling-redundancy-spatial-contiguity-and-temporal-contiguity-principles/CD5B7AE1279A9AB81F8EEBB53DBEC86E
- [S32] Art of Styleframe, visual hierarchy in motion graphics (5 May 2026): https://artofstyleframe.com/blog/visual-hierarchy-motion-graphics/
- Reddit (r/VideoEditing, r/editors, r/NewTubers, r/InstagramMarketing, r/AfterEffects, r/MotionDesign) **could not be read**. The fetch tool refused reddit.com, curl hit a bot wall, pullpush returned 429, and search returned no threads. The community input above therefore comes from creator and tool blogs. Several are vendor SEO pages, and their numbers were cross-checked; inconsistent ones are flagged.

### GitHub skills and templates (`[G: …]`, last commit on the cited file)

- **Barty-Bart/motion-graphics**, `skills/motion-broll/` (SKILL.md, reference/engine-api.md, engine/motion.js, examples/opus-aoe2), commit e8d610a, 2026-09-25: https://github.com/Barty-Bart/motion-graphics
  - It is 16:9 B-roll only, with no vertical, safe-zone or caption rules.
  - Taken from it: pace one change per spoken beat (0.4-1.2 s), major states 0.9-2.1 s apart, hero-to-title ratio ≈ 2.5:1, the shape fills 44-80% of the limiting dimension, "no dead time".
  - **Not taken**: its morphing white-card look conflicts with the owner's no-boxes, no-card-grids reel style.
- **heygen-com/hyperframes**, `skills/` (studio 2026-09-19, frame-worker-core 2026-09-19, video-composition 2026-07-15, typography 2026-09-14, embedded-captions rail 2026-09-19, faceless-explainer visual-design 2026-06-29): https://github.com/heygen-com/hyperframes
- **remotion-dev/skills**, `skills/remotion-create/video-layout.md` (2026-07-27: key text ≥ 80 px from the sides, headline ≥ 84, supporting ≥ 44): https://github.com/remotion-dev/skills
- **remotion-dev/template-tiktok**, `src/CaptionedVideo/Page.tsx` (2026-08-26: caption container bottom 350 px): https://github.com/remotion-dev/template-tiktok
- **iart-ai/tiktok-video-skills**, short-form-video and caption-animation (2026-06-22: caption baseline 62-70%, 56-80 px, max 2 lines). **iart-ai/kinetic-typography-skills** (2026-06-22): https://github.com/iart-ai
- **haidrrrry/claude-remotion-skill**, remotion-motion-graphics (2026-06-13 and 2026-08-12: Reels hero 80-140 px, captions at ~65% height, 30 s arc)
- **bangtutorial/bang-motion** (2026-09-15: ≤ 2 text levels, 9:16 minimums, nothing under 30 px)
- **nateherkai/hyperframes-student-kit**, short-form-edit quality gates (2026-09-08: a gap > 2.2 s fails, one jaw-dropper per 5 s)
- **audrey-560/hyperframes-cinematic-caption**, style-system (2026-08-25: hero tier 150-240 px, safe x 90-990, y 240-1520)
- **harper-carroll/reel-studio-skill** (2026-08-03: Reels UI ~110 top / 320 bottom / 120 right; title lockup 92/196/68)
- **fahmid-juboraj/reelforge** (2026-09-27: shake or flash 1-3 per 30 s)
- **DojoCodingLabs/remotion-superpowers**, create-short (2026-02-09: cut every 2-4 s, no scene > 5 s)
- **Fats403/remotion-captions-kit** (2026-08-15: ≤ 42 characters per page, min page 300 ms)
- **boring-marketing-com/ai-short-form-video-skill** (2026-07-07: 40 s arc, ≥ 60 px from every edge)
- **notivn/AIEV** (2026-08-03)

### Local skills (`[L#]`, all under `~/.claude/skills/`; no video plugins are installed under `~/.claude/plugins`)

- [L1] `hyperframes/references/frame-worker-core.md` (2026-09-26): fill the content area in portrait; hero high at 0.2-0.35 H; hero visible by 0.5 s; no narration sentences as on-screen text.
- [L2] `hyperframes-studio/SKILL.md` (2026-09-26): action-safe 90% and title-safe 80%.
- [L3] `hyperframes-creative/references/video-composition.md` and `motion-principles.md` (2026-09-26): hero text 60-80% of width; two focal points; "never a single text block floating in empty space"; decorative opacity 12-25%.
- [L4] `hyperframes-creative/references/typography.md` (2026-09-26): in-feed headlines ≥ 90 px, body ≥ 32 px; "3 s on screen = must be readable in 2".
- [L5] `embedded-captions/references/rail.md` and `composition-craft.md` (2026-09-26): portrait caption rail 600-700 px from the bottom; climax 0.16-0.22 H; hierarchy ≥ 1.8×; gap voids read as disconnected; one home zone.
- [L6] `phases/visual-design/rules/composition.md` (2026-06-17): portrait centre at 0.42 H; primary visual ≥ 40%; kinetic block 50-75% of height × 60-80% of width; squint and poster tests.
- [L7] `motion-graphics/references/builder-contract.md` (2026-09-26): padding ≥ 80 px, gap 24.
- [L8] `embedded-captions/references/aesthetic-principles.md` and `reference-bar.md` (2026-09-26): words ≥ 0.4 s; caption what adds, cut what restates; the five positive checks. `references/aesthetic-principles.md` (2026-06-17): 9:16 caption zone y 12-78%.
- [L9] `hyperframes-animation/blueprints/kinetic-type-beats.md` (2026-09-26): big→small scale-down; lines re-centre as they add.

### Our own measurements

- `scratchpad/edit-audit/measure.py` (content bands per frame), `holds.py` (static holds), and the montages `m1.jpg`-`m5.jpg` with guide lines at y 250 / 1400 / 1550 and x 930.
- Font-fit numbers come from the real `.woff2` files in `tools/kinetic/fonts/`.
- Shake counts come from `build/<theme>/index.html` (`shakes.push`).
