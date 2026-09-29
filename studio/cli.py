"""studio — the Instagram studio's control panel. Hermes drives it from Telegram; systemd runs `tick` and `worker`.

  studio status                          what's paused, due, making, ready, failed
  studio pause [2h|3d|45m|off] [reason]  stop all posting and making (auto-resumes after the time; default 24h)
  studio resume
  studio plan  [--brands all] [--days 7] [--topic T] [--start YYYY-MM-DD] [--reel N --carousel N --story N] [--request TEXT] [--dry-run]
  studio add   BRAND KIND "topic" [--at "YYYY-MM-DD HH:MM" | --asap] [--angle A] [--notes N] [--source URL] [--animated|--still] [--news|--designed]
  studio suggest BRAND KIND "topic" [--angle A] [--source URL] [--why W]   Hermes' idea, waits for the owner's yes
  studio accept ID [--at T | --asap] | studio decline ID
  studio list  [--brand B] [--status S] [--days N] [--all]
  studio show  ID
  studio make  ID                        queue it now (the worker makes it)
  studio approve ID | hold ID | release ID | retry ID | remove ID
  studio override ID                     the owner overrules the committee (posts the rejected draft, or re-makes without veto)
  studio move  ID "YYYY-MM-DD HH:MM"
  studio post ID --when-ready            post the moment it's made (you still get the preview)
  studio prepare [--days 7] [--brand B] [--all]   make booked posts now instead of 14 h before (news slots only with --all)
  studio slots [KIND HH:MM,HH:MM] [--apply]        posting times; --apply re-times booked items
  studio draw-people ID [on|off] | studio draw-people --brand B on|off   owner switch: AI-drawn real people (captioned)
  studio motion ID animated|still|auto [--slides 2,4]   one carousel: animate all its slides or just some (a finished one is
                                         switched in place); carousels are still unless the owner asks
  studio motion --share 50               how many new carousels are animated (percent; the rest are still) — default 50
  studio today N [--brands all|a,b] [--from HH:MM] [--until HH:MM] [--day YYYY-MM-DD]   N extra posts TODAY across the accounts:
                                         fresh stories scouted now, made now, spread over the rest of the day
  studio priority ID top|high|normal|low  where a post sits in the making queue (top = made next); studio queue shows the order
  studio scout [--brand all|B] [--topic T] [--n 5]   find fresh ideas now (web search) and pitch them — nothing is made until "yes N"
  studio import FILE BRAND [--kind reel|story|poster] --caption 'TEXT' [--topic T] [--post | --at T] [--notes N]
                                         post a finished file (the owner's own or authorised video/image) as it is
  studio cta ID [KEYWORD 'DM text' [--offer 'the links'] | off]   comment KEYWORD -> we DM them (one DM per comment, 7 days)
  studio look ID news|designed|auto      one carousel: real official images (news) or Codex-designed slides (auto: news when the
                                         story's official pages give 3+ usable images)
  studio share ID --as story [--slide N] [--at T]  reuse a finished post as a story instantly (no re-make, no re-review)
  studio post  ID                        publish now (still refuses while paused or unreviewed)
  studio mode  [veto|auto|manual]        approval mode (default veto: preview first, posts unless held)
  studio cadence [BRAND --reel N --carousel N --story N]
  studio media find TEXT | about NAME | stats | graph          the knowledge graph (entities, images, facts, posts)
  studio media add FILE --kind logo|press|photo|object --entity NAME --source URL --licence L [--author A] [--title T]
  studio media import manifest.json | studio media remove ASSET_ID   (a wrong image: gone from the graph)
  studio log   [ID] [-n 30]
  studio check                           accounts, tokens, quota, disk, services
  studio dash                            rebuild the live dashboard (https://studio.example.com/dash/, every minute by timer)
  studio tick | studio worker            (systemd)
"""
import argparse, json, os, pathlib, re, shutil, subprocess, sys, time
import datetime as dt
from . import db, tg
from .config import BRANDS, CADENCE, LEAD_HOURS, OFFSET_MIN, SLOTS, VETO_MIN, PROMPTS, ROOT, PUBLIC

KINDS = ("reel", "carousel", "story", "poster")
LIVE = ("idea", "queued", "making", "ready", "approved", "held", "publishing")


def when(s):
    t = dt.datetime.fromisoformat(s.replace(" ", "T"))
    return t if t.tzinfo else t.replace(tzinfo=db.IST)


def dur(s):
    m = re.fullmatch(r"(\d+)\s*([mhdw])", s.strip().lower())
    if not m: raise SystemExit(f"duration like 45m, 2h, 3d, 1w — got {s!r}")
    unit = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}[m.group(2)]
    return dt.timedelta(**{unit: int(m.group(1))})


def mode():
    return db.setting("mode", "veto")


def cadence(brand):
    return (db.setting("cadence", {}) or {}).get(brand, CADENCE[brand])


def short(it):
    slot = db.parse(it["slot"]).strftime("%a %d %b %H:%M") if it["slot"] else "unscheduled"
    tag = ("[news] " if it.get("look") == "news" else {"animated": "[animated] ", "static": "[still] "}.get(it.get("motion"), "")) \
        if it["kind"] == "carousel" else ""
    return f"#{it['id']:<4} {slot:<16} {BRANDS[it['brand']]['name']:<10} {it['kind']:<8} {it['status']:<10} {tag}{(it['topic'] or '')[:48]}"


# ---------------------------------------------------------------- commands
def c_status(a):
    p, until, why = db.paused()
    lines = [f"PAUSED until {until.strftime('%a %d %b %H:%M') if until else 'you resume'}{' — ' + why if why else ''}" if p else "Running.",
             f"Approval mode: {mode()}"]
    now = db.now(); day = now + dt.timedelta(hours=24)
    soon = db.items("status IN ('idea','queued','making','ready','approved','held') AND slot <= ?", (db.iso(day),))
    lines.append(f"Next 24 h ({len(soon)}):"); lines += ["  " + short(i) for i in soon] or ["  nothing scheduled"]
    busy = db.items("status IN ('queued','making')")
    if busy: lines.append("Making now / queued:"); lines += ["  " + short(i) for i in busy]
    bad = db.items("status IN ('failed','rejected') AND updated >= ?", (db.iso(now - dt.timedelta(days=2)),))
    if bad: lines.append("Needs attention:"); lines += [f"  {short(i)} — {(i['error'] or '')[:90]}" for i in bad]
    pub = db.items("status='published' AND updated >= ?", (db.iso(now - dt.timedelta(hours=24)),))
    if pub: lines.append("Published in the last 24 h:"); lines += [f"  #{i['id']} {BRANDS[i['brand']]['name']} {i['kind']} {i['permalink'] or ''}" for i in pub]
    print("\n".join(lines))


def c_pause(a):
    arg = " ".join(a.args).strip()
    if arg in ("off", "resume"): return c_resume(a)
    m = re.match(r"(\d+\s*[mhdw])?\s*(.*)", arg); span = dur(m.group(1)) if m.group(1) else dt.timedelta(hours=24)
    until = db.now() + span; db.set_setting("pause", {"until": db.iso(until), "reason": m.group(2)})
    db.log(None, f"paused until {db.iso(until)} {m.group(2)}")
    print(f"Paused. Nothing will be made or posted until {until.strftime('%a %d %b %H:%M')} IST. Say /unfreeze to restart earlier.")


def c_resume(a):
    db.set_setting("pause", None); db.log(None, "resumed by owner"); print("Resumed. Scheduled posts will go out from the next check (every 5 min).")


def slots():
    return {**SLOTS, **(db.setting("slots", {}) or {})}


