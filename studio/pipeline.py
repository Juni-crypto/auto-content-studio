"""Make one library item, start to finish, following the frozen format.

  reel / story : research -> write kinetic spec -> committee (fact, voice, safety) -> logos + object images -> Aiden voice
                 -> kreel build (layout audit) -> render -> picture editor on contact sheets -> ready
  news carousel: research -> official gallery (real images from the story's official pages) -> slides around those images
                 -> committee (fact, voice, safety) -> images placed pixel-true + Codex text panels -> picture editor -> ready
  carousel     : research -> slide briefs -> committee (fact, voice, safety) -> logos -> Codex slide designs -> crop 4:5
                 -> picture editor on the slides -> [animated: Codex empty plates -> motion clips -> picture editor] -> ready

A committee "fix" sends the draft back to the writer with every issue (at most MAX_FIX_ROUNDS); "block" rejects the item.
Everything an item produces lives in work/item-NNNNN/; what gets posted is copied to media/ (public, served by Caddy).
"""
import json, pathlib, random, re, secrets, shutil, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from . import animate, assets, committee, db, dm, graph, llm, newsdeck, tg
from .config import (ASSETS, BRANDS, DATA, EXAMPLES, HYPERFRAMES, KIN, MAX_FIX_ROUNDS, MEDIA, PROMPTS, PUBLIC, PY, RULES, VETO_MIN, WORK)

CUES = {"stack", "slam", "line", "count", "image", "tag", "emoji", "outro", "clear"}
EMOJI = sorted(p.stem for p in (KIN / "emoji").glob("*.png"))
EXAMPLE_SPEC = {"techdesk": "tech/final/spec.json", "sportsdesk": "sports/final/spec.json", "bizdesk": "stories/coming-soon/bizdesk.json"}
LENGTH = {"reel": "A reel of 35–55 seconds: 7–11 beats, about 100–160 spoken words in total.",
          "story": "A story of 12–20 seconds: 3–5 beats, about 30–55 spoken words: the hook, then the greeting, one or two key facts, the sign-off."}


class CpuTurn:
    """The CPU-heavy steps (voice, render) take turns across every job process: an exclusive file lock (flock), held for the
    step. Turns go by priority: while a running job with a HIGHER priority still needs this step (the owner's 🔥 top post),
    lower ones wait even if the lock is free. Each `with` opens its own handle, so threads and processes can share one CpuTurn."""
    def __init__(self, name):
        self.name = name; self.path = DATA / "locks" / f"{name}.lock"; self.local = threading.local()

    def _ahead(self):
        import os
        me = os.environ.get("STUDIO_JOB_ID")
        if not me: return False
        mine = db.get_job(int(me)); mp = (mine or {}).get("priority") or 0
        with db.conn() as c:
            rows = c.execute("""SELECT j.pid, i.kind, i.dir FROM jobs j JOIN items i ON i.id = j.item_id
                                WHERE j.status = 'running' AND j.priority > ? AND j.id <> ?""", (mp, int(me))).fetchall()
        for r in rows:
            if not db.alive(r["pid"]) or r["kind"] not in ("reel", "story"): continue
            done = (pathlib.Path(r["dir"]) / "vo" / "said.json").exists() if r["dir"] else False
            if self.name == "voice" and done: continue   # it already has its voice
            return True
        return False

    def __enter__(self):
        import fcntl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            if not self._ahead():
                f = open(self.path, "a")
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); self.local.f = f
                    return self
                except BlockingIOError:
                    f.close()
            time.sleep(3)

    def __exit__(self, *exc):
        import fcntl
        f = self.local.f; fcntl.flock(f, fcntl.LOCK_UN); f.close()


CPU = {"voice": CpuTurn("voice"), "render": CpuTurn("render")}


class Rejected(Exception):
    pass


def gate(it, reason, draft=None):
    """A research/committee "no". Normally it stops the item and keeps the draft so the owner can see it and overrule; when the
    owner has already overruled (`studio override`), it is logged and the pipeline carries on."""
    if it.get("override"):
        db.log(it["id"], f"owner override — carried on past: {reason[:300]}", "warn"); return
    if draft: db.update(it["id"], draft=draft)
    raise Rejected(reason)


def norm(w):
    return w.lower().strip('.,?!":;')


def today():
    return db.now().strftime("%A %d %B %Y, %H:%M IST")


def rules():
    return llm.fill((PROMPTS / "rules.md").read_text(), today=today())


def others(it):
    """Titles of this brand's other items within a day of this slot, and of the last 14 days, so stories never repeat."""
    rows = db.items("brand=? AND id<>? AND status NOT IN ('removed','rejected','declined') AND created >= ?",
                    (it["brand"], it["id"], db.iso(db.now() - db.dt.timedelta(days=14))))
    return "\n".join(f"- #{r['id']} {r['kind']} {r['slot'] or ''}: {r['topic']} {('— ' + r['angle']) if r['angle'] else ''}" for r in rows) or "none"


def mmdd():
    return db.now().strftime("%m%d")


# ---------------------------------------------------------------- research
SCOUT = {b: threading.Lock() for b in BRANDS}   # "auto" stories of one brand are picked one at a time, so two never pick the same


def research(it, d):
    f = d / "research.json"
    if f.exists() and time.time() - f.stat().st_mtime < 6 * 3600: return json.loads(f.read_text())
    if it["topic"] in (None, "", "auto"):
        with SCOUT[it["brand"]]:
            return _research(db.get(it["id"]), d)   # re-read: the avoid list now holds what the other lane just picked
    return _research(it, d)


def _research(it, d):
    f = d / "research.json"
    b = BRANDS[it["brand"]]
    leads = graph.known_facts(" ".join(filter(None, (it["topic"], it["angle"], it["notes"]))))
    notes = (it["notes"] or "none") + ("\n\nLeads from our own library (already verified once; re-check they are still current before use):\n"
                                       + "\n".join(f"- {x['claim']} ({x['date'] or 'undated'})" for x in leads) if leads else "")
    r = llm.ask_json(llm.fill((PROMPTS / "research.md").read_text(), rules=rules(), today=today(), brand_name=b["name"], beat=b["beat"],
                              focus=b["focus"], kind=it["kind"], topic=it["topic"] or "auto", angle=it["angle"] or "(your call)",
                              notes=notes, avoid=others(it)), search=True)
    f.write_text(json.dumps(r, indent=1, ensure_ascii=False))
    try:
        graph.record_research(it["id"], r)
    except Exception as e:
        db.log(it["id"], f"graph: could not record research: {e}", "warn")
    if it["topic"] in (None, "", "auto"): db.update(it["id"], topic=r.get("topic", "auto"))
    if r.get("confidence") == "low" or not r.get("facts"):
        gate(it, f"research could not verify this story well enough: {r.get('why_now', '')[:300]}",
             {"script": "Research notes: " + json.dumps(r.get("facts", [])[:6], ensure_ascii=False)[:2000]})
    return r


