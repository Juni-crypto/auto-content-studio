"""The studio's media & knowledge graph (inside studio.db): every entity, image, fact and post we have touched, linked, so a
logo, a press image, a generated object or a verified fact is found and reused instead of fetched or made again.

Nodes   entity:<id>  brand, company, club, team, league, federation, person, product, event, source
        asset:<id>   logo, press (official press/newsroom image), object (generated cut-out), scene, slide, video
        fact:<id>    one verified claim with its sources and date
        item:<id>    a post in the library
Edges   asset -depicts-> entity · fact -about-> entity · item -about-> entity · item -uses-> asset · item -cites-> fact
        entity -related-> entity
Files live in assets/library/<kind>/ and are never deleted by the pipeline (videos and slides stay in media/, registered in place).
"""
import hashlib, html, json, re, secrets, shutil, subprocess
from PIL import Image
from . import db
from .config import ASSETS, MEDIA, PUBLIC

LIB = ASSETS / "library"
SCHEMA = """
CREATE TABLE IF NOT EXISTS entities(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, official_site TEXT, company TEXT, notes TEXT,
  created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS entity_keys(key TEXT PRIMARY KEY, entity_id INTEGER);
CREATE TABLE IF NOT EXISTS assets(id INTEGER PRIMARY KEY, path TEXT UNIQUE, kind TEXT, title TEXT, tags TEXT, source_url TEXT,
  source_page TEXT, licence TEXT, credit TEXT, prompt TEXT, w INTEGER, h INTEGER, sha1 TEXT, uses INTEGER DEFAULT 0, created TEXT);
CREATE INDEX IF NOT EXISTS assets_sha ON assets(sha1);
CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, claim TEXT, key TEXT UNIQUE, date TEXT, sources TEXT, created TEXT, verified TEXT);
CREATE TABLE IF NOT EXISTS edges(src TEXT, rel TEXT, dst TEXT, created TEXT, PRIMARY KEY(src, rel, dst));
CREATE INDEX IF NOT EXISTS edges_dst ON edges(dst);
"""
STOP = {"the", "inc", "ltd", "limited", "co", "corp", "corporation", "company", "plc", "llc", "pvt", "private", "group", "a", "an", "of"}
WORDSTOP = STOP | {"and", "with", "on", "in", "for", "to", "at", "photoreal", "studio", "lighting", "centred", "centered", "image",
                   "photo", "object", "background", "frame", "filling", "most", "sharp", "flat", "white", "green"}


def key(name):
    return " ".join(w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in STOP)


def conn():
    c = db.conn(); c.executescript(SCHEMA); return c


def rows(sql, args=()):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


def link(src, rel, dst):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO edges(src,rel,dst,created) VALUES(?,?,?,?)", (src, rel, dst, db.iso(db.now())))


# ---------------------------------------------------------------- entities
def find_entity(name):
    k = key(name)
    if not k: return None
    r = rows("SELECT e.* FROM entity_keys k JOIN entities e ON e.id=k.entity_id WHERE k.key=?", (k,))
    if r: return r[0]
    # a longer or shorter form of a known name ("20th Asian Games Aichi-Nagoya 2026" -> "aichi nagoya 2026"): the longest known key
    # that sits inside the asked name on word boundaries, or that contains it (at least 6 characters, so "india" alone never matches)
    q = f" {k} "
    best = [x for x in rows("SELECT k.key, k.entity_id FROM entity_keys k WHERE length(k.key) >= 6")
            if f" {x['key']} " in q or (len(k) >= 6 and f" {k} " in f" {x['key']} ")]
    if not best: return None
    eid = max(best, key=lambda x: len(x["key"]))["entity_id"]
    return rows("SELECT * FROM entities WHERE id=?", (eid,))[0]


