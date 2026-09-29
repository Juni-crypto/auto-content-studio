"""The review committee: four independent reviewers, each a separate Codex call. Nothing posts unless all of them pass.

  fact    — fact-checker with live web search (numbers, names, dates, 2025–26 freshness)
  voice   — brand & script editor (the frozen format, hook, conversational voice, caption lines)
  edit    — picture editor (contact sheets / slide images + the engine's layout audit)
  safety  — standards & legal (defamation, sensitive events, rights, required caption lines)

The chair is code: any block -> rejected; any fix -> the writer revises (at most MAX_FIX_ROUNDS); all pass -> ready.
"""
import json
from . import llm
from .config import PROMPTS

ROLES = {
    "fact": ("Fact-checker", True,
             "Use web search. Check every claim in the spoken lines (tts), the on-screen text (captions, stack/slam/line/tag/count "
             "cues, slide strings) and the Instagram caption against the research sources and fresh searches: names and spellings, "
             "numbers, scores, dates, who did what, and every 'biggest / first / most / record' claim. Statistics must be current "
             "(2025–26); history must be framed as history. Time words ('today', 'on Friday', 'this week', 'for N years') must be "
             "right as of today. False -> block. Unverifiable or overstated -> fix with the safe wording."),
    "voice": ("Brand and script editor", False,
              "Check the frozen format: the hook is the very first words (never the greeting), with the greeting right after it in the same breath; spoken lines that sound like a person talking "
              "to a friend (no headline shorthand, no stacked names or places, no dash/ellipsis gimmicks); a few natural reactions, at "
              "most two 'Haha'; the exact sign-off 'Follow <brand> for more, and catch you later, <friend>!'; English only; the hook is "
              "genuinely catchy; this story differs from the brand's other items today; the length target is met. For carousels: a "
              "strong cover hook, short punchy strings (NEWS carousels — slides typed cover/text/images — are built like the big news pages "
              "by design: the cover headline is ONE news sentence of 12–24 words, and text slides carry 1–3 punch lines with at most one "
              "short sentence each; judge them on clarity and a friendly brand voice, never ask for single-word slogans), the brand voice in the punch lines, a Follow call on the last slide. Caption: "
              "hook first; its written part ends with a question (hashtags, the trademark / not-affiliated lines and 'AI voice · real facts.' "
              "come after it by design — that is correct; a '💬 Comment KEYWORD and I'll DM you …' line is the studio's comment-to-DM offer, also by design); trademark lines present for every real brand shown; 'AI voice' on voiced posts."),
    "edit": ("Picture editor", False,
             "You get the rendered frames (contact sheets, one frame per second, timestamp under each; the frame is 1080x1920) or "
             "the finished slide images, plus the engine's layout audit. Check: the hook is already on screen in the first frame; "
             "the centre is never blank or near-empty for more than about a second; text is never cut off, overlapping or outside "
             "the safe area (no text above y 240 or below y 1440; right edge clear of Instagram's buttons in the lower half); logos "
             "are the real, correct, unaltered official logos of the named entity; images match what is being said; emojis never "
             "cover words; the end card shows the brand tile and the Follow button — by design it animates a tap from '+ Follow' to "
             "'Following ✓', so 'Following' on the last frames is correct. Frames can catch elements mid-entrance or mid-exit "
             "(sliding, scaling, fading): judge the settled layout, not a transition. People: the studio only uses openly licensed "
             "real photos and never draws real faces, so when no photo exists a person shown by name in big type (with a flag or "
             "logo) is CORRECT — never flag a missing photo of a person. Brands likewise: logos are fetched from official sources and "
             "vision-checked, so a brand shown by name in big type means no verified official logo exists — correct; flag only a "
             "WRONG or unofficial logo. Layout audit: BLANK CENTRE must be fixed; THIN BLOCK / "
             "LONE LINE moments under 3 s while a headline is on screen are acceptable. Slides: every quoted string appears exactly (spelling, digits), "
             "no extra words, no invented logos, flags, faces or fake UI, readable, nothing important in the top/bottom 8%. "
             "For reels your fixes must be visual only (cues, sizes, images) because the voice is already recorded. "
             "Say \"fix\" ONLY for real faults: a quoted string wrong, garbled or missing; a wrong, invented or redrawn logo; text cut "
             "off or outside the frame; unreadable text; a blank centre; a drawn face of a real person. Spacing, small extra labels or "
             "counters, punctuation style, 'could be bigger', and near-edge placement that is still fully visible are NOT faults: pass "
             "and mention them in the summary."),
    "safety": ("Standards and legal reviewer", False,
               "Check: accusations (crime, fraud, doping, cheating, misconduct) stated as fact without an official finding; "
               "sensitive events (deaths, injuries, disasters, communal or political conflict) treated with respect and never joked "
               "about (no 'Haha' or laughing emojis near them); no personal details of minors; no betting or gambling promotion; no "
               "medical or investment advice; rights: official logos / official press images, and real photos only from open-licence "
               "collections with a 'Photos:' credit in the caption; no agency/wire or news-site photos, no broadcast footage, no "
               "AI-generated faces of real people; nothing implies a brand sponsored or endorsed the post; the caption carries "
               "'<Brand> is a trademark of <Company>. Not affiliated.' for every real brand shown and 'AI voice' on voiced posts; "
               "Instagram community guidelines."),
}


def review(role, *, rules, today, brand, kind, slot, research, piece, caption, others, extra="", images=()):
    name, search, brief = ROLES[role]
    prompt = llm.fill((PROMPTS / "committee.md").read_text(), role=role, role_name=name, role_brief=brief, rules=rules, today=today,
                      brand_name=brand, kind=kind, slot=slot or "as soon as ready", research=json.dumps(research, ensure_ascii=False, indent=1),
                      piece=piece, caption=caption, others=others or "none", extra=extra)
    try:
        v = llm.ask_json(prompt, images=images, search=search)
    except Exception as e:   # a reviewer that cannot answer is a fix, never a silent pass
        v = {"verdict": "fix", "score": 0, "issues": [{"where": "committee", "problem": f"{name} could not review: {e}", "fix": "retry"}]}
    v["role"] = role
    if v.get("verdict") not in ("pass", "fix", "block"): v["verdict"] = "fix"
    return v


def chair(verdicts):
    """(decision, issues): block beats fix beats pass."""
    kinds = [v["verdict"] for v in verdicts]
    decision = "block" if "block" in kinds else "fix" if "fix" in kinds else "pass"
    issues = [dict(i, role=v["role"]) for v in verdicts if v["verdict"] != "pass" for i in v.get("issues", [])]
    return decision, issues


def feedback(issues, previous, visual_only=False):
    lines = [f"- [{i.get('role')}] {i.get('where', '')}: {i.get('problem', '')} -> {i.get('fix', '')}" for i in issues]
    keep = ("Keep every \"tts\" and \"caption\" EXACTLY as they are (the voice is already recorded); change only cues, holds and assets."
            if visual_only else "Change nothing else that already works.")
    return ("## Committee feedback on your previous draft — fix ALL of these\n" + "\n".join(lines) + f"\n{keep}\n\n"
            "## Your previous draft\n" + json.dumps(previous, ensure_ascii=False, indent=1))


def badge(verdicts):
    mark = {"pass": "✓", "fix": "✎", "block": "✗"}
    return " ".join(f"{v['role']} {mark[v['verdict']]}" for v in verdicts)