# ---------------------------------------------------------------- kinetic (reel / story)
def validate(spec, b, kind, research=None):
    """Structural rules the engine and the frozen format need. Returns problems for the writer to fix."""
    p = []; beats = spec.get("beats") or []
    if spec.get("cta"):
        p += dm.check_cta(spec["cta"], research or {})
        if beats and not dm.keyword_in(spec["cta"].get("keyword", "#"), beats[-1]["caption"]):
            p.append(f'with a cta the last beat must say "Comment {spec["cta"].get("keyword")} and I\'ll send you ..." before the sign-off')
    if not beats: return ["no beats"]
    first = [norm(w) for w in beats[0]["caption"].split() if norm(w)]
    g = [norm(w) for w in b["greeting"].split()]
    at = next((k for k in range(len(first) - 1) if first[k:k + 2] == g), None)
    if at is None: p.append(f'beat 1 must say "{b["greeting"]}!" right after the hook')
    elif at == 0: p.append(f'hook first: beat 1 must open with the hook, then "{b["greeting"]}!" (never start with the greeting)')
    elif at > 14: p.append(f'"{b["greeting"]}!" must come right after the hook (within the first ~12 words of beat 1)')
    last = beats[-1]["caption"].lower()
    if f"follow {b['say'].lower()} for more" not in last or "catch you later" not in last or b["friend"] not in last:
        p.append(f'the last beat must end "Follow {b["say"]} for more, and catch you later, {b["friend"]}!"')
    names = {a.get("file") for a in spec.get("assets", [])}
    words = sum(len(x["tts"].split()) for x in beats)
    lo, hi = (90, 175) if kind == "reel" else (20, 60)
    if not lo <= words <= hi: p.append(f"spoken length is {words} words; the target is {lo}-{hi}")
    if sum(x["tts"].lower().count("haha") for x in beats) > 2: p.append("at most two 'Haha' per piece")
    if re.search(r"[ऀ-ॿ]", json.dumps(spec, ensure_ascii=False)): p.append("English letters only (no Devanagari)")
    outros = 0
    for i, x in enumerate(beats, 1):
        caps = [norm(w) for w in x["caption"].split()]
        if not x.get("cues"): p.append(f"beat {i} has no cues (blank centre)")
        for c in x.get("cues", []):
            do = c.get("do")
            if do not in CUES: p.append(f"beat {i}: unknown cue type {do!r}"); continue
            ats = [l.get("at") for l in c.get("lines", [])] if do == "stack" else [c.get("at")]
            for a in ats:
                if isinstance(a, (int, float)): continue
                if not a or not any(w.startswith(norm(a)) for w in caps): p.append(f'beat {i}: cue word "{a}" is not in that beat\'s caption')
            if do == "emoji":
                for e in (c["e"] if isinstance(c.get("e"), list) else [c.get("e")]):
                    if e not in EMOJI: p.append(f"beat {i}: emoji {e!r} is not in the allowed list")
            if do == "image" and pathlib.Path(c.get("img", "")).name not in names: p.append(f"beat {i}: image {c.get('img')} is not listed in assets")
            if do == "count" and not isinstance(c.get("to"), (int, float)): p.append(f"beat {i}: count 'to' must be a number")
            if do == "outro": outros += 1
    if outros != 1 or not any(c.get("do") == "outro" for c in beats[-1].get("cues", [])): p.append("exactly one outro cue, in the last beat, at 'follow'")
    return p


def write_kinetic(it, d, facts, feedback="", visual_only=False, previous=None):
    b = BRANDS[it["brand"]]
    ex = json.loads((EXAMPLES / EXAMPLE_SPEC[it["brand"]]).read_text())
    example = json.dumps({"beats": ex["beats"]}, ensure_ascii=False)[:9000]
    if it["brand"] == "bizdesk":   # the frozen Parle-G reel carries the storytelling tone; the teaser story carries the cue style
        tone = json.loads((EXAMPLES / "business/_work/parleg/voice-bizdesk.json").read_text())
        example += ("\n\nThe finished BIZDESK reel's spoken script (tone and storytelling to match; its pictures were made by another engine):\n"
                    + "\n".join(b["caption"] for b in tone["beats"]))[:6000]
    gf = d / "gallery.json"
    gallery = json.loads(gf.read_text()) if gf.exists() else []
    pics = "\n".join(f"- id {g['id']}: {g['kind']}, {g['what']} ({g['w']}x{g['h']}{', has big text' if g.get('text_heavy') else ''})" for g in gallery) \
        or "none found — use logos, press images and real photos"
    prompt = llm.fill((PROMPTS / "reel.md").read_text(), rules=rules(), today=today(), kind=it["kind"], brand_name=b["name"], focus=b["focus"],
                      greeting=b["greeting"], friend=b["friend"], say=b["say"], voice=b["voice"], length=LENGTH[it["kind"]],
                      research=json.dumps(facts, ensure_ascii=False, indent=1), emoji=", ".join(EMOJI), example=example, avoid=others(it),
                      no_faces_note="Generated objects never show people or faces; real people appear only through real photos (kind \"photo\").",
                      feedback=feedback, handle=b["handle"], gallery=pics)
    prompt = owner_call(it, prompt); probs = ["the writer kept declining"]
    for attempt in range(3):
        spec = llm.ask_json(prompt)
        if spec.get("cannot"):
            if visual_only: spec.pop("cannot")
            else: prompt = cannot(it, spec, prompt); continue
        if visual_only and previous:   # the voice is recorded: spoken words must not move
            for nb, ob in zip(spec.get("beats", []), previous["beats"]): nb["tts"], nb["caption"] = ob["tts"], ob["caption"]
            spec["beats"] = spec["beats"][:len(previous["beats"])]
        probs = validate(spec, b, it["kind"], facts)
        if not probs: return spec
        prompt += "\n\n## Your last reply broke these rules — fix them and reply again with the full JSON\n" + "\n".join(f"- {x}" for x in probs)
        db.log(it["id"], f"writer draft {attempt + 1} invalid: {'; '.join(probs)[:400]}", "warn")
    raise RuntimeError("the writer could not produce a valid spec: " + "; ".join(probs))


def script_view(spec):
    out = []
    for i, x in enumerate(spec["beats"], 1):
        shown = []
        for c in x.get("cues", []):
            if c["do"] == "stack": shown.append(" / ".join(l["text"] for l in c["lines"]))
            elif c.get("text"): shown.append(c["text"])
            elif c["do"] == "count": shown.append(f"{c.get('prefix', '')}{c['to']}{c.get('suffix', '')} {c.get('label', '')}")
            elif c["do"] == "image": shown.append(f"[image {pathlib.Path(c['img']).name}]")
            elif c["do"] == "emoji": shown.append(f"[emoji {c['e']}]")
            elif c["do"] == "outro": shown.append("[end card + Follow button]")
        out.append(f"Beat {i}\n  says: {x['tts']}\n  caption: {x['caption']}\n  on screen: {' | '.join(shown)}")
    return "\n".join(out) + cta_view(spec)


def cta_view(piece):
    c = piece.get("cta")
    return (f"\nComment-to-DM: people who comment \"{c.get('keyword')}\" get this DM (check every link and claim):\n{c.get('dm')}") if c else ""