def entity(name, kind=None, aliases=(), official_site=None, company=None):
    """Find or create an entity (matched on its name or any alias); fills in missing details. Returns its id."""
    e = find_entity(name) or next((x for x in (find_entity(a) for a in aliases) if x), None)
    now = db.iso(db.now())
    with conn() as c:
        if e:
            c.execute("UPDATE entities SET kind=COALESCE(kind,?), official_site=COALESCE(official_site,?), company=COALESCE(company,?), updated=? WHERE id=?",
                      (kind, official_site, company, now, e["id"])); eid = e["id"]
        else:
            eid = c.execute("INSERT INTO entities(name,kind,official_site,company,created,updated) VALUES(?,?,?,?,?,?)",
                            (name, kind, official_site, company, now, now)).lastrowid
        for n in (name, *aliases):
            if key(n): c.execute("INSERT OR IGNORE INTO entity_keys(key,entity_id) VALUES(?,?)", (key(n), eid))
    return eid


# ---------------------------------------------------------------- assets
def _sha(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def add_asset(file, kind, entities=(), title="", tags="", source_url="", source_page="", licence="", credit="", prompt="", copy=True):
    """Register a file (copied into assets/library/<kind>/ unless copy=False). SVGs are rendered to PNG. Dedupes by content."""
    import pathlib
    src = pathlib.Path(file); sha = _sha(src)
    hit = rows("SELECT * FROM assets WHERE sha1=?", (sha,))
    if hit:
        aid = hit[0]["id"]
    else:
        if copy:
            (LIB / kind).mkdir(parents=True, exist_ok=True)
            stem = re.sub(r"[^a-z0-9]+", "-", (title or src.stem).lower()).strip("-")[:60] or kind
            if src.suffix.lower() == ".svg":
                dest = LIB / kind / f"{stem}-{sha[:8]}.png"
                subprocess.run(["rsvg-convert", "-w", "2000", "-o", str(dest), str(src)], check=True)
            else:
                dest = LIB / kind / f"{stem}-{sha[:8]}{src.suffix.lower()}"; shutil.copy(src, dest)
        else:
            dest = src
        try:
            w, h = Image.open(dest).size
        except Exception:
            w = h = None
        with conn() as c:
            aid = c.execute("INSERT OR IGNORE INTO assets(path,kind,title,tags,source_url,source_page,licence,credit,prompt,w,h,sha1,created) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (str(dest), kind, title or src.stem, tags, source_url, source_page, licence,
                                                                  credit, prompt, w, h, sha, db.iso(db.now()))).lastrowid
            if not aid: aid = c.execute("SELECT id FROM assets WHERE path=?", (str(dest),)).fetchone()["id"]
    for e in entities:
        link(f"asset:{aid}", "depicts", f"entity:{e}")
    return rows("SELECT * FROM assets WHERE id=?", (aid,))[0]


def used(asset_id, item_id=None):
    with conn() as c:
        c.execute("UPDATE assets SET uses=uses+1 WHERE id=?", (asset_id,))
    if item_id: link(f"item:{item_id}", "uses", f"asset:{asset_id}")


def assets_of(entity_name, kind):
    e = find_entity(entity_name)
    if not e: return []
    return rows("SELECT a.* FROM edges x JOIN assets a ON x.src='asset:'||a.id WHERE x.rel='depicts' AND x.dst=? AND a.kind=? "
                "ORDER BY (COALESCE(a.w,0)*COALESCE(a.h,0)) DESC", (f"entity:{e['id']}", kind))


def words(text):
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in WORDSTOP}


def similar(prompt, kinds=("object",), threshold=0.5):
    """A generated image whose prompt/title/tags share most words with this prompt (Jaccard), or None."""
    want = words(prompt)
    if not want: return None
    best, score = None, 0.0
    for a in rows(f"SELECT * FROM assets WHERE kind IN ({','.join('?' * len(kinds))})", kinds):
        have = words(" ".join(filter(None, (a["prompt"], a["title"], a["tags"]))))
        s = len(want & have) / len(want | have) if have else 0
        if s > score: best, score = a, s
    return best if score >= threshold else None


