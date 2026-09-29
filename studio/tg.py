"""Telegram messages to the owner. The owner keeps Telegram for their own asks (28 Sep), so the studio does NOT send previews
or "posted" notes: things that need the owner go through notify() and reach them as ONE short message with the Approvals link,
at most every FLUSH_MIN minutes (flush() runs in the 5-minute tick). say() is only for replies and rare alerts.

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_ID from /opt/studio/.env. Sending never breaks the pipeline: errors are logged.
"""
import pathlib, requests
from .config import ROOT, PUBLIC


def env():
    vals = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1); vals[k.strip()] = v.strip().strip('"')
    return vals


def _send(method, data, files=None):
    e = env()
    try:
        r = requests.post(f"https://api.telegram.org/bot{e['TELEGRAM_BOT_TOKEN']}/{method}",
                          data={"chat_id": e["TELEGRAM_OWNER_ID"], **data}, files=files, timeout=120)
        return r.ok
    except Exception:
        return False


def say(text):
    return _send("sendMessage", {"text": text[:4000], "disable_web_page_preview": "true"})


def video(path, caption):
    p = pathlib.Path(path)
    if p.stat().st_size > 48e6: return say(caption + f"\n(preview too big to attach: {p.name})")
    with p.open("rb") as f:
        return _send("sendVideo", {"caption": caption[:1000], "supports_streaming": "true"}, {"video": f})


def photos(paths, caption):
    """A poster or a carousel as one album; animated carousel slides (.mp4) go in as videos."""
    import json
    if len(paths) == 1:   # a poster: Telegram media groups need 2-10 items
        if str(paths[0]).endswith(".mp4"): return video(paths[0], caption)
        with pathlib.Path(paths[0]).open("rb") as f:
            return _send("sendPhoto", {"caption": caption[:1000]}, {"photo": f})
    media = [{"type": "video" if str(p).endswith(".mp4") else "photo", "media": f"attach://p{i}",
              **({"caption": caption[:1000]} if i == 0 else {})} for i, p in enumerate(paths[:10])]
    files = {f"p{i}": pathlib.Path(p).open("rb") for i, p in enumerate(paths[:10])}
    try:
        return _send("sendMediaGroup", {"media": json.dumps(media)}, files)
    finally:
        for f in files.values(): f.close()


APPROVALS = f"{PUBLIC}/dash/approve.html"
FLUSH_MIN = 20
ICON = {"needs": "✅", "no": "⛔", "failed": "⚠️", "pitch": "💡", "alert": "⚠️", "done": "🎞"}


def notify(text, item_id=None, kind="needs"):
    """Queue one line for the owner's next digest (never sends by itself)."""
    from . import db
    with db.conn() as c:
        c.execute("INSERT INTO outbox(ts, kind, item_id, text) VALUES(?,?,?,?)", (db.iso(db.now()), kind, item_id, text[:240]))


def flush(force=False):
    """Send what's queued as ONE short message with the Approvals link — at most every FLUSH_MIN minutes."""
    import datetime as dt
    from . import db
    now = db.now(); last = db.setting("outbox_last")
    if not force and last and now < db.parse(last) + dt.timedelta(minutes=FLUSH_MIN): return False
    with db.conn() as c:
        rows = [dict(r) for r in c.execute("SELECT id, kind, item_id, text FROM outbox WHERE sent IS NULL ORDER BY id")]
    if not rows: return False
    latest = {}
    for r in rows: latest[r["item_id"] if r["item_id"] is not None else f"x{r['id']}"] = r   # one line per post: its latest news
    lines = [f"{ICON.get(r['kind'], '•')} {r['text']}" for r in latest.values()]
    more = f"\n…and {len(lines) - 8} more" if len(lines) > 8 else ""
    ok = say(f"🔔 {len(lines)} for you:\n" + "\n".join(lines[:8]) + more + f"\n👉 {APPROVALS}")
    if ok:
        with db.conn() as c:
            c.execute(f"UPDATE outbox SET sent=? WHERE id IN ({','.join('?' * len(rows))})", (db.iso(now), *[r["id"] for r in rows]))
        db.set_setting("outbox_last", db.iso(now))
    return ok