def keep_cta(it, d, piece, research):
    """Save a valid cta for the DM scanner (a carousel's broken cta is dropped, never sent)."""
    c = piece.get("cta")
    if not c: return
    probs = dm.check_cta(c, research)
    if probs:
        db.log(it["id"], f"cta dropped: {'; '.join(probs)[:300]}", "warn"); piece["cta"] = None; return
    (d / "cta.json").write_text(json.dumps(c, ensure_ascii=False))


def caption_text(piece, voiced):
    """The posted caption: the writer's text, hashtags, one line per credit, then the studio's fixed lines. The fixed lines are
    added only here, so any copy the writer included is removed first (no duplicates)."""
    def fixed(l): return "ai voice" in l.lower() or l.lower().startswith("photos:")
    body = "\n".join(l for l in piece.get("caption", "").strip().splitlines() if not fixed(l)).strip()
    c = piece.get("cta")
    if c and c.get("keyword") and not re.search(rf"comment\W+{re.escape(c['keyword'])}\b", body, re.I):
        ls = body.splitlines(); line = f"💬 Comment {c['keyword']} and I'll DM you {c.get('offer') or 'the links'}."
        body = "\n".join(ls[:-1] + [line, ls[-1]] if ls and ls[-1].rstrip().endswith("?") else ls + [line])   # the question stays last
    tags = " ".join(dict.fromkeys(t if t.startswith("#") else f"#{t}" for t in piece.get("hashtags", [])[:10]))
    credits = list(dict.fromkeys(c.strip() for c in piece.get("credits", []) if c.strip() and not fixed(c)))
    lines = [body, "", tags, "", *credits]
    if piece.get("image_credits"): lines.append("Images: " + "; ".join(piece["image_credits"]) + " (official)")
    if piece.get("photo_credits"): lines.append("Photos: " + "; ".join(piece["photo_credits"]))
    if piece.get("ai_illustration"): lines.append("Illustration: AI-generated.")
    if voiced: lines.append("AI voice · real facts.")
    return "\n".join(l for l in lines if l is not None).strip()


def run_committee(it, facts, piece_text, caption, roles, extra="", images=()):
    b = BRANDS[it["brand"]]
    kw = dict(rules=rules(), today=today(), brand=b["name"], kind=it["kind"], slot=it["slot"], research=facts, piece=piece_text,
              caption=caption, others=others(it), extra=extra, images=images)
    with ThreadPoolExecutor(len(roles)) as ex:
        verdicts = list(ex.map(lambda r: committee.review(r, **kw), roles))
    return verdicts


def get_asset(it, a, dest):
    """One requested picture, graph first. Returns the graph asset row, or None when nothing safe exists."""
    kind, iid = a.get("kind"), it["id"]
    if kind == "gallery":   # an official image already vetted into the graph for this story
        rows = graph.rows("SELECT * FROM assets WHERE id=?", (int(a.get("id") or 0),))
        if not rows: return None
        im = Image.open(rows[0]["path"]); (im.convert("RGB") if str(dest).endswith(".jpg") else im).save(dest); graph.used(rows[0]["id"], iid)
        return dict(rows[0], official=True)
    if kind == "logo": return assets.logo(a["entity"], dest, a.get("official_site"), iid)
    if kind == "press": return assets.press(a["entity"], a.get("subject") or a.get("prompt") or a["file"], dest, a.get("official_site"), iid)
    if kind == "photo": return assets.photo(a.get("query") or a.get("prompt") or a["file"], dest, a.get("entity"), iid)
    if kind == "flag": return assets.flag(a.get("entity") or a.get("country"), dest, iid)
    return assets.object_image(dest, a.get("prompt", a["file"]), iid)


def fetch_assets(it, d, spec):
    """Logos, press images, real CC photos and generated objects — reused from the graph when we have them. A picture we
    cannot source safely is dropped from the cues (never faked). Photo credits go into the caption."""
    credits, missing = [], set()
    (d / "assets").mkdir(exist_ok=True)
    for a in spec.get("assets", []):
        dest = d / "assets" / a["file"]
        try:
            rec = get_asset(it, a, dest)
            if rec: credits.append({k: rec.get(k) for k in ("id", "kind", "title", "source_page", "licence", "credit")})
            else: missing.add(a["file"])
        except Exception as e:
            db.log(it["id"], f"asset {a['file']} failed: {e}", "warn"); missing.add(a["file"])
    spec["photo_credits"] = sorted({c["credit"] for c in credits if c.get("credit")})
    gal = {g["id"]: g for g in json.loads((d / "gallery.json").read_text())} if (d / "gallery.json").exists() else {}
    spec["image_credits"] = sorted({gal[int(a["id"])]["owner"] for a in spec.get("assets", []) if a.get("kind") == "gallery"
                                    and a["file"] not in missing and int(a.get("id") or 0) in gal and gal[int(a["id"])].get("owner")})
    if missing:
        for x in spec["beats"]:
            x["cues"] = [c for c in x["cues"] if not (c["do"] == "image" and pathlib.Path(c["img"]).name in missing)]
        db.log(it["id"], f"no safe source for {sorted(missing)}; those images were left out", "warn")
    (d / "CREDITS.json").write_text(json.dumps(credits, indent=1, ensure_ascii=False))
    return credits


def full_spec(it, spec):
    b = BRANDS[it["brand"]]
    hook = next((c for c in spec["beats"][0].get("cues", []) if c.get("do") == "stack"), None)
    if hook: hook["together"] = True   # the whole hook is readable on frame 0 (Instagram's default cover)
    for c in spec["beats"][-1].get("cues", []):
        if c.get("do") == "outro": c["signoff"] = f"Catch you later, {b['friend']}"   # the frozen sign-off, always
    first = [norm(w) for w in spec["beats"][0]["caption"].split() if norm(w)]
    hey = first.index("hey") if "hey" in first else 3   # hook first: the greeting chip stays until just after "Hey <friend>"
    until = first[min(len(first) - 1, max(6, hey + 3))] if first else "hey"
    return dict(title=spec.get("title", it["topic"]), voice_dir="vo", music=str(ASSETS / "music" / random.choice(b["music"])),
                kicker={b["theme"]: b["kicker"].format(mmdd=mmdd())},
                greeting={"text": b["greeting"], "emoji": b["greet_emoji"], "until": until},
                voice={"engine": "qwen3", "speaker": "Aiden", "takes": 2, "seed": random.randint(1, 99),
                       "style": b["voice"], **({"max_tempo": 1.12} if it["kind"] == "story" else {})},
                beats=spec["beats"])


def voice(d, full, force=False):
    vo = d / "vo"
    said = json.dumps([x["tts"] for x in full["beats"]])
    if not force and (vo / "timing.json").exists() and (vo / "said.json").exists() and (vo / "said.json").read_text() == said: return
    shutil.rmtree(vo, ignore_errors=True)
    with CPU["voice"]:
        p = subprocess.run([str(PY), str(KIN / "voice_qwen.py"), str(d / "spec.json"), str(vo)], capture_output=True, text=True, timeout=7200)
    if p.returncode or not (vo / "timing.json").exists(): raise RuntimeError(f"voice failed: {p.stderr[-800:]}")
    (vo / "said.json").write_text(said)