def remove_asset(asset_id):
    """Delete a wrong or unwanted image: its row, its edges, and its file if it lives in the library."""
    import os
    a = rows("SELECT * FROM assets WHERE id=?", (asset_id,))
    if not a: return None
    with conn() as c:
        c.execute("DELETE FROM edges WHERE src=? OR dst=?", (f"asset:{asset_id}", f"asset:{asset_id}"))
        c.execute("DELETE FROM assets WHERE id=?", (asset_id,))
    if a[0]["path"].startswith(str(LIB)) and os.path.exists(a[0]["path"]): os.remove(a[0]["path"])
    return a[0]


# ---------------------------------------------------------------- facts
def add_fact(claim, date=None, sources=(), entity_ids=(), item_id=None):
    k = key(claim)[:400]; now = db.iso(db.now())
    with conn() as c:
        r = c.execute("SELECT id FROM facts WHERE key=?", (k,)).fetchone()
        if r:
            fid = r["id"]; c.execute("UPDATE facts SET verified=? WHERE id=?", (now, fid))
        else:
            fid = c.execute("INSERT INTO facts(claim,key,date,sources,created,verified) VALUES(?,?,?,?,?,?)",
                            (claim, k, date, json.dumps(list(sources), ensure_ascii=False), now, now)).lastrowid
    for e in entity_ids: link(f"fact:{fid}", "about", f"entity:{e}")
    if item_id: link(f"item:{item_id}", "cites", f"fact:{fid}")
    return fid


def entities_in(text):
    """Entities whose name or alias appears in the text."""
    t = " " + key(text) + " "
    return rows("SELECT DISTINCT e.* FROM entity_keys k JOIN entities e ON e.id=k.entity_id WHERE length(k.key) >= 3 AND instr(?, ' '||k.key||' ') > 0", (t,))


def known_facts(text, days=180, limit=25):
    ids = [e["id"] for e in entities_in(text)]
    if not ids: return []
    since = db.iso(db.now() - db.dt.timedelta(days=days))
    q = ("SELECT DISTINCT f.* FROM edges x JOIN facts f ON x.src='fact:'||f.id WHERE x.rel='about' AND x.dst IN (%s) AND f.verified >= ? "
         "ORDER BY f.verified DESC LIMIT ?" % ",".join("?" * len(ids)))
    return rows(q, (*[f"entity:{i}" for i in ids], since, limit))


def record_research(item_id, research):
    """Entities and facts from a research pass become graph nodes linked to the item."""
    eids = {}
    for e in research.get("entities", []):
        if e.get("name"):
            eids[e["name"]] = entity(e["name"], e.get("type"), official_site=e.get("official_site"), company=e.get("company"))
            link(f"item:{item_id}", "about", f"entity:{eids[e['name']]}")
    for f in research.get("facts", []):
        about = [i for n, i in eids.items() if key(n) and key(n) in key(f.get("claim", ""))]
        dates = [s.get("published") for s in f.get("sources", []) if s.get("published")]
        add_fact(f.get("claim", ""), max(dates) if dates else research.get("event_date"), f.get("sources", []), about, item_id)
    return eids


# ---------------------------------------------------------------- views
def about(name):
    e = find_entity(name)
    if not e: return None
    node = f"entity:{e['id']}"
    edges = rows("SELECT * FROM edges WHERE dst=? OR src=?", (node, node))
    out = {"entity": e, "aliases": [r["key"] for r in rows("SELECT key FROM entity_keys WHERE entity_id=?", (e["id"],))],
           "assets": [], "facts": [], "items": [], "related": []}
    for x in edges:
        other = x["src"] if x["dst"] == node else x["dst"]; t, i = other.split(":")
        if t == "asset": out["assets"] += rows("SELECT id,kind,title,path,licence,uses FROM assets WHERE id=?", (i,))
        elif t == "fact": out["facts"] += rows("SELECT id,claim,date,verified FROM facts WHERE id=?", (i,))
        elif t == "item": out["items"] += [{"id": int(i), "rel": x["rel"]}]
        elif t == "entity": out["related"] += rows("SELECT id,name,kind FROM entities WHERE id=?", (i,))
    return out


