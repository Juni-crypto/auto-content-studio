"""Comment KEYWORD -> DM (the "comment SEO and I'll send you all three" call to action).

A post can carry a cta {"keyword": "AI", "dm": "the message with the links", "offer": "the links"}. Every 5 minutes (tick) the
studio reads the comments on posts published in the last 8 days that have a cta; each person whose comment contains the keyword
gets ONE private reply (Instagram allows exactly one per comment, within 7 days) and a short public "Sent! Check your DMs" under
their comment. Nobody else is ever messaged. Everything goes through the token helper (studio-ig); every DM is logged in `dms`.
"""
import datetime as dt, json, re
from . import db, igclient
from .config import BRANDS

MAX_PER_RUN = 40   # per brand per tick, well under Instagram's messaging limits


def keyword_in(kw, text):
    return bool(re.search(rf"(?<![\w]){re.escape(kw)}(?![\w])", text or "", re.I))


def sent(comment_id):
    with db.conn() as c:
        return c.execute("SELECT 1 FROM dms WHERE comment_id=?", (comment_id,)).fetchone() is not None


def record(cid, item_id, brand, user, text, ok, err=""):
    with db.conn() as c:
        c.execute("INSERT OR REPLACE INTO dms(comment_id,item_id,brand,username,comment,ts,ok,error) VALUES(?,?,?,?,?,?,?,?)",
                  (cid, item_id, brand, user, (text or "")[:300], db.iso(db.now()), int(ok), err[:500]))


def count(item_id):
    with db.conn() as c:
        return c.execute("SELECT COUNT(*) FROM dms WHERE item_id=? AND ok=1", (item_id,)).fetchone()[0]


def scan():
    """Answer new keyword comments. Returns {item_id: DMs sent this run}."""
    since = db.iso(db.now() - dt.timedelta(days=8))
    live = db.items("status='published' AND cta IS NOT NULL AND ig_media_id IS NOT NULL AND updated >= ?", (since,))
    done = {}
    for brand in {i["brand"] for i in live}:
        mine = [i for i in live if i["brand"] == brand]
        try:
            got = igclient.comments(brand, [i["ig_media_id"] for i in mine][:30])
        except Exception as e:
            db.log(None, f"dm scan {brand}: {e}", "warn"); continue
        n = 0
        for it in mine:
            cta = json.loads(it["cta"]); kw = cta.get("keyword", "")
            for cm in got.get(it["ig_media_id"], []):
                if n >= MAX_PER_RUN: break
                if cm.get("username") == BRANDS[brand]["handle"] or not keyword_in(kw, cm.get("text")) or sent(cm["id"]): continue
                friend = BRANDS[brand]["friend"]
                try:
                    igclient.private_reply(brand, cm["id"], cta["dm"], f"Sent, {friend}! Check your DMs 📩")
                    record(cm["id"], it["id"], brand, cm.get("username"), cm.get("text"), True); n += 1
                    done[it["id"]] = done.get(it["id"], 0) + 1
                except Exception as e:
                    record(cm["id"], it["id"], brand, cm.get("username"), cm.get("text"), False, str(e))
                    db.log(it["id"], f"DM to @{cm.get('username')} failed: {e}", "warn")
    for iid, k in done.items(): db.log(iid, f"sent {k} DM(s) to people who commented the keyword")
    return done


def check_cta(cta, research, caption=""):
    """Problems with a writer's cta: one short keyword, a DM under 1000 bytes whose links all come from the research."""
    if not cta: return []
    p = []; kw = (cta.get("keyword") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{2,12}", kw): p.append("cta keyword: one word, 2-12 letters/digits")
    dm = cta.get("dm") or ""
    if not dm or len(dm.encode()) > 950: p.append("cta dm: 1-950 bytes")
    ok = {s.get("url", "").rstrip("/") for f in research.get("facts", []) for s in f.get("sources", [])}
    ok |= {u.rstrip("/") for u in research.get("official_pages") or []} | {(e.get("official_site") or "").rstrip("/") for e in research.get("entities", [])}
    for u in re.findall(r"https?://\S+", dm):
        if u.rstrip(".,)").rstrip("/") not in ok: p.append(f"cta dm link {u} is not one of the research sources / official sites")
    return p