def build(it, d):
    b = BRANDS[it["brand"]]; out = d / "build"
    shutil.rmtree(out / b["theme"], ignore_errors=True)
    p = subprocess.run([str(PY), str(KIN / "kreel.py"), str(d / "spec.json"), b["theme"], str(out)], capture_output=True, text=True, timeout=600)
    if p.returncode: raise RuntimeError(f"build failed: {(p.stderr or p.stdout)[-800:]}")
    warnings = [l.strip() for l in p.stdout.splitlines() if re.match(r"\s+(BLANK CENTRE|THIN BLOCK|LONE LINE)", l)]
    return out / b["theme"], warnings, p.stdout


def render(proj):
    mp4 = proj / "out.mp4"
    if mp4.exists(): mp4.unlink()
    with CPU["render"]:
        p = subprocess.run(["npx", "--yes", HYPERFRAMES, "render", str(proj), "-o", str(mp4), "--quiet", "--crf", "20"], cwd=proj,
                           capture_output=True, text=True, timeout=3600)
    if not mp4.exists(): raise RuntimeError(f"render failed: {(p.stderr or p.stdout)[-800:]}")
    return mp4


def make_kinetic(it, d, facts):
    if not (d / "gallery.json").exists():   # real official images for the story, before the writer starts
        try:
            (d / "gallery.json").write_text(json.dumps(assets.official_gallery(facts, it["id"], want=8), indent=1))
        except Exception as e:
            db.log(it["id"], f"official gallery failed: {e}", "warn")
    rounds = 0; spec = write_kinetic(it, d, facts)
    while True:   # script committee: fact, voice, safety — before any CPU is spent on voice and render
        cap = caption_text(spec, True)
        verdicts = run_committee(it, facts, script_view(spec), cap, ["fact", "voice", "safety"])
        decision, issues = committee.chair(verdicts); db.log(it["id"], f"script committee round {rounds + 1}: {committee.badge(verdicts)}")
        for i in issues: db.log(it["id"], f"  [{i.get('role')}] {i.get('where', '')}: {i.get('problem', '')}"[:400], "note")
        if decision == "pass": break
        why = "; ".join(i.get("problem", "") for i in issues)[:600]
        if decision == "block":
            gate(it, "committee blocked the script: " + why, {"script": script_view(spec), "caption": caption_text(spec, True)}); break
        rounds += 1
        if rounds > MAX_FIX_ROUNDS:
            if all(i.get("role") == "voice" for i in issues):   # style notes only: made, then it waits for the owner's call
                db.log(it["id"], "only style notes left after the fixes: making it; the owner decides", "warn"); break
            gate(it, "committee still unhappy after fixes: " + why, {"script": script_view(spec), "caption": caption_text(spec, True)}); break
        spec = write_kinetic(it, d, facts, committee.feedback(issues, spec))
    script_verdicts = verdicts
    keep_cta(it, d, spec, facts)
    for rnd in range(MAX_FIX_ROUNDS + 1):   # picture: assets, voice, build, render, then the picture editor
        fetch_assets(it, d, spec)
        full = full_spec(it, spec); (d / "spec.json").write_text(json.dumps(full, indent=1, ensure_ascii=False))
        db.update(it["id"], caption=caption_text(spec, True)); voice(d, full)
        proj, warnings, _ = build(it, d)
        mp4 = render(proj)
        sheets = assets.contact_sheets(mp4, d / "frames")
        extra = ("Layout audit from the engine (BLANK CENTRE must be fixed; THIN BLOCK / LONE LINE under 3 s are acceptable): "
                 + ("; ".join(warnings) or "no warnings") +
                 f"\nThe attached images are {len(sheets)} contact sheets in time order.")
        edit = run_committee(it, facts, script_view(spec), caption_text(spec, True), ["edit"], extra=extra, images=sheets[:5])[0]
        db.log(it["id"], f"picture round {rnd + 1}: {committee.badge([edit])} {edit.get('summary', '')[:200]}")
        for i in edit.get("issues", []): db.log(it["id"], f"  [edit] {i.get('where', '')}: {i.get('problem', '')}"[:400], "note")
        if edit["verdict"] == "pass" and not any(w.startswith("BLANK CENTRE") for w in warnings): break
        if edit["verdict"] == "block":
            gate(it, "picture editor blocked it: " + edit.get("summary", "") + " " + "; ".join(warnings),
                 {"files": [str(mp4)], "caption": caption_text(spec, True)}); break
        if rnd == MAX_FIX_ROUNDS:   # small picture notes left after the fixes: the owner decides (it waits in "Needs you")
            edit["summary"] = (edit.get("summary", "") + " " + "; ".join(warnings)).strip(); break
        issues = [dict(i, role="edit") for i in edit.get("issues", [])] + [{"role": "edit", "where": w, "problem": w, "fix": "add or move a centre cue so nothing is blank"} for w in warnings]
        spec = write_kinetic(it, d, facts, committee.feedback(issues, spec, visual_only=True), visual_only=True, previous=spec)
    return mp4, script_verdicts + [edit], caption_text(spec, True)


# ---------------------------------------------------------------- carousel
POST = ("Canvas is portrait 2:3, but compose it as a 4:5 Instagram carousel slide: keep every piece of text, every logo and every "
        "image inside the central area, and leave the top 8% and bottom 8% as plain continuing background that will be cropped.")
BOARD_NOTE = ("Image 1 is this brand's identity board: follow its colours, type, spacing and motifs exactly, but do not copy its "
              "example words or layout panels.")
IMG_RULES = ("Never draw a real, identifiable person or face — real people appear only as the attached real photos, unaltered. "
             "Exact readable text only as quoted, spelled and punctuated exactly, in English; digits exactly right; no other words "
             "anywhere, no extra slogans, no fake UI text, no handles except where quoted, no follower counts, no watermarks. Official "
             "logos are reproduced faithfully and unaltered from their reference images (same shapes, same colours), placed on a clean "
             "plate where the background would hide them; never redraw, recolour or invent a logo, and never draw a flag or emblem "
             "from memory. Avoid: purple gradients, neon glow, clutter, cards inside cards, emoji.")


OVERRIDE = ("\n\n## The owner's call\nThe owner has read the committee's concerns and decided to publish this story. Write it — never "
            "reply \"cannot\". Stay honest: attribute every claim that only one outlet reported to that outlet (\"TechCrunch reports…\", "
            "\"according to TechCrunch\"), say plainly what the companies have and haven't confirmed, and never state an unconfirmed claim as fact.")


def owner_call(it, prompt):
    """An overridden item: the writer must write it (with attribution), not refuse."""
    return prompt + OVERRIDE if (db.get(it["id"]) or {}).get("override") else prompt


def cannot(it, piece, prompt):
    """The writer declined. Without an override that is a real "no" (refuse); with one, ask again. Returns the new prompt."""
    if not (db.get(it["id"]) or {}).get("override"): refuse(it, piece["cannot"])
    db.log(it["id"], f"writer declined ({str(piece['cannot'])[:160]}); the owner overrode, asking it to write with attribution", "warn")
    return prompt + "\n\nYou replied \"cannot\". The owner has decided to publish: write the full JSON now, attributing unconfirmed claims."