def stats():
    return {t: rows(f"SELECT COUNT(*) n FROM {t}")[0]["n"] for t in ("entities", "assets", "facts", "edges")}


def export_html():
    """A private (unlisted-URL) interactive map of the whole graph with thumbnails. Returns its URL."""
    folder = MEDIA / f"graph-{secrets.token_hex(6)}"; (folder / "t").mkdir(parents=True)
    for old in MEDIA.glob("graph-*"):
        if old != folder: shutil.rmtree(old, ignore_errors=True)
    nodes, edges, colours = [], [], {"entity": "#E6007E", "fact": "#1F4FB8", "item": "#FF5B1F"}
    for e in rows("SELECT * FROM entities"):
        nodes.append({"id": f"entity:{e['id']}", "label": e["name"], "group": "entity", "color": colours["entity"], "shape": "dot", "size": 18,
                      "title": f"{e['kind'] or ''} {e['official_site'] or ''}"})
    for a in rows("SELECT * FROM assets"):
        thumb = folder / "t" / f"{a['id']}.png"
        try:
            im = Image.open(a["path"]); im.thumbnail((96, 96)); im.save(thumb)
            nodes.append({"id": f"asset:{a['id']}", "label": a["title"][:24], "shape": "image", "image": f"t/{a['id']}.png", "size": 22,
                          "title": f"{a['kind']} · {a['licence'] or ''} · used {a['uses']}×"})
        except Exception:
            nodes.append({"id": f"asset:{a['id']}", "label": a["title"][:24], "shape": "box", "title": a["kind"]})
    for f in rows("SELECT * FROM facts"):
        nodes.append({"id": f"fact:{f['id']}", "label": "", "shape": "dot", "size": 6, "color": colours["fact"], "title": html.escape(f["claim"][:300])})
    for it in db.items("1=1"):
        nodes.append({"id": f"item:{it['id']}", "label": f"#{it['id']} {it['kind']}", "shape": "diamond", "size": 12, "color": colours["item"],
                      "title": html.escape(f"{it['brand']} · {it['status']} · {it['topic'] or ''}")})
    ids = {n["id"] for n in nodes}
    for x in rows("SELECT * FROM edges"):
        if x["src"] in ids and x["dst"] in ids: edges.append({"from": x["src"], "to": x["dst"], "title": x["rel"]})
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Studio graph</title><script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>body{{margin:0;font:14px system-ui;background:#111;color:#eee}}#g{{position:absolute;inset:40px 0 0 0}}header{{padding:10px 16px}}</style></head>
<body><header>Studio knowledge graph · {len([n for n in nodes if n['id'].startswith('entity')])} entities ·
{len([n for n in nodes if n['id'].startswith('asset')])} images · {len([n for n in nodes if n['id'].startswith('fact')])} facts ·
{len([n for n in nodes if n['id'].startswith('item')])} posts · generated {db.now().strftime('%d %b %H:%M')}</header><div id="g"></div>
<script>new vis.Network(document.getElementById("g"),{{nodes:new vis.DataSet({json.dumps(nodes)}),edges:new vis.DataSet({json.dumps(edges)})}},
{{physics:{{stabilization:{{iterations:250}},barnesHut:{{springLength:120}}}},nodes:{{font:{{color:"#eee"}}}},edges:{{color:"#555"}},interaction:{{hover:true}}}});</script>
</body></html>"""
    (folder / "index.html").write_text(page)
    for p in folder.rglob("*"): p.chmod(0o755 if p.is_dir() else 0o644)
    folder.chmod(0o755)
    return f"{PUBLIC}/m/{folder.name}/index.html"