def slots_for(brand, day, kinds):
    out = []; S = slots()
    for k in KINDS:
        n = kinds.get(k, 0)
        for j in range(n):
            base = S[k][j % len(S[k])]
            hh, mm = map(int, base.split(":")); t = day.replace(hour=hh, minute=mm, second=0) + dt.timedelta(minutes=OFFSET_MIN[brand] + 90 * (j // len(S[k])))
            out.append((k, t))
    return out


def c_plan(a):
    brands = list(BRANDS) if a.brands in ("all", None) else a.brands.split(",")
    start = when(a.start) if a.start else (db.now() + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = []
    for di in range(a.days):
        day = start + dt.timedelta(days=di)
        for br in brands:
            kinds = dict(cadence(br))
            for k in KINDS:
                if getattr(a, k) is not None: kinds[k] = getattr(a, k)
            for k, t in slots_for(br, day, kinds):
                if t > db.now() + dt.timedelta(minutes=30): rows.append({"brand": br, "kind": k, "slot": t})
    rows.sort(key=lambda r: r["slot"])
    if a.topic and rows:   # a campaign: one angle per slot, planned together so the week never repeats itself
        from . import llm
        from .pipeline import rules, today
        slots = "\n".join(f"{i}. {BRANDS[r['brand']]['name']} {r['kind']} {r['slot'].strftime('%a %d %b %H:%M')}" for i, r in enumerate(rows))
        res = llm.ask_json(llm.fill((PROMPTS / "plan.md").read_text(), rules=rules(), today=today(), request=a.request or a.topic, topic=a.topic, slots=slots,
                                    animated_share=f"about {round(db.setting('animated_share', 0.5) * 100)}%"), search=True)
        for s in res.get("slots", []):
            if 0 <= s.get("i", -1) < len(rows):
                rows[s["i"]].update(topic=s.get("topic"), angle=s.get("angle"))
                if rows[s["i"]]["kind"] == "carousel" and s.get("motion") in ("animated", "static") and db.setting("animated_share", 0) > 0:
                    rows[s["i"]]["motion"] = s["motion"]
        print(res.get("summary", ""))
    chosen = {}
    for r in rows:
        if r["kind"] != "carousel": continue
        r["motion"] = r.get("motion") or db.pick_motion(r["brand"], chosen.get(r["brand"], []))
        chosen.setdefault(r["brand"], []).append(r["motion"])
    per_day = {}
    for r in rows: per_day.setdefault(r["slot"].strftime("%a %d %b"), []).append(r)
    total = {k: sum(1 for r in rows if r["kind"] == k) for k in KINDS}
    print(f"Plan: {a.days} days from {start.strftime('%a %d %b')}, brands {', '.join(BRANDS[b]['name'] for b in brands)} — "
          f"{total['reel']} reels, {total['carousel']} carousels ({sum(1 for r in rows if r.get('motion') == 'animated')} animated), {total['story']} stories")
    for day, rs in per_day.items():
        print(f"\n{day}")
        for r in rs: print(f"  {r['slot'].strftime('%H:%M')} {BRANDS[r['brand']]['name']:<10} {r['kind']:<8} "
                           f"{'[' + {'animated': 'animated', 'static': 'still'}[r['motion']] + '] ' if r.get('motion') else ''}{r.get('topic') or 'auto (freshest story that day)'}"
                           f"{' — ' + r['angle'] if r.get('angle') else ''}")
    if a.dry_run: print("\n(dry run — nothing saved. Run again without --dry-run to book it.)"); return
    with db.conn() as c:
        pid = c.execute("INSERT INTO plans(request,brands,start,days,cadence,created) VALUES(?,?,?,?,?,?)",
                        (a.request or a.topic or "", ",".join(brands), db.iso(start), a.days, json.dumps({b: cadence(b) for b in brands}), db.iso(db.now()))).lastrowid
    for r in rows:
        i = db.add(r["brand"], r["kind"], r.get("topic") or "auto", r["slot"], r.get("angle") or "", "", pid, a.request or "")
        if r.get("motion"): db.update(i, motion=r["motion"])
    print(f"\nBooked plan #{pid}: {len(rows)} items. Each is made ~{LEAD_HOURS} h before its slot, reviewed by the committee, previewed here, then posted.")


def notes_of(a):
    n = a.notes or ""
    if getattr(a, "source", None): n += f"\nSource shared by the owner (open and read it first, then verify elsewhere): {a.source}"
    return n.strip()


def look_of(a):
    return "news" if getattr(a, "news", False) else "designed" if getattr(a, "designed", False) else None


def motion_of(a):
    return "animated" if getattr(a, "animated", False) else "static" if getattr(a, "still", False) else None


def c_add(a):
    if a.brand not in BRANDS: raise SystemExit(f"brand is one of {', '.join(BRANDS)}")
    if a.kind not in KINDS: raise SystemExit(f"kind is one of {', '.join(KINDS)}")
    slot = when(a.at) if a.at else None
    i = db.add(a.brand, a.kind, a.topic, slot, a.angle or "", notes_of(a), request=a.topic)
    if a.draw_people: db.update(i, likeness=1)
    if a.kind == "carousel": db.update(i, motion=motion_of(a) or db.pick_motion(a.brand), look=look_of(a))
    if a.asap or not slot:
        db.update(i, status="queued"); db.enqueue(i, priority=10)   # the owner asked: jumps the scheduled queue
        print(f"#{i} queued now: {BRANDS[a.brand]['name']} {a.kind} — {a.topic}. I'll send the preview when the committee passes it"
              f"{'' if slot else '; it posts when you say'}.")
    else:
        print(f"#{i} booked for {slot.strftime('%a %d %b %H:%M')}: {BRANDS[a.brand]['name']} {a.kind} — {a.topic}.")


def c_suggest(a):
    """Hermes' own idea, waiting for the owner's yes: it is not made or posted until accepted."""
    if a.brand not in BRANDS or a.kind not in KINDS: raise SystemExit(f"brand {list(BRANDS)}, kind {list(KINDS)}")
    dup = db.items("brand=? AND lower(topic)=lower(?) AND status NOT IN ('removed','declined')", (a.brand, a.topic))
    if dup: raise SystemExit(f"already in the library as #{dup[0]['id']} ({dup[0]['status']})")
    i = db.add(a.brand, a.kind, a.topic, None, a.angle or "", notes_of(a), request=f"suggested: {a.why or ''}")
    db.update(i, status="suggested"); db.log(i, f"suggested: {a.why or ''}")
    if a.kind == "carousel": db.update(i, motion=motion_of(a) or db.pick_motion(a.brand))
    print(f"#{i} suggested: {BRANDS[a.brand]['name']} {a.kind} — {a.topic}{' — ' + a.angle if a.angle else ''}")


def c_accept(a):
    it = db.get(a.id)
    if not it or it["status"] != "suggested": raise SystemExit(f"#{a.id} is not a pending suggestion")
    if a.at:
        db.update(a.id, status="idea", slot=db.iso(when(a.at))); print(f"#{a.id} accepted, booked for {when(a.at).strftime('%a %d %b %H:%M')}.")
    else:
        slot = db.now() + dt.timedelta(hours=1) if a.asap else None
        db.update(a.id, status="queued", slot=db.iso(slot)); db.enqueue(a.id, priority=10)
        print(f"#{a.id} accepted and queued now; preview comes when the committee passes it{'' if slot else '; it posts when you say'}.")


def c_decline(a):
    it = db.get(a.id)
    if not it or it["status"] != "suggested": raise SystemExit(f"#{a.id} is not a pending suggestion")
    db.update(a.id, status="declined"); print(f"#{a.id} dropped.")


def c_list(a):
    where, args = ["1=1"], []
    if not a.all: where.append("status NOT IN ('removed','declined')")
    if a.brand: where.append("brand=?"); args.append(a.brand)
    if a.status: where.append("status=?"); args.append(a.status)
    if a.days: where.append("(slot IS NULL OR slot <= ?)"); args.append(db.iso(db.now() + dt.timedelta(days=a.days)))
    if not a.all and not a.status: where.append("(status<>'published' OR updated >= ?)"); args.append(db.iso(db.now() - dt.timedelta(days=3)))
    rows = db.items(" AND ".join(where), tuple(args))
    print("\n".join(short(r) for r in rows) or "Library is empty for that filter.")


def c_show(a):
    it = db.get(a.id)
    if not it: raise SystemExit(f"no item #{a.id}")
    print(short(it))
    for k in ("angle", "notes", "request", "error", "permalink", "dir"):
        if it.get(k): print(f"{k}: {it[k]}")
    if it.get("review"):
        for v in json.loads(it["review"]): print(f"committee {v['role']}: {v['verdict']} — {v.get('summary', '')}")
    if it.get("media"): print("media:", ", ".join(json.loads(it["media"])))
    if it.get("caption"): print("\ncaption:\n" + it["caption"])
    with db.conn() as c:
        ev = c.execute("SELECT ts,level,msg FROM events WHERE item_id=? ORDER BY id DESC LIMIT 8", (a.id,)).fetchall()
    if ev: print("\nrecent:"); [print(f"  {e['ts']} {e['level']}: {e['msg'][:160]}") for e in reversed(ev)]


def set_status(i, status, allowed, msg):
    it = db.get(i)
    if not it: raise SystemExit(f"no item #{i}")
    if it["status"] not in allowed: raise SystemExit(f"#{i} is {it['status']}; can't {msg} it")
    if msg == "release" and not it.get("media"): status = "idea"   # held before it was made: back to the plan, not "ready"
    if msg == "approve" and (not it.get("slot") or db.parse(it["slot"]) <= db.now()): db.update(i, slot=db.iso(db.now()))   # no time: now
    db.update(i, status=status); db.log(i, f"owner: {msg}")
    slot = db.parse(it["slot"]).strftime("%a %d %b %H:%M") if it.get("slot") else None
    if msg == "release" and status == "ready":
        print(f"#{i} released: it posts as it is at {slot}." if slot else f"#{i} released: ready — it posts when you say 'post {i}'.")
    elif msg == "retry":
        print(f"#{i} retry: back to the plan; it is made again fresh (now if you say 'make {i}', else at its usual time).")
    else:
        print(f"#{i} {msg}: now {status}.")


def c_make(a):
    it = db.get(a.id)
    if not it: raise SystemExit(f"no item #{a.id}")
    if it["status"] in ("making", "publishing", "published"): raise SystemExit(f"#{a.id} is {it['status']}")
    db.update(a.id, status="queued"); db.enqueue(a.id, priority=10); print(f"#{a.id} queued for making (ahead of the scheduled week).")


def c_remove(a):
    it = db.get(a.id)
    if not it: raise SystemExit(f"no item #{a.id}")
    if it["status"] == "published":
        print(f"#{a.id} is already live on Instagram ({it['permalink'] or 'no link'}). Our Instagram-Login tokens can't delete posts; "
              "delete it in the Instagram app (••• → Delete). I've marked it removed in the library."); db.update(a.id, status="removed"); return
    if it["status"] in ("making", "publishing"): raise SystemExit(f"#{a.id} is {it['status']} right now; hold it first, or try again in a few minutes")
    db.update(a.id, status="removed"); db.log(a.id, "removed by owner"); print(f"#{a.id} removed from the schedule (kept in the library as removed).")


def c_move(a):
    it = db.get(a.id)
    if not it or it["status"] in ("published", "removed"): raise SystemExit(f"#{a.id} can't be moved")
    if when(a.at) < db.now() - dt.timedelta(minutes=5): raise SystemExit(f"{a.at} is in the past — pick a later time")
    db.update(a.id, slot=db.iso(when(a.at))); print(f"#{a.id} moved to {when(a.at).strftime('%a %d %b %H:%M')}.")


def publishable(it):
    return it["status"] == "approved" or (it["status"] == "ready" and mode() != "manual")


def do_publish(it):
    from . import igclient as ig
    b = BRANDS[it["brand"]]
    db.update(it["id"], status="publishing")
    try:
        mid, link = ig.publish(it["brand"], "image" if it["kind"] == "poster" else it["kind"], json.loads(it["media"]), it["caption"] or "")
        db.update(it["id"], status="published", ig_media_id=mid, permalink=link); db.log(it["id"], f"published {mid} {link}")
        pass   # live posts show on the dashboard; Telegram stays for the owner's asks
    except Exception as e:
        db.update(it["id"], status="failed", error=f"publish: {e}"[:1500]); db.log(it["id"], f"publish failed: {e}", "error")
        tg.notify(f"#{it['id']} {b['name']} {it['kind']} failed to post — {str(e)[:90]}", it["id"], "failed")


def c_override(a):
    """The owner overrules the committee. A rendered draft is posted as is; otherwise the item is re-made with the committee
    advising (it still fixes what it can) but unable to block."""
    it = db.get(a.id)
    if not it: raise SystemExit(f"no item #{a.id}")
    if it["status"] not in ("rejected", "failed", "held", "expired", "ready"): raise SystemExit(f"#{a.id} is {it['status']}; nothing to override")
    dr = json.loads(it.get("draft") or "{}")
    files = [f for f in dr.get("files", []) if pathlib.Path(f).exists()]
    if files:
        from .pipeline import publish_copy
        urls = publish_copy(it, files); now = db.now()
        slot = max(db.parse(it["slot"]), now) if it["slot"] else now
        db.update(a.id, status="approved", media=urls, caption=dr.get("caption") or it["caption"], slot=db.iso(slot), override=1,
                  preview_at=db.iso(now - dt.timedelta(minutes=VETO_MIN)), error=None)
        db.log(a.id, "owner override: posting the rejected draft")
        print(f"#{a.id} overridden: the draft you saw posts {'within 5 minutes' if slot <= now + dt.timedelta(minutes=5) else 'at ' + slot.strftime('%a %d %b %H:%M')}.")
    else:
        db.update(a.id, status="queued", override=1, error=None); db.enqueue(a.id, priority=10); db.log(a.id, "owner override: re-making without committee veto")
        print(f"#{a.id} overridden: re-making it now; the committee can suggest fixes but can't block it. It then waits for your 'post {a.id}'.")


def story_image(src, dest):
    """A 4:5 post image as a 9:16 story: the image at 960 px wide in the story-safe band, over a blurred, darkened copy of itself."""
    from PIL import Image, ImageFilter
    im = Image.open(src).convert("RGB")
    bg = im.resize((1080, round(im.height * 1080 / im.width))).resize((1080, 1920)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", bg.size, "black"), 0.45)
    fg = im.resize((960, round(im.height * 960 / im.width)), Image.LANCZOS)
    bg.paste(fg, ((1080 - fg.width) // 2, max(300, (1920 - fg.height) // 2 - 20)))
    bg.save(dest, quality=92, subsampling=0)
    return dest


def story_video(src, dest):
    """A reel as a story: same video, trimmed to Instagram's 60 s story limit when longer. A 4:5 animated carousel slide is
    framed like story_image: 960 px wide in the story-safe band over a blurred, darkened copy of itself."""
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)]))
    w, h = map(int, subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                              "-of", "csv=p=0", str(src)]).decode().strip().split(","))
    if abs(h / w - 16 / 9) > 0.02:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex",
                        "[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=40:2,"
                        "eq=brightness=-0.22[bg];[b]scale=960:-2[fg];[bg][fg]overlay=(W-w)/2:max(300\\,(H-h)/2-20),format=yuv420p",
                        "-t", "59.5", "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-c:a", "aac", str(dest)], check=True)
        return dest
    if dur <= 59.5:
        shutil.copy(src, dest)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-t", "59.5", "-af", "afade=t=out:st=58.3:d=1.2",
                        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-c:a", "aac", str(dest)], check=True)
    return dest