def refuse(it, why):
    """The writer says the verified facts can't carry this post: a committee-style "no" with the real reason (never an empty draft)."""
    gate(it, "the writer couldn't build it from the verified facts: " + str(why)[:500], {"script": "Writer: " + str(why)[:1500]})
    raise RuntimeError("the writer couldn't build it from the verified facts: " + str(why)[:300])   # an override can't continue without a draft


def check_carousel(plan, poster):
    p = []; sl = plan.get("slides") or []
    lo, hi = (1, 1) if poster else (4, 8)
    if not lo <= len(sl) <= hi: p.append(f"{len(sl)} slides; write {lo if poster else '6'}")
    for x in sl:
        if not (x.get("brief") or "").strip() or not x.get("texts"): p.append(f"slide {x.get('n')}: needs its brief and its exact strings")
    if not (plan.get("caption") or "").strip(): p.append("the caption is empty")
    return p


def write_carousel(it, facts, feedback=""):
    b = BRANDS[it["brand"]]; poster = it["kind"] == "poster"
    prompt = (llm.fill((PROMPTS / "carousel.md").read_text(), rules=rules(), today=today(), slides="1" if poster else "6",
                                 format_note=("This is a POSTER: ONE slide that is the whole post — the hook headline, the key number or result, "
                                              "one real photo if a person/place is the story, and small \"Follow @" + b["handle"] + "\" at the bottom. "
                                              "No slide counter, no \"swipe\".") if poster else "", brand_name=b["name"],
                                 focus=b["focus"], image_style=b["image_style"].format(mmdd=mmdd()), research=json.dumps(facts, ensure_ascii=False, indent=1),
                                 handle=b["handle"], avoid=others(it), feedback=feedback,
                                 no_faces_note="- The image model never draws people or faces; real people appear only through the real photos you list."))
    prompt = owner_call(it, prompt); probs = ["the writer kept declining"]
    for attempt in range(3):
        plan = llm.ask_json(prompt)
        if plan.get("cannot"): prompt = cannot(it, plan, prompt); continue
        probs = check_carousel(plan, poster)
        if not probs: return plan
        prompt += "\n\n## Your last reply broke these rules — fix them and reply again with the full JSON\n" + "\n".join(f"- {x}" for x in probs)
        db.log(it["id"], f"slide writer draft {attempt + 1} invalid: {'; '.join(probs)[:400]}", "warn")
    raise RuntimeError("the slide writer could not produce a valid plan: " + "; ".join(probs))


def slides_view(plan):
    return "\n".join(f"Slide {s['n']} ({s.get('role', '')}): {s['brief']}\n  exact strings: {s.get('texts')}" for s in plan["slides"])


