"""The content library (SQLite): every idea, draft, review verdict and published post, plus the pause switch and job queue.

Item life: idea -> queued -> making -> ready -> publishing -> published
           (side exits: held by the owner, rejected by the committee, failed, removed)
"""
import datetime as dt, json, sqlite3
from zoneinfo import ZoneInfo
from .config import DB, TZ

IST = ZoneInfo(TZ)
SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY, brand TEXT NOT NULL, kind TEXT NOT NULL, topic TEXT, angle TEXT, notes TEXT,
  status TEXT NOT NULL DEFAULT 'idea', slot TEXT, plan_id INTEGER, request TEXT,
  dir TEXT, media TEXT, caption TEXT, facts TEXT, review TEXT, preview_at TEXT,
  ig_media_id TEXT, permalink TEXT, error TEXT, attempts INTEGER DEFAULT 0, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY, request TEXT, brands TEXT, start TEXT, days INTEGER, cadence TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts TEXT, item_id INTEGER, level TEXT, msg TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, item_id INTEGER, action TEXT, status TEXT DEFAULT 'queued',
  created TEXT, started TEXT, finished TEXT, note TEXT, priority INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS dms(comment_id TEXT PRIMARY KEY, item_id INTEGER, brand TEXT, username TEXT, comment TEXT, ts TEXT,
  ok INTEGER, error TEXT);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, item_id INTEGER, text TEXT, sent TEXT);