def c_share(a):
    """Reuse a finished post in another format, instantly — no new making or review (the content is already approved).
    Today: as a story (poster / carousel slide -> 9:16 image, animated slide or reel -> 9:16 video, at most 60 s)."""
    from .config import MEDIA, WORK
    from .pipeline import publish_copy
    src = db.get(a.id)
    if not src or not src.get("media"): raise SystemExit(f"#{a.id} has no finished media to share yet")
    files = [MEDIA / u.split("/m/", 1)[1] for u in json.loads(src["media"])]
    pick = files[min(max(a.slide, 1), len(files)) - 1]
    d = WORK / f"share-{a.id:05d}"; d.mkdir(parents=True, exist_ok=True)
    out = story_video(pick, d / "story.mp4") if pick.suffix == ".mp4" else story_image(pick, d / "story.jpg")
    slot = when(a.at) if a.at else db.now()
    nid = db.add(src["brand"], "story", f"{src['topic']} (story of #{a.id})", slot, angle=f"shared from #{a.id}", request=f"share #{a.id} as story")
    urls = publish_copy(db.get(nid), [out])
    db.update(nid, status="approved", media=urls, caption="", override=src.get("override") or 0, dir=str(d),
              preview_at=db.iso(db.now() - dt.timedelta(minutes=VETO_MIN)))
    db.log(nid, f"shared from #{a.id} as a story (owner request)")
    print(f"#{nid}: #{a.id} goes up as a {src['brand']} story {'within 5 minutes' if not a.at else 'at ' + slot.strftime('%a %d %b %H:%M')}.")


