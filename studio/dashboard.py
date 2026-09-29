"""The owner's live dashboard: the week's calendar, the pipeline, what needs a decision, and what went live.

`studio dash` writes /opt/studio/dash/index.html (a timer runs it every minute). Caddy serves it at
https://studio.example.com/dash/ behind a password (it lists unpublished drafts). The page re-loads itself every 60 s.
"""
import datetime as dt, html, json, pathlib, shutil
from . import db
from .config import BRANDS, ROOT

OUT = ROOT / "dash"
PV = OUT / "p"          # preview pages and copies of unpublished drafts (behind the dashboard password)
COL = {"sportsdesk": "#E6007E", "techdesk": "#FF5B1F", "bizdesk": "#F5B800"}
ICON = {"reel": "🎬", "carousel": "🗂️", "story": "⭕", "poster": "🖼️"}
STATUS = {  # label, colour
    "idea": ("planned", "#6b7280"), "suggested": ("pitched", "#6b7280"), "queued": ("queued", "#3b82f6"),
    "making": ("making", "#f59e0b"), "ready": ("ready", "#22c55e"), "approved": ("posting", "#16a34a"),
    "held": ("waiting for you", "#a855f7"), "publishing": ("publishing", "#14b8a6"), "published": ("live", "#15803d"),
    "rejected": ("committee said no", "#ef4444"), "failed": ("failed", "#dc2626"), "expired": ("expired", "#9ca3af"),
    "archived": ("archived", "#9ca3af"), "declined": ("declined", "#9ca3af"), "removed": ("removed", "#9ca3af")}
E = html.escape


def chip(status):
    label, colour = STATUS.get(status, (status, "#6b7280"))
    pulse = " pulse" if status in ("making", "publishing") else ""
    return f'<span class="chip{pulse}" style="--c:{colour}">{E(label)}</span>'


def files_of(it):
    """What the post looks like: its media, or for a draft the committee stopped, the draft's files (copied under the
    dashboard so they stay behind its password). Returns [(url relative to the dashboard or absolute, is_video)]."""
    media = json.loads(it["media"] or "[]")
    if media: return [(m, m.endswith(".mp4")) for m in media]
    out, d = [], PV / str(it["id"])
    for f in json.loads(it.get("draft") or "{}").get("files", []):
        src = pathlib.Path(f)
        if not src.exists(): continue
        d.mkdir(parents=True, exist_ok=True); dst = d / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size: shutil.copy(src, dst); dst.chmod(0o644)
        out.append((f"p/{it['id']}/{src.name}", src.suffix == ".mp4"))
    return out


def notes_of(item_id, n=25):
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT ts, level, msg FROM events WHERE item_id=? ORDER BY id DESC LIMIT ?", (item_id, n))][::-1]