def crop45(src, dest):
    """Any generated shape -> a 1080x1350 slide. Taller than 4:5: centre crop. Wider (e.g. square): fit the whole design and fill
    above/below with a blurred, darkened copy (never crop off text)."""
    from PIL import ImageFilter
    im = Image.open(src).convert("RGB"); w, h = im.size
    if h / w >= 1.25:
        ch = round(w * 5 / 4); y = (h - ch) // 2
        im.crop((0, y, w, y + ch)).resize((1080, 1350), Image.LANCZOS).save(dest, quality=92, subsampling=0); return
    fg = im.resize((1080, round(h * 1080 / w)), Image.LANCZOS)
    bg = im.resize((round(w * 1350 / h), 1350)).crop((0, 0, 1080, 1350)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", bg.size, "black"), 0.4); bg.paste(fg, (0, (1350 - fg.height) // 2))
    bg.save(dest, quality=92, subsampling=0)


LIKENESS = ("The owner has allowed an AI illustration of the real people named in this brief: draw them as a bold poster "
            "illustration of the real event described here only — no invented actions, products, endorsements or places — and never "
            "label it a photo (no \"photo\", \"archive\" or credit text).")


def likeness_ok(it):
    """Owner switch: this item (studio draw-people ID) or this brand (studio draw-people --brand B on)."""
    return bool(it.get("likeness")) or it["brand"] in (db.setting("likeness_brands", []) or [])


def make_carousel(it, d, facts):
    b = BRANDS[it["brand"]]; rounds = 0; plan = write_carousel(it, facts)
    while True:
        verdicts = run_committee(it, facts, slides_view(plan), caption_text(plan, False), ["fact", "voice", "safety"])
        decision, issues = committee.chair(verdicts); db.log(it["id"], f"slide committee round {rounds + 1}: {committee.badge(verdicts)}")
        for i in issues: db.log(it["id"], f"  [{i.get('role')}] {i.get('where', '')}: {i.get('problem', '')}"[:400], "note")
        if decision == "pass": break
        why = "; ".join(i.get("problem", "") for i in issues)[:600]
        if decision == "block":
            gate(it, "committee blocked the slides: " + why, {"script": slides_view(plan), "caption": caption_text(plan, False)}); break
        rounds += 1
        if rounds > MAX_FIX_ROUNDS:
            if all(i.get("role") == "voice" for i in issues):   # style notes only: made, then it waits for the owner's call
                db.log(it["id"], "only style notes left after the fixes: making it; the owner decides", "warn"); break
            gate(it, "committee still unhappy after fixes: " + why, {"script": slides_view(plan), "caption": caption_text(plan, False)}); break
        plan = write_carousel(it, facts, committee.feedback(issues, plan))
    if likeness_ok(it): plan["ai_illustration"] = True
    keep_cta(it, d, plan, facts)
    (d / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    credits, logo_file = [], {}
    (d / "assets").mkdir(exist_ok=True)
    for a in plan.get("assets", []):
        if a.get("kind") == "logo":
            dest = d / "assets" / a["file"]; rec = assets.logo(a["entity"], dest, a.get("official_site"), it["id"])
            if rec: credits.append({k: rec.get(k) for k in ("id", "title", "source_page", "licence", "credit")}); logo_file[a["entity"]] = dest
    (d / "CREDITS.json").write_text(json.dumps(credits, indent=1, ensure_ascii=False))
    board = ASSETS / b["board"]; n = len(plan["slides"]); style = b["image_style"].format(mmdd=mmdd())

    photo_file = {}
    for s_ in plan["slides"]:
        for ph in s_.get("photos", [])[:1]:
            dest = d / "assets" / f"photo-s{s_['n']}.jpg"
            try:
                rec = assets.photo(ph.get("query", ""), dest, ph.get("entity"), it["id"])
                if rec:
                    photo_file[s_["n"]] = (dest, ph.get("query", ""))
                    if rec.get("credit"): plan.setdefault("photo_credits", []).append(rec["credit"])
            except Exception as e:
                db.log(it["id"], f"slide {s_['n']} photo failed: {e}", "warn")

    def one(s, note=""):
        logos = [e for e in s.get("logos", []) if e in logo_file][:3]
        refs = [board] + [logo_file[e] for e in logos]
        ref_note = " ".join(f"Image {k + 2} is the official {e} logo." for k, e in enumerate(logos))
        if s.get("photos") and s["n"] not in photo_file and not likeness_ok(it):   # no licensed photo: never let the model draw a person
            ref_note += (" IMPORTANT: no photo is available for this slide. Do NOT draw, paint or depict any real person or face; fill that "
                         "space with typography, numbers, the scoreboard and graphic motifs instead, and do not write \"photo\" anywhere.")
        if s["n"] in photo_file:
            refs.append(photo_file[s["n"]][0])
            ref_note += (f" Image {len(refs)} is a real photo ({photo_file[s['n']][1]}): place it in the layout as a photo, unaltered "
                         "(crop allowed, no redrawing, no filters on faces).")
        counter = "" if n == 1 else f"Slide counter \"{s['n']}/{n}\" small in the bottom-right corner. "
        brief = (f"Design a finished Instagram {'poster' if n == 1 else 'carousel slide'} for a {b['beat']} account. {style} {counter}"
                 f"{POST} {BOARD_NOTE} {ref_note} {s['brief']} "
                 f"{IMG_RULES.replace(IMG_RULES.split('. ')[0] + '. ', LIKENESS + ' ') if likeness_ok(it) else IMG_RULES} {note}")
        raw = d / "slides" / f"slide-{s['n']:02d}.png"
        if note and raw.exists(): raw.unlink()
        assets.codex_image(raw, brief, refs)
        crop45(raw, d / "slides" / f"slide-{s['n']:02d}.jpg")
    (d / "slides").mkdir(exist_ok=True)
    with ThreadPoolExecutor(3) as ex: list(ex.map(one, plan["slides"]))
    for rnd in range(MAX_FIX_ROUNDS + 1):
        jpgs = [d / "slides" / f"slide-{s['n']:02d}.jpg" for s in plan["slides"]]
        edit = run_committee(it, facts, slides_view(plan), caption_text(plan, False), ["edit"],
                             extra=f"The attached images are slides 1 to {n} in order." + (
                                 " The OWNER HAS ALLOWED an AI illustration of the real people in this post (labelled 'Illustration: "
                                 "AI-generated.' in the caption): a drawn likeness is correct here; flag it only if it is called a "
                                 "photo, shows an invented action, or looks like an endorsement." if likeness_ok(it) else ""), images=jpgs)[0]
        db.log(it["id"], f"slide picture round {rnd + 1}: {committee.badge([edit])} {edit.get('summary', '')[:200]}")
        if edit["verdict"] == "pass": break
        if edit["verdict"] == "block":
            gate(it, "slide editor: " + edit.get("summary", ""), {"files": [str(j) for j in jpgs], "caption": caption_text(plan, False)}); break
        if rnd == MAX_FIX_ROUNDS: break   # small notes left: the owner decides (it waits in "Needs you" with the slides)
        bad = {int(m) for i in edit.get("issues", []) for m in re.findall(r"slide\s*(\d+)", i.get("where", ""), re.I)} or {s["n"] for s in plan["slides"]}
        fixes = " ".join(f"Fix: {i.get('problem')} -> {i.get('fix')}." for i in edit.get("issues", []))
        with ThreadPoolExecutor(3) as ex: list(ex.map(lambda s: one(s, fixes), [s for s in plan["slides"] if s["n"] in bad]))
    files, extra = jpgs, []
    if it["kind"] == "carousel" and (db.get(it["id"]).get("motion") or it.get("motion")) == "animated":   # the owner may flip it mid-make
        files, extra = animate_slides(it, d, plan, jpgs, facts)
    return files, verdicts + [edit] + extra, caption_text(plan, False)


def plate45(plate_raw, raw, design, dest):
    """The empty plate cut exactly like its design (crop45). Where crop45 filled a band with a blur of the design, the band is
    taken from the design: it is not an element."""
    p = animate.fit_plate(plate_raw, raw)
    if p is None: return None
    full = pathlib.Path(dest).with_suffix(".fit.png"); p.save(full); crop45(full, dest)
    w, h = Image.open(raw).size
    if h / w < 1.25:
        fgh = round(h * 1080 / w); y = (1350 - fgh) // 2
        a, b = Image.open(design).convert("RGB"), Image.open(dest).convert("RGB")
        b.paste(a.crop((0, 0, 1080, y)), (0, 0)); b.paste(a.crop((0, y + fgh, 1080, 1350)), (0, y + fgh)); b.save(dest, quality=95)
    return dest


def animate_slides(it, d, plan, jpgs, facts, only=None):
    """Animated carousel: each approved slide (or only the slide numbers in `only`) becomes a 6 s clip built from its own design
    (animate.py). A slide whose plate or motion fails, or looks broken to the picture editor, goes out as its still image, so
    the carousel can mix both."""
    sd = d / "slides"
    pick = [k for k in range(len(jpgs)) if only is None or k + 1 in only]

    def plate(j):
        raw, praw, pj = j.with_suffix(".png"), sd / f"{j.stem}.plate.png", sd / f"{j.stem}.plate.jpg"
        try:
            if pj.exists(): return pj
            assets.codex_image(praw, animate.PLATE, [raw], size=animate.plate_size(raw))
            return plate45(praw, raw, j, pj)
        except Exception as e:
            db.log(it["id"], f"{j.stem}: no empty plate ({e}); whole-slide entrance", "warn"); return None
    with ThreadPoolExecutor(3) as ex: plates = dict(zip(pick, ex.map(plate, [jpgs[k] for k in pick])))
    clips = {}
    with CPU["render"]:
        for k in pick:
            j, pl = jpgs[k], plates[k]
            try:
                mp4, how = animate.make_clip(j, pl, it["brand"], sd / f"{j.stem}.mp4", cover=(k == 0), seed=it["id"] * 10 + k)
                clips[k + 1] = mp4; db.log(it["id"], f"{j.stem}: animated ({how})")
            except Exception as e:
                db.log(it["id"], f"{j.stem}: animation failed ({e}); still image", "warn")
    note = "motion: none (all still)"
    if clips:
        sheet = animate.sheet(sorted(clips.items()), sd / "motion-sheet.jpg")
        v = run_committee(it, facts, slides_view(plan), caption_text(plan, False), ["edit"], extra=animate.CHECK, images=[sheet])[0]
        broken = {int(m) for i in v.get("issues", []) for m in re.findall(r"slide\s*(\d+)", i.get("where", ""), re.I)}
        if v["verdict"] != "pass" and not broken: broken = set(clips)   # something looks off but nobody said where: play safe
        for n in broken: clips.pop(n, None)
        db.log(it["id"], f"motion check: {v['verdict']} {v.get('summary', '')[:200]}" + (f" — still: slides {sorted(broken)}" if broken else ""))
        note = f"motion ✓ {len(clips)}/{len(jpgs)} animated" if clips else "motion: still (the animation looked off)"
    files = [clips.get(k + 1, j) for k, j in enumerate(jpgs)]
    return files, [{"role": "motion", "verdict": "pass" if clips else "fix", "summary": note}]


def animate_existing(item_id):
    """The owner asked to animate a finished carousel — all its slides, or only the ones named (setting motion_slides:<id>):
    animate those approved slides (no re-design, no re-review of the words), keep every other slide exactly as it is now, keep
    its slot, preview on Telegram. It is held as 'making' meanwhile so the old version can't post."""
    it = db.get(item_id); b = BRANDS[it["brand"]]
    only = db.setting(f"motion_slides:{item_id}")
    prev = db.setting(f"motion_prev:{item_id}") or it["status"]
    if prev == "making": prev = "ready"
    db.set_setting(f"motion_prev:{item_id}", prev); db.update(item_id, status="making")
    try:
        d = pathlib.Path(it["dir"]); plan = json.loads((d / "plan.json").read_text())
        jpgs = [d / "slides" / f"slide-{s['n']:02d}.jpg" for s in plan["slides"]]
        now_files = [MEDIA / u.split("/m/", 1)[1] for u in json.loads(it.get("media") or "[]")]
        files, extra = animate_slides(it, d, plan, jpgs, json.loads(it.get("facts") or "[]"), only=set(only) if only else None)
        if only and len(now_files) == len(files):   # untouched slides stay exactly as they were (still, or animated before)
            files = [files[k] if k + 1 in only and str(files[k]).endswith(".mp4") else now_files[k] for k in range(len(files))]
        urls = publish_copy(it, files)
        review = [v for v in json.loads(it.get("review") or "[]") if v.get("role") != "motion"] + extra
        final = "held" if db.get(item_id)["status"] == "held" else prev   # the owner may have held it meanwhile
        db.update(item_id, status=final, media=urls, review=review); db.log(item_id, f"animated: {extra[0]['summary']}")
        tg.notify(f"#{item_id} {b['name']} carousel — animation done ({extra[0]['summary']})", item_id, "done")
        return True
    except Exception as e:
        db.update(item_id, status="held" if db.get(item_id)["status"] == "held" else prev); db.log(item_id, f"animate failed: {e}", "error")
        tg.notify(f"#{item_id}: couldn't animate it ({str(e)[:80]}); it stays still", item_id, "failed")
        return False
    finally:
        db.set_setting(f"motion_prev:{item_id}", None); db.set_setting(f"motion_slides:{item_id}", None)


# ---------------------------------------------------------------- news carousel (real official images)
NEWS_EDIT = ("These are NEWS carousel slides: the real official images are placed unaltered by code (they may show the product's "
             "own UI, HUD numbers, titles or logos — that is correct, not ours to fix); every word on the dark panels is designed. "
             "Check the designed text: every quoted string exact and readable, nothing cut off or overlapping; the seam between image "
             "and panel looks clean; the cover's headline colours and the round logo badge (the official logo, correct entity); no "
             "face cropped awkwardly; the images match what the slide says.")


def write_news(it, facts, gallery, feedback=""):
    b = BRANDS[it["brand"]]
    pics = "\n".join(f"- id {g['id']}: {g['kind']}, {g['what']} ({g['w']}x{g['h']}{', text_heavy' if g.get('text_heavy') else ''}; {g['owner']})"
                      for g in gallery)
    prompt = llm.fill((PROMPTS / "news-carousel.md").read_text(), rules=rules(), today=today(), brand_name=b["name"], focus=b["focus"],
                      research=json.dumps(facts, ensure_ascii=False, indent=1), gallery=pics, handle=b["handle"], avoid=others(it), feedback=feedback)
    prompt = owner_call(it, prompt); probs = ["the writer kept declining"]
    for attempt in range(3):
        plan = llm.ask_json(prompt)
        if plan.get("cannot"): prompt = cannot(it, plan, prompt); continue
        probs = newsdeck.check(plan, gallery)
        if not probs: return plan
        prompt += "\n\n## Your last reply broke these rules — fix them and reply again with the full JSON\n" + "\n".join(f"- {x}" for x in probs)
        db.log(it["id"], f"news writer draft {attempt + 1} invalid: {'; '.join(probs)[:400]}", "warn")
    raise RuntimeError("the news writer could not produce a valid plan: " + "; ".join(probs))


def make_news_carousel(it, d, facts, gallery):
    b = BRANDS[it["brand"]]; rounds = 0; plan = write_news(it, facts, gallery)
    while True:
        verdicts = run_committee(it, facts, newsdeck.view(plan, gallery), caption_text(plan, False), ["fact", "voice", "safety"])
        decision, issues = committee.chair(verdicts); db.log(it["id"], f"news committee round {rounds + 1}: {committee.badge(verdicts)}")
        for i in issues: db.log(it["id"], f"  [{i.get('role')}] {i.get('where', '')}: {i.get('problem', '')}"[:400], "note")
        if decision == "pass": break
        why = "; ".join(i.get("problem", "") for i in issues)[:600]
        if decision == "block":
            gate(it, "committee blocked the slides: " + why, {"script": newsdeck.view(plan, gallery), "caption": caption_text(plan, False)}); break
        rounds += 1
        if rounds > MAX_FIX_ROUNDS:
            if all(i.get("role") == "voice" for i in issues):   # style notes only: made, then it waits for the owner's call
                db.log(it["id"], "only style notes left after the fixes: making it; the owner decides", "warn"); break
            gate(it, "committee still unhappy after fixes: " + why, {"script": newsdeck.view(plan, gallery), "caption": caption_text(plan, False)}); break
        plan = write_news(it, facts, gallery, committee.feedback(issues, plan))
    used = {i for s in plan["slides"] for i in ([s.get("image")] if s.get("image") is not None else []) + list(s.get("images") or [])}
    plan["image_credits"] = sorted({g["owner"] for g in gallery if g["id"] in used and g.get("owner")})
    keep_cta(it, d, plan, facts)
    (d / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False)); (d / "gallery.json").write_text(json.dumps(gallery, indent=1))
    logo_file = None; cover = plan["slides"][0]
    if cover.get("logo"):
        e = next((x for x in facts.get("entities", []) if x.get("name") == cover["logo"]), {})
        (d / "assets").mkdir(exist_ok=True); dest = d / "assets" / f"logo-{assets.slug(cover['logo'])}.png"
        try:
            if assets.logo(cover["logo"], dest, e.get("official_site"), it["id"]): logo_file = dest
        except Exception as ex:
            db.log(it["id"], f"cover logo failed: {ex}", "warn")
    sd = d / "slides"; jpgs = newsdeck.build(plan, it["brand"], b["handle"], gallery, logo_file, sd)
    for rnd in range(MAX_FIX_ROUNDS + 1):
        edit = run_committee(it, facts, newsdeck.view(plan, gallery), caption_text(plan, False), ["edit"],
                             extra=NEWS_EDIT + f" The attached images are slides 1 to {len(jpgs)} in order.", images=jpgs)[0]
        db.log(it["id"], f"news picture round {rnd + 1}: {committee.badge([edit])} {edit.get('summary', '')[:200]}")
        if edit["verdict"] == "pass": break
        if edit["verdict"] == "block":
            gate(it, "slide editor: " + edit.get("summary", ""), {"files": [str(j) for j in jpgs], "caption": caption_text(plan, False)}); break
        if rnd == MAX_FIX_ROUNDS: break   # small notes left: the owner decides (it waits in "Needs you" with the slides)
        bad = {int(m) for i in edit.get("issues", []) for m in re.findall(r"slide\s*(\d+)", i.get("where", ""), re.I)} or {s["n"] for s in plan["slides"]}
        bad = {s["n"] for s in plan["slides"] if s["n"] in bad and s["type"] != "images"}   # image-only slides have nothing designed to fix
        if not bad: break
        fixes = " ".join(f"Fix: {i.get('problem')} -> {i.get('fix')}." for i in edit.get("issues", []))
        jpgs = newsdeck.build(plan, it["brand"], b["handle"], gallery, logo_file, sd, fixes=fixes, only=bad)
    return jpgs, verdicts + [edit], caption_text(plan, False)


def carousel_look(it, facts):
    """News (real official images) or designed. The owner's choice wins; otherwise news whenever the story's official pages give
    at least three usable images. Returns (look, gallery)."""
    want = it.get("look")
    if want == "designed" or it["kind"] != "carousel": return "designed", []
    try:
        gallery = assets.official_gallery(facts, it["id"])
    except Exception as e:
        db.log(it["id"], f"official gallery failed: {e}", "warn"); gallery = []
    usable = [g for g in gallery if not g.get("text_heavy")]
    look = "news" if len(gallery) >= 3 and usable else "designed"
    if want == "news" and look != "news": db.log(it["id"], f"only {len(gallery)} official images found: designed slides instead", "warn")
    db.log(it["id"], f"carousel look: {look} ({len(gallery)} official images)")
    return look, gallery


# ---------------------------------------------------------------- entry points
def publish_copy(it, files):
    """Copy the post's files into media/<id>-<random>/ (served publicly by Caddy) and return their URLs."""
    folder = MEDIA / f"{it['id']:05d}-{secrets.token_hex(4)}"; folder.mkdir(parents=True, exist_ok=True)
    urls = []
    for f in files:
        dst = folder / pathlib.Path(f).name; shutil.copy(f, dst); dst.chmod(0o644)
        urls.append(f"{PUBLIC}/m/{folder.name}/{dst.name}")
    folder.chmod(0o755)
    return urls


def make(item_id):
    it = db.get(item_id); b = BRANDS[it["brand"]]
    d = WORK / f"item-{item_id:05d}"; d.mkdir(parents=True, exist_ok=True)
    db.update(item_id, status="making", dir=str(d), attempts=(it["attempts"] or 0) + 1, error=None)
    db.log(item_id, f"making {it['brand']} {it['kind']}: {it['topic']}")
    try:
        if it["kind"] == "carousel" and it.get("motion") not in ("animated", "static"):
            db.update(item_id, motion=db.pick_motion(it["brand"]))
        facts = research(it, d); it = db.get(item_id)
        if it["kind"] in ("reel", "story"):
            mp4, verdicts, cap = make_kinetic(it, d, facts); files = [mp4]
        else:
            look, gallery = carousel_look(it, facts)
            if look == "news":
                db.update(item_id, look="news", motion="static"); it = db.get(item_id)   # news slides are stills (real images)
                files, verdicts, cap = make_news_carousel(it, d, facts, gallery)
            else:
                if it["kind"] == "carousel": db.update(item_id, look="designed")
                files, verdicts, cap = make_carousel(it, d, facts)
        urls = publish_copy(it, files)
        if (d / "cta.json").exists(): db.update(item_id, cta=(d / "cta.json").read_text())
        now_it = db.get(item_id)   # the owner may have held it (or asked to post on ready) while it was being made
        try:
            ents = [int(x["dst"].split(":")[1]) for x in graph.rows("SELECT dst FROM edges WHERE src=? AND rel='about'", (f"item:{item_id}",))]
            for f in files:
                a = graph.add_asset(f, ("video" if it["kind"] in ("reel", "story") else "slide-video") if str(f).endswith(".mp4") else "slide",
                                    ents, title=f"#{item_id} {it['topic']}", copy=False)
                graph.used(a["id"], item_id)
        except Exception as e:
            db.log(item_id, f"graph: could not register media: {e}", "warn")
        notes = "; ".join(f"{v['role']}: {v.get('summary', '')}" for v in verdicts if v.get("role") in ("edit", "voice") and v.get("verdict") != "pass")[:600]
        if now_it["status"] == "held" or (now_it.get("override") and not now_it.get("autopost")):
            status, when = "held", "waits for you — say 'post " + str(item_id) + " now'"
        elif notes and not now_it.get("autopost"):
            status, when = "held", f"waits for you — the reviewers left small notes; 'post {item_id}' posts it as is, 'retry {item_id}' re-makes it"
        elif now_it.get("autopost"):
            status, when = "approved", "now (you asked to post it when ready)"
            db.update(item_id, slot=db.iso(db.now()))
        else:
            status, when = "ready", now_it["slot"] or "when you say"
        preview = db.now() - db.dt.timedelta(minutes=VETO_MIN) if status == "approved" else db.now()
        db.update(item_id, status=status, media=urls, caption=cap, review=verdicts, facts=facts, preview_at=db.iso(preview),
                  error=("reviewer notes: " + notes) if notes else None)
        db.log(item_id, f"{status}: {committee.badge(verdicts)}")
        kind = "animated carousel" if it["kind"] == "carousel" and any(str(f).endswith(".mp4") for f in files) else it["kind"]
        head = (f"#{item_id} {b['name']} {kind} made — {it['topic']}\nPosts: {when}\n"
                f"Committee: {committee.badge(verdicts)}\n" + "".join(v["summary"] + "\n" for v in verdicts if v.get("role") == "motion") +
                (f"⚠️ Notes for you: {notes[:300]}\n" if notes else "") +
                f"Say 'hold {item_id}' to stop it or 'post {item_id} now'." +
                (f"\n✅ Approve here: {PUBLIC}/dash/approve.html" if status == "held" else "") + f"\n\n{cap[:600]}")
        if status == "held" or (status == "ready" and not now_it.get("slot")):   # only what needs the owner reaches Telegram
            tg.notify(f"#{item_id} {b['name']} {kind} waits for your OK — {(it['topic'] or '')[:60]}", item_id, "needs")
        return True
    except Rejected as e:
        db.update(item_id, status="rejected", error=str(e)[:1500]); db.log(item_id, f"rejected: {e}", "warn")
        dr = json.loads(db.get(item_id).get("draft") or "{}")
        head = (f"⛔ #{item_id} {b['name']} {it['kind']} — the committee said no:\n{str(e)[:600]}\n\n"
                f"Reply \"override {item_id}\" to post it anyway, \"retry {item_id}\" for a fresh attempt, or give me a new angle.\n"
                f"Or decide here: {PUBLIC}/dash/approve.html")
        tg.notify(f"#{item_id} {b['name']} {it['kind']}: the committee said no — {str(e)[:90]}", item_id, "no")
        return False
    except Exception as e:
        db.update(item_id, status="failed", error=f"{type(e).__name__}: {e}"[:1500]); db.log(item_id, f"failed: {e}", "error")
        tg.notify(f"#{item_id} {b['name']} {it['kind']} failed to make — {str(e)[:90]}", item_id, "failed")
        return False