def c_motion(a):
    """Animated or still carousels. One item: before it's made, just the choice; once made, a still one is animated in place
    from its approved slides (a few minutes, preview on Telegram) and an animated one goes back to its still slides instantly.
    --share: how many new carousels are animated."""
    if a.share is not None:
        v = a.share / 100 if a.share > 1 else a.share; v = max(0.0, min(1.0, v)); db.set_setting("animated_share", v)
        print(f"From now on about {round(v * 100)}% of new carousels are animated and the rest still (each brand keeps its own mix). "
              "Already-booked carousels keep their choice; switch one with 'studio motion ID animated|still'."); return
    if a.id is None:
        v = db.setting("animated_share", 0)
        up = db.items("kind='carousel' AND status IN ('idea','queued','making','ready','approved','held')")
        n = {m: sum(1 for i in up if i.get("motion") == m) for m in ("animated", "static")}
        print(f"About {round(v * 100)}% of new carousels are animated. Booked now: {n['animated']} animated, {n['static']} still"
              f"{', ' + str(len(up) - sum(n.values())) + ' to be decided when made' if len(up) > sum(n.values()) else ''}."); return
    it = db.get(a.id)
    if not it: raise SystemExit(f"no item #{a.id}")
    if it["kind"] != "carousel": raise SystemExit(f"#{a.id} is a {it['kind']}; only carousels are animated or still (reels always move)")
    want = {"still": "static"}.get(a.state, a.state)
    if not want: raise SystemExit("say animated, still or auto")
    if it["status"] in ("published", "publishing"): raise SystemExit(f"#{a.id} is already {it['status']}; a live post can't be changed")
    if want == "auto":
        db.update(a.id, motion=None); print(f"#{a.id}: animated or still is picked when it's made (keeps the brand's mix)."); return
    media = json.loads(it.get("media") or "[]"); moving = any(u.endswith(".mp4") for u in media)
    db.update(a.id, motion=want); db.log(a.id, f"owner: carousel {want}")
    if not media or it["status"] not in ("ready", "approved", "held"):
        print(f"#{a.id} will be {'animated' if want == 'animated' else 'still slides'} when it's made."); return
    if want == "animated":
        slides = sorted({int(x) for x in re.findall(r"\d+", a.slides or "")}) or None
        n = len(media)
        if slides and any(not 1 <= x <= n for x in slides): raise SystemExit(f"#{a.id} has slides 1-{n}")
        done = [k + 1 for k, u in enumerate(media) if u.endswith(".mp4")]
        todo = [x for x in (slides or range(1, n + 1)) if x not in done]
        if not todo: print(f"#{a.id}: {'those slides are' if slides else 'every slide is'} already animated."); return
        db.set_setting(f"motion_slides:{a.id}", todo if slides else None)
        db.enqueue(a.id, action="animate", priority=10)
        print(f"#{a.id}: animating {'slide' + ('s ' if len(todo) > 1 else ' ') + ', '.join(map(str, todo)) if slides else 'all its slides'} now "
              f"(a few minutes); the other slides stay as they are. It keeps its slot; the new preview comes here.")
    else:
        if not moving: print(f"#{a.id} is already still slides."); return
        from .pipeline import publish_copy
        d = pathlib.Path(it["dir"]); plan = json.loads((d / "plan.json").read_text())
        jpgs = [d / "slides" / f"slide-{s['n']:02d}.jpg" for s in plan["slides"]]
        db.update(a.id, media=publish_copy(it, jpgs)); print(f"#{a.id} now posts as still slides (same design, same slot).")


MIX = ["story", "carousel", "story", "reel", "carousel", "poster", "story", "reel"]   # per brand, in this order
SPEED = {"poster": 0, "story": 1, "carousel": 2, "reel": 3}                          # made fastest first -> earliest slots