def preview(it):
    """dash/p/<id>.html: the whole post (slides or video, drafts included), its caption, the committee's verdicts and notes."""
    rel = lambda u: u if u.startswith("http") else "../" + u
    media = "".join(f'<video src="{E(rel(u))}#t=0.1" controls playsinline preload="metadata"></video>' if v else
                    f'<a href="{E(rel(u))}" target="_blank"><img src="{E(rel(u))}" loading="lazy"></a>' for u, v in files_of(it))
    dr = json.loads(it.get("draft") or "{}")
    if not media: media = f'<pre class="script">{E(dr.get("script") or "Nothing designed yet.")}</pre>'
    verdicts = "".join(f'<li><b>{E(v.get("role", ""))}</b> {E(v.get("verdict", ""))} — {E(v.get("summary", ""))}</li>'
                       for v in json.loads(it.get("review") or "[]"))
    log = "".join(f'<li class="{E(e["level"])}"><small>{E(e["ts"][5:16].replace("T", " "))}</small> {E(e["msg"])}</li>' for e in notes_of(it["id"]))
    cap = it.get("caption") or dr.get("caption") or ""
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>#{it['id']} preview</title><style>
:root{{--bg:#0f1115;--panel:#171a21;--ink:#e8eaf0;--dim:#9aa3b2}} body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif}}
main{{max-width:1100px;margin:auto;padding:16px;display:grid;gap:16px}} a{{color:#7dd3fc}} h1{{font-size:18px;margin:0}}
.media{{display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:6px}}
.media img,.media video{{height:min(70vh,560px);border-radius:10px;scroll-snap-align:start;flex:none;background:#000}}
section{{background:var(--panel);border-radius:10px;padding:12px}} pre{{white-space:pre-wrap;margin:0;font:13px/1.5 system-ui}}
ul{{margin:0;padding-left:18px}} li.warn{{color:#fcd34d}} li.error{{color:#fca5a5}} li.note{{color:var(--dim)}} .why{{color:#fca5a5}}
.acts button{{font:600 12px system-ui;padding:6px 11px;border-radius:7px;border:1px solid #3a4150;background:#232834;color:var(--ink);margin:2px}}
</style></head><body><main>
<p><a href="../">← dashboard</a></p>
<h1>#{it['id']} {E(BRANDS[it['brand']]['name'])} {E(it['kind'])} · {chip(it['status'])}</h1>
<div>{E(it.get('topic') or '')}</div>{f'<div class="why">{E(it["error"])}</div>' if it.get("error") else ''}
{buttons(it)}
<div class="media">{media}</div>
<section><h2>Caption</h2><pre>{E(cap) or '—'}</pre></section>
<section><h2>Committee</h2><ul>{verdicts or '<li>not reviewed yet</li>'}</ul></section>
<section><h2>What happened</h2><ul>{log}</ul></section>
</main><div id="toast" style="position:fixed;left:50%;bottom:18px;transform:translateX(-50%);background:#111827;color:#e8eaf0;padding:10px 14px;border-radius:10px;display:none"></div>
<script>
document.addEventListener("click", async (e) => {{
  const b = e.target.closest(".acts button"); if (!b) return;
  if (b.dataset.c === "1" && !confirm(b.textContent + " #" + b.dataset.id + "?")) return;
  b.disabled = true; const t = document.getElementById("toast"); t.style.display = "block"; t.textContent = "Working…";
  try {{ const r = await fetch("../api/act", {{method: "POST", headers: {{"Content-Type": "application/json", "X-Studio": "1"}},
          body: JSON.stringify({{id: +b.dataset.id, action: b.dataset.a}})}}); const j = await r.json();
        t.textContent = (j.ok ? "✅ " : "⚠️ ") + (j.output || j.error || ""); }} catch (err) {{ t.textContent = "⚠️ " + err; }}
  setTimeout(() => location.reload(), 2500);
}});
</script></body></html>"""
    PV.mkdir(parents=True, exist_ok=True)
    tmp = PV / f"{it['id']}.html.tmp"; tmp.write_text(page); tmp.replace(PV / f"{it['id']}.html")


def thumb(it):
    fs = files_of(it)
    if not fs: return ""
    m = fs[0][0]
    link = it["permalink"] or f"p/{it['id']}.html"
    if m.endswith(".mp4"):   # a reel's hook is on frame 0; an animated slide has settled by 5 s
        t = 5 if it["kind"] == "carousel" else 1
        return f'<a href="{E(link)}" target="_blank"><video src="{E(m)}#t={t}" preload="metadata" muted playsinline></video></a>'
    return f'<a href="{E(link)}" target="_blank"><img src="{E(m)}" loading="lazy"></a>'


BUTTONS = {  # status -> [(action, label, confirm?)]
    "rejected": [("retry", "Retry", False), ("override", "Post anyway", True), ("remove", "Remove", True)],
    "failed": [("retry", "Retry", False), ("override", "Post anyway", True), ("remove", "Remove", True)],
    "expired": [("retry", "Retry", False), ("remove", "Remove", True)],
    "held": [("post", "Post now", True), ("release", "Post at its time", False), ("retry", "Re-make", True), ("remove", "Remove", True)],
    "ready": [("post", "Post now", True), ("hold", "Hold", False)],
    "approved": [("post", "Post now", True), ("hold", "Hold", False)],
    "idea": [("top", "🔥 Make next", False), ("make", "Make now", False), ("hold", "Hold", False), ("remove", "Remove", True)],
    "queued": [("top", "🔥 Make next", False), ("low", "⬇ Later", False), ("when-ready", "Post when ready", False), ("hold", "Hold", False),
               ("remove", "Remove", True)],
    "making": [("when-ready", "Post when ready", False), ("hold", "Hold", False)],
    "suggested": [("accept", "Yes, make it", False), ("decline", "No", False)],
}


def buttons(it):
    bs = list(BUTTONS.get(it["status"], []))
    if it["status"] in ("rejected", "failed") and not json.loads(it.get("draft") or "{}").get("files"):   # nothing designed yet
        bs = [("override", "Make anyway", True) if a == "override" else (a, l, c) for a, l, c in bs]
    if it["kind"] == "carousel" and it.get("look") != "news" and it["status"] in ("idea", "queued", "suggested", "ready", "approved", "held"):
        media = json.loads(it.get("media") or "[]")
        moving = any(u.endswith(".mp4") for u in media) if media else it.get("motion") == "animated"   # what it IS, once made
        bs.append(("still", "Make still", False) if moving else ("animate", "Animate", False))
    return ('<div class="acts">' + "".join(f'<button data-id="{it["id"]}" data-a="{a}" data-c="{int(c)}">{E(l)}</button>' for a, l, c in bs)
            + "</div>") if bs else ""


QUEUE = {}   # item_id -> {"pos", "priority"} — filled by build() each minute


def queue_note(it):
    if it["status"] == "making":
        return f'<div class="q making">⚙️ being made now</div>'
    q = QUEUE.get(it["id"])
    if it["status"] != "queued" or not q: return ""
    name = db.PRIORITY_NAME.get(q["priority"], str(q["priority"]))
    return f'<div class="q{" top" if q["priority"] >= 50 else ""}">#{q["pos"]} in the queue · priority {E(name)}</div>'


def card(it, show_day=False):
    slot = db.parse(it["slot"]) if it["slot"] else None
    when = (slot.strftime("%a %d %b · %H:%M") if show_day else slot.strftime("%H:%M")) if slot else "when you say"
    extra = ""
    if it["status"] in ("rejected", "failed", "held") and it["error"]:
        extra = f'<div class="why">{E(it["error"][:220])}</div>'
    live = f' · <a href="{E(it["permalink"])}" target="_blank">open ↗</a>' if it["permalink"] else ""
    if it["status"] not in ("idea", "queued", "suggested"): live += f' · <a href="p/{it["id"]}.html">preview ↗</a>'
    if it.get("cta"):
        from . import dm
        c = json.loads(it["cta"]); live += f' · 💬 {E(c.get("keyword", ""))} → {dm.count(it["id"])} DMs'
    topic = it["topic"] if it["topic"] and it["topic"] != "auto" else "auto: the day's freshest story"
    motion = (" · 📰 news" if it.get("look") == "news" else {"animated": " · 🎞 animated", "static": " · still"}.get(it.get("motion"), "")) \
        if it["kind"] == "carousel" else ""
    return (f'<div class="card" style="--b:{COL[it["brand"]]}">{thumb(it)}<div class="meta"><div class="top">'
            f'<b>#{it["id"]}</b> {ICON.get(it["kind"], "")} {E(it["kind"])}{motion} · {E(when)} {chip(it["status"])}</div>'
            f'<div class="topic">{E(topic)}</div>'
            f'<div class="angle">{E((it["angle"] or "")[:160])}{live}</div>{queue_note(it)}{extra}{buttons(it)}</div></div>')


def nav(active, waiting):
    tab = lambda href, label, key: f'<a class="tab{" on" if key == active else ""}" href="{href}">{label}</a>'
    return (f'<nav class="tabs">{tab("index.html", "📅 Calendar", "cal")}'
            f'{tab("approve.html", f"✅ Approvals <b>{waiting}</b>" if waiting else "✅ Approvals", "ok")}'
            f'{tab("auto.html", "⚙️ Automation", "auto")}</nav>')


HERMES = pathlib.Path("/home/studio/.hermes")
DOW = {"*": "daily", "0": "Sundays", "7": "Sundays", "1": "Mondays", "2": "Tuesdays", "3": "Wednesdays", "4": "Thursdays",
       "5": "Fridays", "6": "Saturdays", "1-5": "weekdays"}


def human_cron(expr):
    """'30 9,14,19 * * *' -> 'daily at 09:30, 14:30, 19:30' (simple patterns; anything else is shown as written)."""
    try:
        mi, hr, dom, mon, dow = expr.split()
        if dom == "*" and mon == "*" and mi.isdigit() and all(h.isdigit() for h in hr.split(",")) and dow in DOW:
            return f"{DOW[dow]} at " + ", ".join(f"{int(h):02d}:{int(mi):02d}" for h in hr.split(","))
        if mi.startswith("*/") and hr == "*": return f"every {mi[2:]} min"
    except ValueError:
        pass
    return expr


def when_str(v):
    if v in (None, ""): return "—"
    try:
        t = dt.datetime.fromtimestamp(float(v), db.IST) if isinstance(v, (int, float)) or str(v).replace(".", "").isdigit() else db.parse(str(v))
        return t.astimezone(db.IST).strftime("%a %d %b %H:%M")
    except Exception:
        return str(v)[:16]


def hermes_jobs():
    try:
        d = json.loads((HERMES / "cron" / "jobs.json").read_text()); jobs = d.get("jobs", d)
        return list(jobs.values()) if isinstance(jobs, dict) else list(jobs)
    except Exception:
        return []


def hermes_runs(limit=12):
    import sqlite3
    try:
        c = sqlite3.connect(f"file:{HERMES / 'cron' / 'executions.db'}?mode=ro", uri=True)
        rows = c.execute("SELECT job_id, status, started_at, finished_at, error FROM executions ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        c.close(); return rows
    except Exception:
        return []


def build_auto(now, waiting):
    names = {j.get("id"): j.get("name") for j in hermes_jobs()}
    jobs = "".join(
        f'<tr><td><b>{E(j.get("name") or j.get("id"))}</b><br><small>{E((j.get("prompt") or "")[:140])}</small></td>'
        f'<td>{E(human_cron((j.get("schedule") or {}).get("expr", "") if isinstance(j.get("schedule"), dict) else str(j.get("schedule"))))}</td>'
        f'<td>{E(when_str(j.get("next_run_at")))}</td><td>{E(when_str(j.get("last_run_at")))} '
        f'<span class="st {E(str(j.get("last_status") or ""))}">{E(str(j.get("last_status") or "—"))}</span></td>'
        f'<td>{"on" if j.get("enabled") else "paused"}</td></tr>' for j in hermes_jobs()) or '<tr><td colspan=5 class="empty">no Hermes jobs</td></tr>'
    runs = "".join(f'<li><b>{E(names.get(r[0], r[0]))}</b> {E(when_str(r[2]))} → <span class="st {E(str(r[1]))}">{E(str(r[1]))}</span>'
                   f'{" — " + E(str(r[4])[:160]) if r[4] else ""}</li>' for r in hermes_runs()) or '<li class="empty">no runs yet</li>'
    with db.conn() as c:
        dms_today = c.execute("SELECT COUNT(*) FROM dms WHERE ok=1 AND ts >= ?", (db.iso(now.replace(hour=0, minute=0)),)).fetchone()[0]
        glog = [dict(r) for r in c.execute("SELECT ts, level, msg FROM events WHERE item_id IS NULL ORDER BY id DESC LIMIT 15")]
    making = db.items("status='making'")
    studio_rows = [
        ("Studio check", "every 5 min", "publishes due posts, starts making posts 14 h before their time, answers comment keywords with DMs, "
         "expires stale news", f"last run {when_str(db.setting('last_tick'))}"),
        ("Worker", "always on (3 lanes)", "makes posts: research, writing, committee, voice, render",
         f"making now: {', '.join('#' + str(i['id']) for i in making) or 'nothing'}"),
        ("Comment → DM", "every 5 min", "DMs everyone who comments a post's keyword", f"{dms_today} DMs sent today"),
        ("Morning line-up", "daily at 08:00", "today's posts to Telegram", f"last {db.setting('digest') or '—'}"),
        ("Token refresh", "daily", "keeps the Instagram logins alive", f"last {db.setting('last_refresh') or '—'}"),
        ("Dashboard", "every minute", "rebuilds these pages", f"updated {now:%H:%M}")]
    srows = "".join(f"<tr><td><b>{E(a)}</b><br><small>{E(c_)}</small></td><td>{E(b)}</td><td colspan=3>{E(d)}</td></tr>" for a, b, c_, d in studio_rows)
    scout = ""
    for r in (db.setting("scout_runs", []) or [])[:12]:
        ideas = []
        for i in r.get("ids", []):
            it = db.get(i)
            if it: ideas.append(f'<li>#{i} {E(BRANDS[it["brand"]]["name"])} {E(it["kind"])} — {E(it["topic"] or "")} {chip(it["status"])}</li>')
        scope = (BRANDS[r["brand"]]["name"] if r.get("brand") in BRANDS else "all accounts") + (f' · “{r["topic"]}”' if r.get("topic") else "")
        scout += (f'<div class="run"><div><b>{E(when_str(r.get("ts")))}</b> · {E(scope)} · by {E(r.get("by", ""))} · '
                  f'<span class="st">{E(r.get("status", ""))}</span></div><ul>{"".join(ideas) or "<li class=empty>no ideas</li>"}</ul></div>')
    pitches = db.items("request LIKE 'suggested%' AND created >= ?", (db.iso(now - dt.timedelta(days=3)),), order="id DESC")[:25]
    prow = "".join(f'<li>#{i["id"]} {E(BRANDS[i["brand"]]["name"])} {E(i["kind"])} — {E(i["topic"] or "")} {chip(i["status"])}'
                   f'<br><small>{E((i["request"] or "")[:160])}</small></li>' for i in pitches) or '<li class="empty">none</li>'
    log = "".join(f'<li class="{E(e["level"])}"><small>{E(e["ts"][5:16].replace("T", " "))}</small> {E(e["msg"][:200])}</li>' for e in glog)
    opts = '<option value="all">All accounts</option>' + "".join(f'<option value="{b}">{E(BRANDS[b]["name"])}</option>' for b in BRANDS)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Automation</title><style>
:root{{--bg:#0f1115;--panel:#171a21;--ink:#e8eaf0;--dim:#9aa3b2;--line:#262b36}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:1000px;margin:auto;padding:12px 12px 60px;display:grid;grid-template-columns:minmax(0,1fr);gap:16px}}
.tabs{{display:flex;gap:6px;padding:12px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5;flex-wrap:wrap}}
.tab{{padding:8px 14px;border-radius:99px;color:var(--dim);text-decoration:none;border:1px solid var(--line)}} .tab.on{{color:var(--ink);background:#232834}}
.tab b{{background:#ef4444;color:#fff;border-radius:99px;padding:0 7px;margin-left:4px;font-size:12px}}
section{{background:var(--panel);border-radius:12px;padding:14px;min-width:0}} h2{{margin:0 0 8px;font-size:16px}} .note{{color:var(--dim);margin:0 0 10px;font-size:13px}}
.wrap{{overflow-x:auto}} table{{width:100%;border-collapse:collapse;min-width:620px}} td,th{{text-align:left;padding:8px 6px;border-top:1px solid var(--line);vertical-align:top}}
th{{color:var(--dim);font-weight:600;font-size:12px}} small{{color:var(--dim)}} ul{{margin:4px 0;padding-left:18px}} li{{margin:3px 0}}
.st{{font-size:12px;padding:0 7px;border-radius:99px;border:1px solid #3a4150}} .st.ok,.st.done,.st.succeeded,.st.completed{{color:#86efac;border-color:#166534}}
.st.error,.st.failed{{color:#fca5a5;border-color:#7f1d1d}}
.chip{{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;border:1px solid var(--c);color:var(--c);margin-left:4px}}
.pulse{{animation:p 1.4s infinite}} @keyframes p{{50%{{opacity:.35}}}}
form{{display:grid;grid-template-columns:1fr 2fr 90px auto;gap:8px}} @media(max-width:640px){{form{{grid-template-columns:1fr 1fr}} form input{{grid-column:1/3}}}}
select,input,button{{font:14px system-ui;padding:10px;border-radius:9px;border:1px solid #3a4150;background:#11141a;color:var(--ink)}}
button{{background:#16a34a;border-color:#16a34a;color:#fff;font-weight:700;cursor:pointer}} button:disabled{{opacity:.5}}
.run{{border-top:1px solid var(--line);padding:8px 0}} .empty{{color:#4b5563}} li.warn{{color:#fcd34d}} li.error{{color:#fca5a5}}
#toast{{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);background:#111827;border:1px solid #374151;color:var(--ink);
  padding:12px 16px;border-radius:12px;max-width:92vw;display:none;font-size:14px;z-index:9}}
</style></head><body>
{nav("auto", waiting)}
<main>
<section><h2>🔎 Scout now</h2><p class="note">Hermes searches the web for fresh stories and pitches them — they arrive on Telegram and the ✅ Approvals tab
for your Yes/No; nothing is made before you say yes. Leave the topic empty for "whatever is hot right now".</p>
<form id="scout"><select name="brand">{opts}</select><input name="topic" maxlength="160" placeholder="Topic (optional) — e.g. IPL auction, AI phones, D2C brands">
<select name="n"><option>3</option><option selected>5</option><option>10</option></select><button type="submit">Scout</button></form></section>
<section><h2>🗓 Hermes' scheduled jobs</h2><p class="note">Run by Hermes on its own clock (IST). Change them by asking Hermes on Telegram.</p>
<div class="wrap"><table><tr><th>Job</th><th>When</th><th>Next run</th><th>Last run</th><th></th></tr>{jobs}</table></div>
<h2 style="margin-top:14px">Recent runs</h2><ul>{runs}</ul></section>
<section><h2>⚙️ The studio's own automation</h2><div class="wrap"><table><tr><th>What</th><th>When</th><th colspan=3>Now</th></tr>{srows}</table></div></section>
<section><h2>🔎 Scout runs from here</h2>{scout or '<p class="empty">none yet — use Scout now above</p>'}</section>
<section><h2>💡 All pitches (last 3 days)</h2><p class="note">From the scheduled scout and from Scout now. Decide on the ✅ Approvals tab.</p><ul>{prow}</ul></section>
<section><h2>📜 Studio log</h2><ul>{log}</ul></section>
</main><div id="toast"></div>
<script>
setTimeout(function tick(){{ if (!document.activeElement || document.activeElement.tagName !== "INPUT") location.reload(); else setTimeout(tick, 15000); }}, 60000);
document.getElementById("scout").addEventListener("submit", async (e) => {{
  e.preventDefault(); const f = e.target, b = f.querySelector("button"); b.disabled = true;
  const t = document.getElementById("toast"); t.style.display = "block"; t.textContent = "Starting the scout…";
  try {{ const r = await fetch("api/scout", {{method: "POST", headers: {{"Content-Type": "application/json", "X-Studio": "1"}},
          body: JSON.stringify({{brand: f.brand.value, topic: f.topic.value, n: +f.n.value}})}}); const j = await r.json();
        t.textContent = (j.ok ? "✅ " : "⚠️ ") + (j.output || j.error || ""); }} catch (err) {{ t.textContent = "⚠️ " + err; }}
  setTimeout(() => location.reload(), 4000);
}});
</script></body></html>"""
    tmp = OUT / "auto.html.tmp"; tmp.write_text(page); tmp.replace(OUT / "auto.html")


def waiting_items(now):
    held = db.items("status='held' OR (status='ready' AND slot IS NULL)", order="slot IS NULL, slot, id")
    no = db.items("status IN ('rejected','failed') AND updated >= ?", (db.iso(now - dt.timedelta(days=3)),), order="updated DESC")
    soon = db.items("status IN ('ready','approved') AND slot IS NOT NULL AND slot <= ?", (db.iso(now + dt.timedelta(hours=24)),), order="slot")
    pitches = db.items("status='suggested'", order="id DESC")
    return held, no, soon, pitches


def review_card(it, acts, now):
    """One post, big: swipeable slides / the video / the script, caption, why it's here, and the decision buttons."""
    fs = files_of(it); dr = json.loads(it.get("draft") or "{}")
    per_slide = it["kind"] == "carousel" and it.get("look") != "news" and it["status"] in ("held", "ready", "approved") and len(fs) > 1

    def slide(k, u, v):
        body = (f'<video src="{E(u)}#t=0.1" controls playsinline preload="metadata"></video>' if v else
                f'<img src="{E(u)}" loading="lazy" alt="slide {k + 1}">')
        btn = (f'<div class="acts sl"><button data-id="{it["id"]}" data-a="animate_slide" data-s="{k + 1}" data-c="0">🎞 Animate slide {k + 1}</button></div>'
               if per_slide and not v else f'<div class="sl tag">🎞 slide {k + 1} animated</div>' if per_slide else "")
        return f'<figure>{body}{btn}</figure>'
    media = "".join(slide(k, u, v) for k, (u, v) in enumerate(fs))
    if not media:
        text = dr.get("script") or (f"Pitch: {it.get('angle') or ''}\n{it.get('request') or ''}" if it["status"] == "suggested" else "Nothing designed yet.")
        media = f'<pre class="script">{E(text)}</pre>'
    slot = db.parse(it["slot"]) if it.get("slot") else None
    when = ("posts " + (f"at {slot:%a %d %b %H:%M}" if slot > now else "as soon as approved (its time has passed)")) if slot else "no time set"
    verdicts = " ".join(f'<span class="v {E(v.get("verdict", ""))}">{E(v.get("role", ""))} {"✓" if v.get("verdict") == "pass" else "✎" if v.get("verdict") == "fix" else "✗"}</span>'
                        for v in json.loads(it.get("review") or "[]"))
    cap = it.get("caption") or dr.get("caption") or ""
    kind = it["kind"] + (" · 📰 news" if it.get("look") == "news" else " · 🎞 animated" if any(u.endswith(".mp4") for u, _ in fs) and it["kind"] == "carousel" else "")
    btns = "".join(f'<button class="{cls}" data-id="{it["id"]}" data-a="{a}" data-c="{int(c)}">{E(l)}</button>' for a, l, c, cls in acts)
    if it["status"] in ("held", "ready", "approved"):   # pick a time (IST) and approve it for then
        slot_t = db.parse(it["slot"]) if it.get("slot") else None
        base = slot_t if slot_t and slot_t > now else now + dt.timedelta(hours=1)
        base = (base + dt.timedelta(minutes=(15 - base.minute % 15) % 15)).replace(second=0, microsecond=0)
        label = "🗓 Move to this time" if it["status"] in ("ready", "approved") and it.get("slot") else "🗓 Approve for this time"
        btns += (f'<div class="sched"><input type="datetime-local" value="{base:%Y-%m-%dT%H:%M}" min="{now:%Y-%m-%dT%H:%M}" step="300">'
                 f'<button data-id="{it["id"]}" data-a="schedule" data-c="0">{label}</button></div>')
    count = f'<span class="count">{len(fs)} slides — swipe →</span>' if len(fs) > 1 else ""
    why = f'<div class="why">{E(it["error"])}</div>' if it.get("error") else ""
    topic = it.get("topic") if it.get("topic") not in (None, "", "auto") else "auto: the day's freshest story"
    return (f'<article class="rev" style="--b:{COL[it["brand"]]}" id="i{it["id"]}"><div class="rhead"><b>#{it["id"]}</b> '
            f'{E(BRANDS[it["brand"]]["name"])} · {E(kind)} {chip(it["status"])}<span class="when">{E(when)}</span></div>'
            f'<h3>{E(topic)}</h3>{why}'
            f'<div class="strip">{media}</div>{count}'
            f'<details{" open" if cap else ""}><summary>Caption</summary><pre>{E(cap) or "—"}</pre></details>'
            f'<div class="verdicts">{verdicts}</div><div class="acts big">{btns}</div>'
            f'<a class="more" href="p/{it["id"]}.html">full details ↗</a></article>')


def build_approvals(now):
    held, no, soon, pitches = waiting_items(now)

    def held_acts(it):
        passed = it.get("slot") and db.parse(it["slot"]) <= now
        acts = [("approve", "✅ Approve — post now" if passed or not it.get("slot") else "✅ Approve — post at its time", False, "go"),
                ("post", "Post right now", True, ""), ("retry", "Re-make", True, ""), ("remove", "Remove", True, "bad")]
        if it["kind"] == "carousel" and it.get("look") != "news":
            moving = any(u.endswith(".mp4") for u in json.loads(it.get("media") or "[]"))
            acts.insert(3, ("still", "Make still", False, "") if moving else ("animate", "Animate", False, ""))
        return acts

    def no_acts(it):
        drafted = bool(json.loads(it.get("draft") or "{}").get("files"))
        return [("override", "Post anyway" if drafted else "Make anyway (you approve after)", True, "go"), ("retry", "Retry fresh", False, ""),
                ("remove", "Remove", True, "bad")]
    soon_acts = lambda it: [("hold", "✋ Hold", False, "bad"), ("post", "Post right now", True, "")]
    pitch_acts = lambda it: [("accept", "✅ Yes, make it", False, "go"), ("decline", "No", False, "bad")]

    def part(title, rows, acts, note):
        body = "".join(review_card(it, acts(it), now) for it in rows) or '<p class="empty">Nothing here 🎉</p>'
        return f'<section><h2>{title} <small>{len(rows)}</small></h2><p class="note">{note}</p>{body}</section>'
    waiting = len(held) + len(no) + len(pitches)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Approvals ({waiting})</title><style>
:root{{--bg:#0f1115;--panel:#171a21;--ink:#e8eaf0;--dim:#9aa3b2;--line:#262b36}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:760px;margin:auto;padding:12px 12px 80px;display:grid;grid-template-columns:minmax(0,1fr);gap:18px}}
section,.rev{{min-width:0}} .rev{{overflow:hidden}} h3{{overflow-wrap:anywhere}}
.tabs{{display:flex;gap:6px;padding:12px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}}
.tab{{padding:8px 14px;border-radius:99px;color:var(--dim);text-decoration:none;border:1px solid var(--line)}} .tab.on{{color:var(--ink);background:#232834}}
.tab b{{background:#ef4444;color:#fff;border-radius:99px;padding:0 7px;margin-left:4px;font-size:12px}}
h2{{margin:6px 0 2px;font-size:17px}} h2 small{{color:var(--dim);font-weight:400}} .note{{color:var(--dim);margin:0 0 10px;font-size:13px}}
.rev{{background:var(--panel);border-radius:14px;border-top:4px solid var(--b);padding:12px;margin-bottom:14px}}
.rhead{{font-size:13px;color:var(--dim);display:flex;flex-wrap:wrap;gap:6px;align-items:center}} .rhead b{{color:var(--ink)}}
.when{{margin-left:auto}} h3{{margin:6px 0;font-size:16px}}
.why{{color:#fcd34d;font-size:13px;margin:4px 0 8px}}
.strip{{display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:4px;max-width:100%}}
.strip figure{{margin:0;flex:none;scroll-snap-align:start}} .acts.sl{{margin-top:6px}} .acts.sl button{{flex:none;padding:6px 10px;font-size:12px}}
.sl.tag{{font-size:12px;color:#86efac;margin-top:6px}}
.strip img,.strip video{{width:min(78vw,420px);aspect-ratio:4/5;object-fit:cover;border-radius:10px;scroll-snap-align:start;flex:none;background:#000}}
.strip video{{aspect-ratio:auto;max-height:70vh;object-fit:contain}}
.count{{font-size:12px;color:var(--dim)}} pre{{white-space:pre-wrap;margin:6px 0;font:13px/1.5 system-ui}} .script{{background:#11141a;padding:10px;border-radius:8px;width:100%}}
details{{margin-top:8px}} summary{{cursor:pointer;color:var(--dim)}}
.verdicts{{margin:8px 0 2px;display:flex;flex-wrap:wrap;gap:4px}} .v{{font-size:12px;padding:1px 8px;border-radius:99px;border:1px solid #3a4150;color:var(--dim)}}
.v.fix{{color:#fcd34d;border-color:#8a6d1c}} .v.block{{color:#fca5a5;border-color:#7f1d1d}}
.acts{{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}}
.acts button{{font:600 14px system-ui;padding:11px 16px;border-radius:10px;border:1px solid #3a4150;background:#232834;color:var(--ink);cursor:pointer;flex:1 1 auto}}
.acts button.go{{background:#16a34a;border-color:#16a34a;color:#fff}} .acts button.bad{{color:#fca5a5}}
.sched{{display:flex;gap:8px;flex-wrap:wrap;width:100%}} .sched input{{flex:1 1 180px;font:14px system-ui;padding:10px;border-radius:10px;
  border:1px solid #3a4150;background:#11141a;color:var(--ink);color-scheme:dark}} .sched button{{flex:1 1 180px}}
.acts button:disabled{{opacity:.5}} .more{{display:inline-block;margin-top:8px;font-size:12px;color:#7dd3fc}}
.empty{{color:#4b5563}} .done{{opacity:.35;pointer-events:none}}
#toast{{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);background:#111827;border:1px solid #374151;color:var(--ink);
  padding:12px 16px;border-radius:12px;max-width:92vw;display:none;white-space:pre-wrap;font-size:14px;z-index:9}}
</style></head><body>
{nav("ok", waiting)}
<main>
{part("Needs your OK", held, held_acts, "Made and waiting for you. Approve posts it at its time (or now, if its time has passed).")}
{part("Committee said no", no, no_acts, "The reason is in yellow. Post anyway uses this draft; Make anyway re-makes it without the veto and brings it back here.")}
{part("Hermes' pitches", pitches, pitch_acts, "Stories Hermes found for you.")}
{part("Going out in the next 24 h", soon, soon_acts, "Already approved or auto-posting (veto mode). Hold stops one.")}
</main><div id="toast"></div>
<script>
let busy = false;
setTimeout(function tick(){{ if (!busy && !document.querySelector("video:not([paused])")) location.reload(); else setTimeout(tick, 15000); }}, 90000);
document.addEventListener("click", async (e) => {{
  const b = e.target.closest(".acts button"); if (!b) return;
  if (b.dataset.c === "1" && !confirm(b.textContent + " — #" + b.dataset.id + "?")) return;
  busy = true; const card = b.closest(".rev"); card.querySelectorAll("button").forEach(x => x.disabled = true);
  const t = document.getElementById("toast"); t.style.display = "block"; t.textContent = "Working on #" + b.dataset.id + "…";
  try {{
    const r = await fetch("api/act", {{method: "POST", headers: {{"Content-Type": "application/json", "X-Studio": "1"}},
                                        body: JSON.stringify({{id: +b.dataset.id, action: b.dataset.a, slide: +(b.dataset.s || 0),
                                                               at: (b.parentElement.querySelector("input[type=datetime-local]") || {{}}).value || ""}})}});
    const j = await r.json(); t.textContent = (j.ok ? "✅ " : "⚠️ ") + (j.output || j.error || "");
    if (j.ok && !["animate_slide"].includes(b.dataset.a)) card.classList.add("done"); else card.querySelectorAll("button").forEach(x => x.disabled = false);
    if (j.ok && b.dataset.a === "animate_slide") b.textContent = "🎞 animating…"; else card.querySelectorAll("button").forEach(x => x.disabled = false);
  }} catch (err) {{ t.textContent = "⚠️ " + err; card.querySelectorAll("button").forEach(x => x.disabled = false); }}
  busy = false; setTimeout(() => {{ t.style.display = "none"; }}, 6000);
}});
</script></body></html>"""
    tmp = OUT / "approve.html.tmp"; tmp.write_text(page); tmp.replace(OUT / "approve.html")
    return waiting


def build(days=7):
    now = db.now(); start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    items = db.items("slot >= ? AND slot < ? AND status NOT IN ('removed','declined','archived')",
                     (db.iso(start), db.iso(start + dt.timedelta(days=days))))
    p, until, why = db.paused()
    state = (f'⏸ Paused until {until.strftime("%a %d %b %H:%M") if until else "resumed"}' + (f" — {E(why)}" if why else "")) if p else "▶ Running"
    counts = {}
    for it in db.items("status IN ('queued','making','ready','approved','held','publishing')"): counts[it["status"]] = counts.get(it["status"], 0) + 1
    week = {}
    for it in items: week.setdefault(it["kind"], 0); week[it["kind"]] += 1
    # calendar: one row per day, one column per brand
    rows = []
    for d in range(days):
        day = start + dt.timedelta(days=d); key = day.strftime("%Y-%m-%d")
        cells = []
        for b in BRANDS:
            day_items = [i for i in items if i["brand"] == b and i["slot"].startswith(key)]
            cells.append(f'<td>{"".join(card(i) for i in day_items) or "<span class=empty>—</span>"}</td>')
        rows.append(f'<tr><th>{day.strftime("%a<br>%d %b")}{" <small>today</small>" if d == 0 else ""}</th>{"".join(cells)}</tr>')
    QUEUE.clear(); QUEUE.update({q["item_id"]: q for q in db.queue()})
    making = db.items("status IN ('making','publishing')", order="slot IS NULL, slot, id")
    making += sorted(db.items("status='queued'"), key=lambda i: QUEUE.get(i["id"], {}).get("pos", 999))   # in the order they'll be made
    attention = db.items("status IN ('held','rejected','failed') AND updated >= ?", (db.iso(now - dt.timedelta(days=2)),))
    ready = db.items("status IN ('ready','approved')")
    live = db.items("status='published' AND updated >= ?", (db.iso(now - dt.timedelta(days=3)),), order="updated DESC")
    pitched = db.items("status='suggested'")
    OUT.mkdir(parents=True, exist_ok=True)
    waiting = build_approvals(now)
    try:
        build_auto(now, waiting)
    except Exception as e:
        db.log(None, f"automation page failed: {e}", "warn")

    def section(title, rows_, note="", show_day=True):
        body = "".join(card(i, show_day) for i in rows_) or '<span class="empty">nothing right now</span>'
        return f'<section><h2>{title} <small>{len(rows_)}</small></h2>{f"<p class=note>{note}</p>" if note else ""}<div class="grid">{body}</div></section>'

    head = "".join(f'<th style="--b:{COL[b]}">{E(BRANDS[b]["name"])}<br><small>@{E(BRANDS[b]["handle"])}</small></th>' for b in BRANDS)
    plural = {"story": "stories"}
    summary = " · ".join(f"{v} {plural.get(k, k + 's') if v != 1 else k}" for k, v in sorted(week.items())) or "nothing booked"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Studio dashboard</title>
<style>
:root{{--bg:#0f1115;--panel:#171a21;--ink:#e8eaf0;--dim:#9aa3b2;--line:#262b36}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
header{{padding:16px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px 18px;align-items:baseline}}
header h1{{margin:0;font-size:20px}} header span{{color:var(--dim)}}
main{{padding:16px;display:grid;gap:22px}} h2{{margin:0 0 10px;font-size:16px}} h2 small,th small{{color:var(--dim);font-weight:400}}
.note{{color:var(--dim);margin:-4px 0 10px}}
.wrap{{overflow-x:auto}} table{{border-collapse:separate;border-spacing:6px;min-width:760px;width:100%}}
th{{text-align:left;vertical-align:top;color:var(--dim);font-weight:600}} thead th{{border-top:3px solid var(--b);padding-top:6px;color:var(--ink)}}
tbody th{{width:64px}} td{{vertical-align:top;background:var(--panel);border-radius:10px;padding:6px;width:33%}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px}}
.card{{display:flex;gap:8px;background:var(--panel);border-left:4px solid var(--b);border-radius:8px;padding:8px;margin-bottom:6px}}
td .card{{background:#1e222b}}
.card img,.card video{{width:54px;height:68px;object-fit:cover;border-radius:6px;flex:none;background:#000}}
.meta{{min-width:0}} .top{{font-size:12px;color:var(--dim)}} .top b{{color:var(--ink)}}
.topic{{font-weight:600;margin:2px 0}} .angle{{font-size:12px;color:var(--dim);overflow-wrap:anywhere}} .angle a{{color:#7dd3fc}}
.why{{font-size:12px;color:#fca5a5;margin-top:3px}}
.q{{font-size:12px;color:#93c5fd;margin-top:3px}} .q.top{{color:#fb923c;font-weight:700}} .q.making{{color:#fcd34d}}
.chip{{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;border:1px solid var(--c);color:var(--c);margin-left:4px}}
.pulse{{animation:p 1.4s infinite}} @keyframes p{{50%{{opacity:.35}}}}
.empty{{color:#4b5563}} footer{{color:var(--dim);padding:0 16px 20px;font-size:12px}}
.acts{{display:flex;flex-wrap:wrap;gap:4px;margin-top:5px}}
.acts button{{font:600 11px system-ui;padding:4px 9px;border-radius:6px;border:1px solid #3a4150;background:#232834;color:var(--ink);cursor:pointer}}
.acts button:hover{{border-color:#7dd3fc}} .acts button:disabled{{opacity:.5;cursor:wait}}
.tabs{{display:flex;gap:6px;padding:12px 16px 0}} .tab{{padding:7px 13px;border-radius:99px;color:var(--dim);text-decoration:none;border:1px solid var(--line)}}
.tab.on{{color:var(--ink);background:#232834}} .tab b{{background:#ef4444;color:#fff;border-radius:99px;padding:0 7px;margin-left:4px;font-size:12px}}
#toast{{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);background:#111827;border:1px solid #374151;color:var(--ink);
  padding:10px 14px;border-radius:10px;max-width:90vw;display:none;white-space:pre-wrap;font-size:13px;z-index:9}}
</style></head><body>
{nav("cal", waiting)}
<header><h1>Studio</h1><span>{state}</span><span>approval: {E(db.setting("mode", "veto"))}</span>
<span>making {counts.get("making", 0)} · queued {counts.get("queued", 0)} · ready {counts.get("ready", 0) + counts.get("approved", 0)} · waiting for you {counts.get("held", 0)}</span>
<span>updated {now.strftime("%a %d %b %H:%M")} IST</span></header>
<main>
<section><h2>Next {days} days <small>{summary}</small></h2><div class="wrap"><table><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>
{section("Needs you", attention, "Easier on the ✅ Approvals tab. Or reply on Telegram: 'post N', 'override N', 'retry N' or 'remove N'.")}
{section("In production", making, "Three at a time, in queue order: 🔥 top priority first, then posts due in the next 12 h, then the rest. Tap 🔥 Make next to jump the queue.")}
{section("Ready to post", ready)}
{section("Hermes' pitches", pitched, "Reply 'yes N' or 'no N'.")}
{section("Live (last 3 days)", live)}
</main><footer>Refreshes every minute (paused while you act). Times are IST. Buttons run the same studio commands as Telegram.</footer>
<div id="toast"></div>
<script>
let busy = false;
setTimeout(function tick(){{ if (!busy) location.reload(); else setTimeout(tick, 5000); }}, 60000);
document.addEventListener("click", async (e) => {{
  const b = e.target.closest(".acts button"); if (!b) return;
  if (b.dataset.c === "1" && !confirm(b.textContent + " #" + b.dataset.id + "?")) return;
  busy = true; b.disabled = true; const t = document.getElementById("toast"); t.style.display = "block"; t.textContent = "Working on #" + b.dataset.id + "…";
  try {{
    const r = await fetch("api/act", {{method: "POST", headers: {{"Content-Type": "application/json", "X-Studio": "1"}},
                                        body: JSON.stringify({{id: +b.dataset.id, action: b.dataset.a}})}});
    const j = await r.json(); t.textContent = (j.ok ? "✅ " : "⚠️ ") + (j.output || j.error || "");
  }} catch (err) {{ t.textContent = "⚠️ " + err; }}
  setTimeout(() => location.reload(), 2500);
}});
</script></body></html>"""
    OUT.mkdir(parents=True, exist_ok=True)
    for it in {i["id"]: i for i in items + making + attention + ready + live + pitched}.values():
        if it["status"] not in ("idea", "queued", "suggested"):
            try:
                preview(it)
            except Exception:
                pass
    tmp = OUT / "index.html.tmp"; tmp.write_text(page); tmp.replace(OUT / "index.html")
    return OUT / "index.html"