CREATE INDEX IF NOT EXISTS items_slot ON items(status, slot);
"""


def now():
    return dt.datetime.now(IST).replace(microsecond=0)


def iso(t):
    return t.isoformat(timespec="minutes") if t else None


def parse(s):
    if not s: return None
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=IST)


def conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30); c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL"); c.executescript(SCHEMA)
    if "priority" not in [r[1] for r in c.execute("PRAGMA table_info(jobs)")]:
        c.execute("ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 0")
    if "pid" not in [r[1] for r in c.execute("PRAGMA table_info(jobs)")]:
        c.execute("ALTER TABLE jobs ADD COLUMN pid INTEGER")   # the process making it (jobs run in their own processes)
    cols = [r[1] for r in c.execute("PRAGMA table_info(items)")]
    if "draft" not in cols: c.execute("ALTER TABLE items ADD COLUMN draft TEXT")        # what a rejected item looked like (files/script)
    if "override" not in cols: c.execute("ALTER TABLE items ADD COLUMN override INTEGER DEFAULT 0")   # the owner overruled the committee
    if "likeness" not in cols: c.execute("ALTER TABLE items ADD COLUMN likeness INTEGER DEFAULT 0")   # owner allowed AI-drawn real people
    if "autopost" not in cols: c.execute("ALTER TABLE items ADD COLUMN autopost INTEGER DEFAULT 0")   # owner: post the moment it is ready
    if "motion" not in cols: c.execute("ALTER TABLE items ADD COLUMN motion TEXT")   # carousels: 'animated' | 'static' (NULL = pick at make)
    if "cta" not in cols: c.execute("ALTER TABLE items ADD COLUMN cta TEXT")   # {"keyword", "dm", "offer"}: comment KEYWORD -> we DM them
    if "look" not in cols: c.execute("ALTER TABLE items ADD COLUMN look TEXT")   # carousels: 'news' (real official images) | 'designed' | NULL = auto
    return c


def log(item_id, msg, level="info"):
    with conn() as c:
        c.execute("INSERT INTO events(ts,item_id,level,msg) VALUES(?,?,?,?)", (iso(now()), item_id, level, msg))


def add(brand, kind, topic, slot=None, angle="", notes="", plan_id=None, request=""):
    with conn() as c:
        cur = c.execute("INSERT INTO items(brand,kind,topic,angle,notes,slot,plan_id,request,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (brand, kind, topic, angle, notes, iso(slot), plan_id, request, iso(now()), iso(now())))
        return cur.lastrowid


def get(item_id):
    with conn() as c:
        r = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return dict(r) if r else None


def update(item_id, **kw):
    kw["updated"] = iso(now())
    for k, v in kw.items():
        if isinstance(v, (dict, list)): kw[k] = json.dumps(v, ensure_ascii=False)
    with conn() as c:
        c.execute(f"UPDATE items SET {', '.join(k + '=?' for k in kw)} WHERE id=?", (*kw.values(), item_id))


def items(where="1=1", args=(), order="slot IS NULL, slot, id"):
    with conn() as c:
        return [dict(r) for r in c.execute(f"SELECT * FROM items WHERE {where} ORDER BY {order}", args)]


def setting(key, default=None):
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_setting(key, value):
    with conn() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))


def pick_motion(brand, pending=()):
    """Animated or still for the brand's next carousel: keeps its recent carousels near the owner's share of animated ones
    (setting animated_share, default half: they alternate). pending = choices already made in a plan not yet booked."""
    share = setting("animated_share", 0)   # owner, 28 Sep: carousels are still unless the owner asks for animation
    recent = list(reversed(pending)) + [r["motion"] for r in items(
        "brand=? AND kind='carousel' AND motion IN ('animated','static') AND status NOT IN ('removed','declined')", (brand,),
        order="COALESCE(slot, created) DESC, id DESC")]
    recent = recent[:6]
    if share <= 0: return "static"
    if share >= 1: return "animated"
    if not recent: return "animated" if share >= 0.5 else "static"
    frac = recent.count("animated") / len(recent)
    return "animated" if frac < share or (frac == share and recent[0] == "static") else "static"


def paused():
    """(True, until, reason) while the pause switch is on. An expired pause switches itself off."""
    p = setting("pause")
    if not p: return False, None, None
    until = parse(p.get("until"))
    if until and until <= now():
        set_setting("pause", None); log(None, "pause expired, studio resumed")
        return False, None, None
    return True, until, p.get("reason", "")


def enqueue(item_id, action="make", priority=0):
    """Queue a job. priority 10 = the owner asked for it now (jumps the scheduled week); 0 = scheduled."""
    with conn() as c:
        busy = c.execute("SELECT id FROM jobs WHERE item_id=? AND action=? AND status IN ('queued','running')", (item_id, action)).fetchone()
        if busy:
            c.execute("UPDATE jobs SET priority=MAX(priority,?) WHERE id=?", (priority, busy["id"])); return None
        return c.execute("INSERT INTO jobs(item_id,action,created,priority) VALUES(?,?,?,?)", (item_id, action, iso(now()), priority)).lastrowid


def next_job():
    """Claim the next job atomically (several lanes run side by side): the owner's asks first, and among them whatever posts
    in the next 12 hours; then the fast formats (poster, story, carousel), reels last — and only one reel at a time while
    anything else is waiting."""
    soon = iso(now() + dt.timedelta(hours=12))
    with conn() as c:
        r = c.execute("""UPDATE jobs SET status='running', started=? WHERE id = (
                SELECT j.id FROM jobs j JOIN items i ON i.id = j.item_id WHERE j.status = 'queued'
                ORDER BY j.priority DESC,
                         CASE WHEN i.slot IS NOT NULL AND i.slot <= ? THEN 0 ELSE 1 END,
                         CASE WHEN i.kind = 'reel' AND EXISTS (SELECT 1 FROM jobs r JOIN items ri ON ri.id = r.item_id
                                                               WHERE r.status = 'running' AND ri.kind = 'reel') THEN 1 ELSE 0 END,
                         CASE i.kind WHEN 'poster' THEN 0 WHEN 'story' THEN 1 WHEN 'carousel' THEN 2 ELSE 3 END,
                         i.slot IS NULL, i.slot, j.id LIMIT 1) RETURNING *""", (iso(now()), soon)).fetchone()
    return dict(r) if r else None


PRIORITY = {"top": 50, "high": 20, "normal": 10, "low": 0}
PRIORITY_NAME = {50: "🔥 top", 20: "high", 10: "normal", 0: "low"}


def queue():
    """Queued jobs in the order the worker will take them: [{item_id, job_id, priority, pos}] (1 = next)."""
    soon = iso(now() + dt.timedelta(hours=12))
    with conn() as c:
        rows = c.execute("""SELECT j.id, j.item_id, j.priority FROM jobs j JOIN items i ON i.id = j.item_id WHERE j.status = 'queued'
                            ORDER BY j.priority DESC, CASE WHEN i.slot IS NOT NULL AND i.slot <= ? THEN 0 ELSE 1 END,
                                     CASE i.kind WHEN 'poster' THEN 0 WHEN 'story' THEN 1 WHEN 'carousel' THEN 2 ELSE 3 END,
                                     i.slot IS NULL, i.slot, j.id""", (soon,)).fetchall()
    return [{"job_id": r[0], "item_id": r[1], "priority": r[2], "pos": k + 1} for k, r in enumerate(rows)]


def alive(pid):
    import os
    if not pid: return False
    try:
        os.kill(int(pid), 0); return True
    except (OSError, ValueError):
        return False


def get_job(job_id):
    with conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(r) if r else None


def set_job_pid(job_id, pid):
    with conn() as c:
        c.execute("UPDATE jobs SET pid=? WHERE id=?", (pid, job_id))


def running_alive():
    """Jobs being made right now by a live process."""
    with conn() as c:
        rows = c.execute("SELECT id, pid FROM jobs WHERE status='running'").fetchall()
    return [r["id"] for r in rows if alive(r["pid"])]


def recover_jobs(grace_min=2):
    """Jobs marked running whose process is gone (a crash, or an old worker): back to the queue, their item too. A job claimed
    in the last `grace_min` minutes without a pid yet is left alone (its process is starting)."""
    cut = iso(now() - dt.timedelta(minutes=grace_min)); n = 0
    with conn() as c:
        for r in c.execute("SELECT id, item_id, pid, started FROM jobs WHERE status='running'").fetchall():
            if alive(r["pid"]) or (not r["pid"] and (r["started"] or "") > cut): continue
            c.execute("UPDATE jobs SET status='queued', started=NULL, pid=NULL WHERE id=?", (r["id"],))
            c.execute("UPDATE items SET status='queued' WHERE id=? AND status='making'", (r["item_id"],)); n += 1
    return n


def finish_job(job_id, ok, note=""):
    with conn() as c:
        c.execute("UPDATE jobs SET status=?, finished=?, note=? WHERE id=?", ("done" if ok else "failed", iso(now()), note[:2000], job_id))