def c_today(a):
    """The owner wants N posts today: book N new items round the brands (a mix of stories, carousels, reels and posters), each
    scouting its own fresh story, spread from ~90 min from now (the time they take to make) to the end of the day, and start
    making them all now."""
    brands = list(BRANDS) if a.brands in (None, "all") else [b.strip() for b in a.brands.split(",")]
    if any(b not in BRANDS for b in brands): raise SystemExit(f"brands: {', '.join(BRANDS)}")
    if not 1 <= a.n <= 40: raise SystemExit("between 1 and 40 posts")
    day = when(a.day + " 00:00") if a.day else db.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = max(db.now() + dt.timedelta(minutes=90), when(day.strftime("%Y-%m-%d ") + (a.from_ or "09:00")))
    end = when(day.strftime("%Y-%m-%d ") + (a.until or "23:30"))
    if end <= start + dt.timedelta(minutes=30): raise SystemExit(f"not enough of the day left (from {start:%H:%M} to {end:%H:%M}); try --day tomorrow's date")
    per = {b: a.n // len(brands) + (1 if k < a.n % len(brands) else 0) for k, b in enumerate(brands)}
    booked = []
    for k, b in enumerate(brands):
        kinds = sorted([MIX[j % len(MIX)] for j in range(per[b])], key=lambda x: SPEED[x])
        if not kinds: continue
        step = (end - start) / max(1, len(kinds))
        for j, kind in enumerate(kinds):
            t = start + step * j + dt.timedelta(minutes=min(OFFSET_MIN.get(b, 0), step.total_seconds() / 180))   # brands staggered
            t = (t + dt.timedelta(minutes=(5 - t.minute % 5) % 5)).replace(second=0, microsecond=0)                 # on 5-minute marks
            i = db.add(b, kind, "auto", t, "", "", request=f"owner: {a.n} posts today")
            if kind == "carousel": db.update(i, motion=db.pick_motion(b))
            db.update(i, status="queued"); db.enqueue(i, priority=10); booked.append((t, b, kind, i))
    booked.sort()
    print(f"Booked {len(booked)} posts for {day:%a %d %b}, made now (fresh stories scouted per post), posting {booked[0][0]:%H:%M}–{booked[-1][0]:%H:%M}:")
    for t, b, kind, i in booked: print(f"  #{i} {t:%H:%M} {BRANDS[b]['name']:<10} {kind}")
    print("Previews come here as each is made; they post at their times unless you hold them. Reels take longest (~30–40 min each).")


def c_queue(a):
    """The making queue, in the order the worker takes it (what's being made now first)."""
    making = db.items("status='making'")
    lines = [f"now   {short(i)}" for i in making]
    for q in db.queue():
        it = db.get(q["item_id"])
        if it: lines.append(f"{q['pos']:>3}.  {short(it)}  [{db.PRIORITY_NAME.get(q['priority'], q['priority'])}]")
    print("\n".join(lines) or "Nothing being made or queued.")


def c_priority(a):
    """Escalate (or lower) a post in the making queue. top = the very next job a lane takes; a post that isn't queued yet
    (planned, failed, held before making) is queued at that priority."""
    it = db.get(a.id)
    if not it: raise SystemExit(f"no item #{a.id}")
    pr = db.PRIORITY[a.level]
    if it["status"] == "making": print(f"#{a.id} is being made right now."); return
    if it["status"] in ("published", "publishing", "removed"): raise SystemExit(f"#{a.id} is {it['status']}")
    with db.conn() as c:
        n = c.execute("UPDATE jobs SET priority=? WHERE item_id=? AND status='queued'", (pr, a.id)).rowcount
    if not n:
        if it["status"] in ("ready", "approved", "held") and it.get("media"): raise SystemExit(f"#{a.id} is already made ({it['status']})")
        db.update(a.id, status="queued"); db.enqueue(a.id, priority=pr)
    pos = next((q["pos"] for q in db.queue() if q["item_id"] == a.id), None)
    db.log(a.id, f"owner: priority {a.level}")
    print(f"#{a.id}: priority {a.level} — {'next in line' if pos == 1 else f'number {pos} in the queue' if pos else 'queued'}.")


def c_scout(a):
    """Find fresh post ideas now (web search) and pitch them as suggestions: they wait for the owner's "yes N" (Telegram or the
    Approvals tab); nothing is made before that. --topic narrows the search, --brand picks one account. Each run is logged
    (setting scout_runs) for the dashboard's Automation tab."""
    from . import llm
    from .pipeline import rules, today
    brands = list(BRANDS) if a.brand in (None, "all") else [a.brand]
    if any(b not in BRANDS for b in brands): raise SystemExit(f"brand is all or one of {', '.join(BRANDS)}")
    n = max(1, min(10, a.n)); topic = (a.topic or "").strip()[:160]
    run = {"ts": db.iso(db.now()), "by": a.by or "owner", "brand": a.brand or "all", "topic": topic, "n": n, "status": "running", "ids": []}

    def save():
        runs = [r for r in (db.setting("scout_runs", []) or []) if r.get("ts") != run["ts"]]
        db.set_setting("scout_runs", [run] + runs[:29])
    save()
    recent = db.items("created >= ? AND status NOT IN ('removed','declined')", (db.iso(db.now() - dt.timedelta(days=10)),))
    avoid = "\n".join(f"- {BRANDS[r['brand']]['name']} {r['kind']}: {r['topic']}" for r in recent if r["topic"] and r["topic"] != "auto")[-6000:] or "none"
    try:
        res = llm.ask_json(llm.fill((PROMPTS / "scout.md").read_text(), rules=rules(), today=today(), n=n,
                                    scope=f"for {BRANDS[brands[0]]['name']}" if len(brands) == 1 else "across the three accounts",
                                    topic_line=f"The owner asked to scout: \"{topic}\" — every idea must be about that." if topic else "",
                                    brands="\n".join(f"- {b}: {BRANDS[b]['name']} (@{BRANDS[b]['handle']}) — {BRANDS[b]['focus']}" for b in brands),
                                    avoid=avoid), search=True, timeout=1500)
        for x in res.get("ideas", []):
            if len(run["ids"]) >= n: break
            if x.get("brand") not in brands or x.get("kind") not in KINDS or not x.get("topic"): continue
            if db.items("brand=? AND lower(topic)=lower(?) AND status NOT IN ('removed','declined')", (x["brand"], x["topic"])): continue
            i = db.add(x["brand"], x["kind"], x["topic"][:120], None, (x.get("angle") or "")[:300],
                       f"Source (scout): {x.get('source') or ''}", request=f"suggested (scout, {run['by']}): {(x.get('why') or '')[:300]}")
            db.update(i, status="suggested")
            if x["kind"] == "carousel": db.update(i, motion=db.pick_motion(x["brand"]))
            run["ids"].append(i)
        run["status"] = "done"
    except Exception as e:
        run["status"] = f"failed: {type(e).__name__}: {e}"[:200]
    save(); db.log(None, f"scout ({run['by']}{', ' + topic if topic else ''}): {run['status']}, {len(run['ids'])} ideas")
    lines = [f"#{i} {BRANDS[db.get(i)['brand']]['name']} {db.get(i)['kind']} — {db.get(i)['topic']}" for i in run["ids"]]
    msg = (f"🔎 Scout{' on ' + repr(topic) if topic else ''}: {len(lines)} ideas\n" + "\n".join(lines) +
           f"\n\nReply 'yes N' to make one (or 'yes all'), 'no N' to drop it — or tap on {PUBLIC}/dash/approve.html") \
        if lines else f"🔎 Scout{' on ' + repr(topic) if topic else ''}: nothing new worth posting right now ({run['status']})."
    if run["ids"] and run["by"] != "owner": tg.notify(f"{len(run['ids'])} new ideas from the scout{' on ' + repr(topic) if topic else ''}", None, "pitch")
    print(msg)   # asked through Hermes: Hermes relays this reply itself


def c_import(a):
    """Post a finished file through the studio — the owner's own video/image, or one they have permission for, already edited.
    It is copied to the public media folder, captioned and previewed on Telegram; it posts now (--post), at --at, or waits in
    Approvals for the owner. The committee does not review it: the owner sent it and owns the call."""
    from .pipeline import publish_copy
    src = pathlib.Path(a.file)
    if not src.is_file() or src.suffix.lower() not in (".mp4", ".mov", ".jpg", ".jpeg", ".png"): raise SystemExit("give an .mp4, .mov, .jpg or .png file")
    if a.brand not in BRANDS: raise SystemExit(f"brand is one of {', '.join(BRANDS)}")
    kind = a.kind or ("reel" if src.suffix.lower() in (".mp4", ".mov") else "poster")
    slot = when(a.at) if a.at else (db.now() if a.post else None)
    i = db.add(a.brand, kind, a.topic or src.stem, slot, notes=a.notes or "", request="owner import")
    urls = publish_copy(db.get(i), [src])
    db.update(i, media=urls, caption=a.caption or "", status="approved" if (a.post or a.at) else "held", override=1,
              preview_at=db.iso(db.now() - dt.timedelta(minutes=VETO_MIN)), dir=str(src.parent))
    db.log(i, f"owner import: {src.name}{' — ' + a.notes if a.notes else ''}")
    head = f"#{i} {BRANDS[a.brand]['name']} {kind} (your file) — " + ("posting now." if a.post else f"posts {slot:%a %d %b %H:%M}." if slot else "waits for your OK in Approvals.")
    if not (a.post or a.at): tg.notify(f"#{i} {BRANDS[a.brand]['name']} {kind} (your file) waits for your OK", i, "needs")
    if a.post:
        do_publish(db.get(i)); it = db.get(i)
        print(f"#{i}: {it['status']} {it['permalink'] or it.get('error') or ''}")
    else:
        print(f"#{i} imported: {head}")


def c_cta(a):
    """The comment-to-DM offer on one post: show it, set it (keyword + the DM text), or switch it off. On a live post the
    DMs start at the next check (5 min); Instagram allows one DM per comment, within 7 days of the comment."""
    from . import dm
    it = db.get(a.id)
    if not it: raise SystemExit(f"no item #{a.id}")
    if not a.keyword:
        c = json.loads(it.get("cta") or "null")
        if not c: print(f"#{a.id} has no comment-to-DM offer."); return
        print(f"#{a.id}: comment \"{c['keyword']}\" -> DM ({dm.count(a.id)} sent so far):\n{c['dm']}"); return
    if a.keyword == "off":
        db.update(a.id, cta=None); db.log(a.id, "owner: cta off"); print(f"#{a.id}: no more DMs for comments."); return
    kw = a.keyword.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,12}", kw): raise SystemExit("the keyword is one word, 2-12 letters/digits")
    if not a.dm or len(a.dm.encode()) > 950: raise SystemExit("give the DM text (up to ~950 characters), in single quotes")
    db.update(a.id, cta=json.dumps({"keyword": kw, "dm": a.dm, "offer": a.offer or "the links"}, ensure_ascii=False))
    line = f"💬 Comment {kw} and I'll DM you {a.offer or 'the links'}."
    if it["status"] not in ("published", "publishing") and it.get("caption") and not re.search(rf"comment\W+{kw}\b", it["caption"], re.I):
        head, _, rest = it["caption"].partition("\n\n"); db.update(a.id, caption=f"{head}\n{line}\n\n{rest}".strip())
    db.log(a.id, f"owner: cta {kw}")
    print(f"#{a.id}: anyone who comments \"{kw}\" gets your DM" + (" (checking every 5 minutes)." if it["status"] == "published" else
          f" once it's live; the caption now says: {line}"))


def c_look(a):
    """News carousel (real official images, pixel-true, with designed headline panels) or designed slides, for one carousel."""
    it = db.get(a.id)
    if not it: raise SystemExit(f"no item #{a.id}")
    if it["kind"] != "carousel": raise SystemExit(f"#{a.id} is a {it['kind']}; the news look is for carousels")
    if it["status"] in ("published", "publishing", "making"): raise SystemExit(f"#{a.id} is {it['status']}; set the look before it's made, or retry it after")
    look = None if a.value == "auto" else a.value
    db.update(a.id, look=look); db.log(a.id, f"owner: look {a.value}")
    made = it.get("media") and it["status"] in ("ready", "approved", "held")
    print(f"#{a.id}: {'news slides with real official images' if look == 'news' else 'designed slides' if look == 'designed' else 'news when official images exist, else designed'}"
          + (f". It's already made — say 'retry {a.id}' to re-make it this way." if made else " when it's made."))


def c_draw_people(a):
    """Owner switch for AI-drawn real people (off by default): one item, or a whole brand."""
    on = (a.state or "on") == "on"
    if a.brand:
        cur = set(db.setting("likeness_brands", []) or [])
        cur = cur | {a.brand} if on else cur - {a.brand}; db.set_setting("likeness_brands", sorted(cur))
        print(f"{BRANDS[a.brand]['name']}: AI illustrations of real people {'ALLOWED on every post' if on else 'off'} (captioned 'Illustration: AI-generated.').")
    elif a.id:
        db.update(a.id, likeness=1 if on else 0); db.log(a.id, f"owner: draw-people {'on' if on else 'off'}")
        print(f"#{a.id}: AI illustration of the real people in it {'allowed' if on else 'off'}. Say retry {a.id} to re-make it this way.")
    else:
        print("brands allowing AI-drawn people:", ", ".join(db.setting("likeness_brands", []) or []) or "none (per-post only)")


def c_slots(a):
    """Posting times (IST). `studio slots reel 12:30,19:30` sets them (brands still stagger +0/20/40 min); future plans use them;
    `--apply` also moves already-booked future items onto the new times."""
    cur = db.setting("slots", {}) or {}
    if a.kind:
        if a.kind not in KINDS or not a.times: raise SystemExit("studio slots KIND HH:MM[,HH:MM…]")
        times = [t.strip() for t in a.times.split(",")]
        for t in times: dt.datetime.strptime(t, "%H:%M")
        cur[a.kind] = times; db.set_setting("slots", cur)
        if a.apply:
            n = 0
            for it in db.items("kind=? AND status IN ('idea','queued','ready','approved') AND slot > ?", (a.kind, db.iso(db.now()))):
                day = db.parse(it["slot"]); same = [x for x in db.items("brand=? AND kind=? AND slot LIKE ? AND id<? AND status NOT IN ('removed')",
                                                                          (it["brand"], a.kind, day.strftime("%Y-%m-%d") + "%", it["id"]))]
                hh, mm = map(int, times[len(same) % len(times)].split(":"))
                db.update(it["id"], slot=db.iso(day.replace(hour=hh, minute=mm) + dt.timedelta(minutes=OFFSET_MIN[it["brand"]]))); n += 1
            print(f"moved {n} booked {a.kind}s onto the new times")
    for k, v in slots().items(): print(f"{k:<9} {', '.join(v)}  (+0/20/40 min for SPORTS DESK / TECHDESK / BIZDESK)")


def c_prepare(a):
    """Make booked items now instead of 14 h before their slot. Planned topics by default; --all also makes the 'auto' (news)
    slots now — they will pick today's news, which may be stale by their slot."""
    where = "status='idea' AND slot IS NOT NULL AND slot <= ?"; args = [db.iso(db.now() + dt.timedelta(days=a.days))]
    if not a.all: where += " AND topic <> 'auto'"
    if a.brand: where += " AND brand=?"; args.append(a.brand)
    rows = db.items(where, tuple(args))
    for it in rows: db.update(it["id"], status="queued"); db.enqueue(it["id"], priority=1)
    left = len(db.items("status='idea' AND slot IS NOT NULL AND slot <= ? AND topic='auto'", (args[0],))) if not a.all else 0
    print(f"Queued {len(rows)} items to make now (3 at a time; previews arrive as each passes the committee)."
          + (f" {left} news slots ('auto') stay near their time so they carry that day's news; add --all to make those now too." if left else ""))


def c_post(a):
    it = db.get(a.id)
    if not it: raise SystemExit(f"no item #{a.id}")
    if a.when_ready or it["status"] in ("idea", "queued", "making"):   # not made yet: post the moment it is
        db.update(a.id, autopost=1); db.log(a.id, "owner: post when ready")
        if it["status"] == "idea": db.update(a.id, status="queued"); db.enqueue(a.id, priority=10)
        print(f"#{a.id} will post the moment it's made (status now {db.get(a.id)['status']}); you still get the preview."); return
    p, until, _ = db.paused()
    if p: raise SystemExit(f"The studio is paused until {until}. Say /unfreeze first.")
    if not it.get("media") or it["status"] not in ("ready", "approved", "held"):
        raise SystemExit(f"#{a.id} is {it['status']}; nothing finished to post (say 'override {a.id}' for a rejected one).")
    do_publish(it); print(f"#{a.id}: {db.get(a.id)['status']} {db.get(a.id)['permalink'] or ''}")


def c_mode(a):
    if a.value:
        if a.value not in ("veto", "auto", "manual"): raise SystemExit("mode is veto, auto or manual")
        db.set_setting("mode", a.value)
    print({"veto": f"veto: previews reach you ≥{VETO_MIN} min before posting; posts unless you hold it.",
           "auto": "auto: posts on schedule once the committee passes it (you still get the preview).",
           "manual": "manual: nothing posts until you approve it."}[mode()])


def c_cadence(a):
    cad = db.setting("cadence", {}) or {}
    if a.brand:
        cur = dict(cadence(a.brand))
        for k in KINDS:
            if getattr(a, k) is not None: cur[k] = getattr(a, k)
        cad[a.brand] = cur; db.set_setting("cadence", cad)
    for b in BRANDS: print(f"{BRANDS[b]['name']:<10} " + ", ".join(f"{v} {k}{'s' if v != 1 else ''}/day" for k, v in cadence(b).items()))
    print("slots (IST): " + "; ".join(f"{k} {', '.join(v)}" for k, v in SLOTS.items()) + " (+0/20/40 min per brand)")


def c_media(a):
    """The media & knowledge graph: find, about, add, import, graph, stats."""
    from . import graph
    if a.action == "stats":
        print(", ".join(f"{v} {k}" for k, v in graph.stats().items()))
    elif a.action == "find":
        q = f"%{' '.join(a.args)}%"
        for e in graph.rows("SELECT * FROM entities WHERE name LIKE ? OR official_site LIKE ? LIMIT 20", (q, q)):
            n = graph.rows("SELECT COUNT(*) n FROM edges WHERE dst=?", (f"entity:{e['id']}",))[0]["n"]
            print(f"entity #{e['id']} {e['name']} ({e['kind'] or '?'}) — {n} links {e['official_site'] or ''}")
        for x in graph.rows("SELECT * FROM assets WHERE title LIKE ? OR tags LIKE ? OR prompt LIKE ? LIMIT 20", (q, q, q)):
            print(f"asset #{x['id']} {x['kind']:<7} {x['title'][:50]:<50} {x['licence'] or '':<22} used {x['uses']}×")
        for f in graph.rows("SELECT * FROM facts WHERE claim LIKE ? ORDER BY verified DESC LIMIT 10", (q,)):
            print(f"fact #{f['id']} ({f['date'] or '?'}) {f['claim'][:140]}")
    elif a.action == "about":
        r = graph.about(" ".join(a.args))
        if not r: raise SystemExit("not in the graph yet")
        e = r["entity"]; print(f"{e['name']} ({e['kind'] or '?'}) {e['official_site'] or ''} — aliases: {', '.join(r['aliases'])}")
        for x in r["assets"]: print(f"  image #{x['id']} {x['kind']}: {x['title']} [{x['licence'] or ''}] used {x['uses']}×")
        for f in r["facts"][:15]: print(f"  fact ({f['date'] or '?'}): {f['claim'][:150]}")
        if r["items"]: print("  posts: " + ", ".join(f"#{i['id']}" for i in r["items"]))
        if r["related"]: print("  related: " + ", ".join(x["name"] for x in r["related"]))
    elif a.action == "add":
        if not (a.args and a.kind): raise SystemExit("studio media add FILE --kind logo|press|photo|object --entity NAME --source URL --licence L")
        from .assets import needs_credit
        ents = [graph.entity(a.entity)] if a.entity else []
        credit = f"{a.title or a.entity}: {a.author or 'unknown'}, {a.licence}" if needs_credit(a.licence) else ""
        x = graph.add_asset(a.args[0], a.kind, ents, title=a.title or (f"{a.entity} {a.kind}" if a.entity else ""), tags=a.tags or "",
                            source_url=a.source or "", source_page=a.source or "", licence=a.licence or "owner-provided", credit=credit)
        print(f"asset #{x['id']} saved: {x['kind']} {x['title']} -> {x['path']}")
    elif a.action == "import":
        n = 0
        for r in json.loads(open(a.args[0]).read()):
            ents = [graph.entity(r["entity"], r.get("entity_kind"), r.get("aliases", []), r.get("official_site"), r.get("company"))] if r.get("entity") else []
            graph.add_asset(r["file"], r["kind"], ents, title=r.get("title", ""), tags=r.get("tags", ""), source_url=r.get("source_url", ""),
                            source_page=r.get("source_page", ""), licence=r.get("licence", ""), credit=r.get("credit", ""), prompt=r.get("prompt", ""))
            n += 1
        print(f"imported {n} assets; graph now {graph.stats()}")
    elif a.action == "graph":
        print(graph.export_html())
    elif a.action == "remove":
        for x in a.args:
            r = graph.remove_asset(int(x))
            print(f"removed image #{x}: {r['kind']} {r['title']}" if r else f"no image #{x}")


def c_log(a):
    with db.conn() as c:
        q = "SELECT * FROM events" + (" WHERE item_id=?" if a.id else "") + " ORDER BY id DESC LIMIT ?"
        rows = c.execute(q, ((a.id, a.n) if a.id else (a.n,))).fetchall()
    for r in reversed(rows): print(f"{r['ts']} {('#' + str(r['item_id'])) if r['item_id'] else '-':<6} {r['level']:<5} {r['msg'][:220]}")


def c_check(a):
    from . import igclient as ig
    for b in BRANDS:
        try:
            r = ig.check(b); print(f"{BRANDS[b]['name']:<10} @{r['username']} ({r['type']}) quota {r['quota'].get('quota_usage')}/{(r['quota'].get('config') or {}).get('quota_total')} per 24h")
        except Exception as e: print(f"{BRANDS[b]['name']:<10} PROBLEM: {e}")
    du = shutil.disk_usage(ROOT); print(f"disk: {du.free / 1e9:.0f} GB free of {du.total / 1e9:.0f} GB")
    for s in ("studio-worker", "studio-tick.timer", "hermes-gateway", "caddy"):
        st = subprocess.run(["systemctl", "is-active", s], capture_output=True, text=True).stdout.strip()
        if st != "active":
            import os
            env = dict(os.environ, XDG_RUNTIME_DIR=f"/run/user/{os.getuid()}")
            st = subprocess.run(["systemctl", "--user", "is-active", s], capture_output=True, text=True, env=env).stdout.strip() or st
        print(f"{s}: {st}")
    p = subprocess.run(["codex", "login", "status"], capture_output=True, text=True); print("codex:", (p.stdout or p.stderr).strip().splitlines()[-1:])


def c_tick(a):
    """Every 5 minutes: auto-resume, publish what's due, start making what's coming, expire stale news, morning digest."""
    db.set_setting("last_tick", db.iso(db.now()))
    p, _, _ = db.paused()
    if p: return
    now = db.now()
    if db.setting("last_refresh") != now.date().isoformat():
        from . import igclient as ig
        try:
            ch = ig.refresh_all()
            if ch: db.log(None, f"refreshed tokens: {ch}")
        except Exception as e: tg.notify(f"Instagram login refresh failed — {str(e)[:120]}", None, "alert")
        db.set_setting("last_refresh", now.date().isoformat())
    try:   # comment KEYWORD -> DM, for live posts with a cta
        from . import dm
        dm.scan()
    except Exception as e:
        db.log(None, f"dm scan failed: {e}", "warn")
    for it in db.items("status IN ('ready','approved') AND slot IS NOT NULL AND slot <= ?", (db.iso(now),)):
        slot = db.parse(it["slot"])
        if BRANDS[it["brand"]]["beat"] in ("sports", "tech") and now - slot > dt.timedelta(hours=4):
            db.update(it["id"], status="expired"); tg.notify(f"#{it['id']} {(it['topic'] or '')[:50]} missed its slot by 4 h+ — not posted (stale)", it["id"], "failed"); continue
        if not publishable(it): continue
        if mode() == "veto" and it["preview_at"] and now < db.parse(it["preview_at"]) + dt.timedelta(minutes=VETO_MIN): continue
        do_publish(it)
    for it in db.items("status='idea' AND slot IS NOT NULL AND slot <= ?", (db.iso(now + dt.timedelta(hours=LEAD_HOURS)),)):
        db.update(it["id"], status="queued"); db.enqueue(it["id"])
    for it in db.items("status IN ('failed') AND attempts < 2 AND slot IS NOT NULL AND slot > ?", (db.iso(now + dt.timedelta(hours=1)),)):
        db.update(it["id"], status="queued"); db.enqueue(it["id"]); db.log(it["id"], "auto-retry")
    try:
        tg.flush()   # one short "things for you" message with the Approvals link, at most every 20 min
    except Exception as e:
        db.log(None, f"telegram digest failed: {e}", "warn")
    if now.hour == 9 and db.setting("digest") != now.date().isoformat():
        db.set_setting("digest", now.date().isoformat())
        today_items = db.items("slot >= ? AND slot < ? AND status NOT IN ('removed')", (db.iso(now.replace(hour=0, minute=0)), db.iso(now.replace(hour=23, minute=59))))
        waiting = len(db.items("status IN ('held','rejected','failed','suggested')"))
        tg.say(f"🌅 Good morning! Start with /new today (fresh chat = fast replies).\n"
               f"Today: {len(today_items)} posts booked · {waiting} waiting for you 👉 {tg.APPROVALS}")


def c_dash(a):
    from .dashboard import build
    build(); print(f"{PUBLIC}/dash/")


def c_reload(a):
    db.set_setting("reload", True)
    print("Reload requested: the dispatcher restarts within seconds on the new code; posts being made carry on in their own processes.")


def c_run_job(a):
    """Make one queued job in THIS process (the worker starts one process per job, so each job runs the latest code and a
    deploy or worker restart never interrupts it). Marks the job done/failed itself."""
    from . import pipeline
    job = db.get_job(a.job)
    if not job: raise SystemExit(f"no job {a.job}")
    db.set_job_pid(job["id"], os.getpid()); os.environ["STUDIO_JOB_ID"] = str(job["id"])   # CPU turns go by this job's priority
    it = db.get(job["item_id"])
    if not it or it["status"] in ("removed", "published", "publishing") or (it["status"] == "held" and job["action"] != "animate"):
        db.finish_job(job["id"], True, "skipped"); return
    ok = False
    try:
        ok = (pipeline.animate_existing if job["action"] == "animate" else pipeline.make)(job["item_id"])
    finally:
        db.finish_job(job["id"], bool(ok))
    sys.exit(0 if ok else 1)


def c_worker(a):
    """The dispatcher: WORKERS lanes, each claims the next job and makes it in its own process (`studio run-job`). Research,
    writing, review and images overlap; voice and render take turns on the CPU (pipeline.CPU, a file lock). A restart or deploy
    never interrupts a job: its process carries on (systemd KillMode=process) and the new dispatcher counts it as a busy lane.
    A pause stops new work; jobs in hand finish."""
    import threading
    from .config import WORKERS
    db.set_setting("reload", None)
    n = db.recover_jobs()
    print(f"worker up: {WORKERS} lanes, jobs in their own processes ({n} orphaned job(s) re-queued, "
          f"{len(db.running_alive())} still running from before)", flush=True)
    env = dict(os.environ)

    def lane(k):
        while True:
            try:
                if db.setting("reload"):   # a new dispatcher: running job processes carry on without us
                    print("reload: restarting the dispatcher now (running jobs continue)", flush=True); os._exit(0)
                if db.paused()[0]: time.sleep(60); continue
                db.recover_jobs()
                if len(db.running_alive()) >= WORKERS: time.sleep(10); continue
                job = db.next_job()
                if not job: time.sleep(15); continue
                print(f"lane {k}: job {job['id']} item {job['item_id']} (priority {job.get('priority') or 0})", flush=True)
                p = subprocess.Popen([sys.executable, "-u", "-m", "studio.cli", "run-job", str(job["id"])], env=env, cwd=str(ROOT))
                db.set_job_pid(job["id"], p.pid)
                p.wait()
                j = db.get_job(job["id"])
                if j and j["status"] == "running":   # the process died without closing its job
                    db.finish_job(job["id"], False, f"job process exited {p.returncode}")
                    it = db.get(job["item_id"])
                    if it and it["status"] == "making": db.update(it["id"], status="failed", error=f"the making process stopped (exit {p.returncode})")
            except Exception as e:   # a lane never dies
                print(f"lane {k}: {type(e).__name__}: {e}", flush=True); time.sleep(10)
    lanes = [threading.Thread(target=lane, args=(k,), daemon=True) for k in range(WORKERS)]
    for t in lanes: t.start(); time.sleep(3)
    for t in lanes: t.join()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("status").set_defaults(f=c_status)
    x = sp.add_parser("pause"); x.add_argument("args", nargs="*"); x.set_defaults(f=c_pause)
    sp.add_parser("resume").set_defaults(f=c_resume)
    x = sp.add_parser("plan"); x.add_argument("--brands", default="all"); x.add_argument("--days", type=int, default=7)
    x.add_argument("--topic"); x.add_argument("--start"); x.add_argument("--request"); x.add_argument("--dry-run", action="store_true")
    for k in KINDS: x.add_argument(f"--{k}", type=int)
    x.set_defaults(f=c_plan)
    x = sp.add_parser("add"); x.add_argument("brand"); x.add_argument("kind"); x.add_argument("topic")
    x.add_argument("--at"); x.add_argument("--asap", action="store_true"); x.add_argument("--angle"); x.add_argument("--notes")
    x.add_argument("--source"); x.add_argument("--draw-people", action="store_true")
    x.add_argument("--animated", action="store_true"); x.add_argument("--still", "--static", dest="still", action="store_true")
    x.add_argument("--news", action="store_true"); x.add_argument("--designed", action="store_true"); x.set_defaults(f=c_add)
    x = sp.add_parser("suggest"); x.add_argument("brand"); x.add_argument("kind"); x.add_argument("topic")
    x.add_argument("--angle"); x.add_argument("--source"); x.add_argument("--why"); x.add_argument("--notes")
    x.add_argument("--animated", action="store_true"); x.add_argument("--still", "--static", dest="still", action="store_true"); x.set_defaults(f=c_suggest)
    x = sp.add_parser("accept"); x.add_argument("id", type=int); x.add_argument("--at"); x.add_argument("--asap", action="store_true"); x.set_defaults(f=c_accept)
    x = sp.add_parser("decline"); x.add_argument("id", type=int); x.set_defaults(f=c_decline)
    x = sp.add_parser("list"); x.add_argument("--brand"); x.add_argument("--status"); x.add_argument("--days", type=int); x.add_argument("--all", action="store_true"); x.set_defaults(f=c_list)
    for name, fn in (("show", c_show), ("make", c_make), ("remove", c_remove), ("post", c_post), ("override", c_override)):
        x = sp.add_parser(name); x.add_argument("id", type=int); x.set_defaults(f=fn)
        if name == "post": x.add_argument("--when-ready", action="store_true")
    for name, st, allowed in (("approve", "approved", ("ready", "held")), ("hold", "held", ("idea", "queued", "making", "ready", "approved")),
                              ("release", "ready", ("held",)), ("retry", "idea", ("failed", "rejected", "expired", "held"))):
        x = sp.add_parser(name); x.add_argument("id", type=int)
        x.set_defaults(f=lambda a, st=st, allowed=allowed, name=name: set_status(a.id, st, allowed, name))
    x = sp.add_parser("move"); x.add_argument("id", type=int); x.add_argument("at"); x.set_defaults(f=c_move)
    x = sp.add_parser("slots"); x.add_argument("kind", nargs="?"); x.add_argument("times", nargs="?"); x.add_argument("--apply", action="store_true")
    x.set_defaults(f=c_slots)
    x = sp.add_parser("prepare"); x.add_argument("--days", type=int, default=7); x.add_argument("--brand"); x.add_argument("--all", action="store_true")
    x.set_defaults(f=c_prepare)
    x = sp.add_parser("draw-people"); x.add_argument("id", type=int, nargs="?"); x.add_argument("state", nargs="?", choices=["on", "off"])
    x.add_argument("--brand"); x.set_defaults(f=c_draw_people)
    x = sp.add_parser("motion"); x.add_argument("id", type=int, nargs="?")
    x.add_argument("state", nargs="?", choices=["animated", "still", "static", "auto"]); x.add_argument("--share", type=float)
    x.add_argument("--slides"); x.set_defaults(f=c_motion)
    x = sp.add_parser("queue"); x.set_defaults(f=c_queue)
    x = sp.add_parser("priority"); x.add_argument("id", type=int); x.add_argument("level", choices=list(db.PRIORITY)); x.set_defaults(f=c_priority)
    x = sp.add_parser("scout"); x.add_argument("--brand"); x.add_argument("--topic"); x.add_argument("--n", type=int, default=5)
    x.add_argument("--by"); x.set_defaults(f=c_scout)
    x = sp.add_parser("import"); x.add_argument("file"); x.add_argument("brand"); x.add_argument("--kind", choices=["reel", "story", "poster"])
    x.add_argument("--caption"); x.add_argument("--topic"); x.add_argument("--post", action="store_true"); x.add_argument("--at"); x.add_argument("--notes")
    x.set_defaults(f=c_import)
    x = sp.add_parser("today"); x.add_argument("n", type=int); x.add_argument("--brands"); x.add_argument("--from", dest="from_")
    x.add_argument("--until"); x.add_argument("--day"); x.set_defaults(f=c_today)
    x = sp.add_parser("cta"); x.add_argument("id", type=int); x.add_argument("keyword", nargs="?"); x.add_argument("dm", nargs="?")
    x.add_argument("--offer"); x.set_defaults(f=c_cta)
    x = sp.add_parser("look"); x.add_argument("id", type=int); x.add_argument("value", choices=["news", "designed", "auto"]); x.set_defaults(f=c_look)
    x = sp.add_parser("share"); x.add_argument("id", type=int); x.add_argument("--as", dest="as_", default="story", choices=["story"])
    x.add_argument("--slide", type=int, default=1); x.add_argument("--at"); x.set_defaults(f=c_share)
    x = sp.add_parser("mode"); x.add_argument("value", nargs="?"); x.set_defaults(f=c_mode)
    x = sp.add_parser("cadence"); x.add_argument("brand", nargs="?")
    for k in KINDS: x.add_argument(f"--{k}", type=int)
    x.set_defaults(f=c_cadence)
    x = sp.add_parser("media"); x.add_argument("action", choices=["find", "about", "add", "import", "graph", "stats", "remove"]); x.add_argument("args", nargs="*")
    for o in ("--kind", "--entity", "--source", "--licence", "--title", "--tags", "--author"): x.add_argument(o)
    x.set_defaults(f=c_media)
    x = sp.add_parser("log"); x.add_argument("id", type=int, nargs="?"); x.add_argument("-n", type=int, default=30); x.set_defaults(f=c_log)
    sp.add_parser("check").set_defaults(f=c_check)
    sp.add_parser("tick").set_defaults(f=c_tick)
    sp.add_parser("worker").set_defaults(f=c_worker)
    x = sp.add_parser("run-job"); x.add_argument("job", type=int); x.set_defaults(f=c_run_job)
    sp.add_parser("reload").set_defaults(f=c_reload)
    sp.add_parser("dash").set_defaults(f=c_dash)
    a = ap.parse_args(argv); a.f(a)


if __name__ == "__main__":
    main()
