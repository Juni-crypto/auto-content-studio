"""The Instagram token helper. Runs as `studioig` via `sudo -u studioig /usr/local/bin/studio-ig` — the only process that can
read the tokens. JSON request on stdin, one JSON line on stdout. Root-owned, stdlib only, run with `python3 -I`.
"""
import json, sys

sys.path.insert(0, "/opt/studio/app")
from studio import ig                      # noqa: E402  (after the path is set)
from studio.config import PUBLIC           # noqa: E402

KINDS = {"reel", "story", "carousel", "image"}


def main():
    try:
        req = json.loads(sys.stdin.read() or "{}")
        action = req.get("action")
        if action == "publish":
            urls = req.get("urls") or []
            if req.get("kind") not in KINDS: raise ValueError(f"unknown kind {req.get('kind')!r}")
            if not urls or len(urls) > 10 or not all(isinstance(u, str) and u.startswith(PUBLIC + "/m/") for u in urls):
                raise ValueError("media must be 1-10 files served from the studio's own /m/ folder")
            mid, link = ig.publish(req["brand"], req["kind"], urls, str(req.get("caption", ""))[:2200])
            out = {"ok": True, "id": mid, "permalink": link}
        elif action == "comments":
            ids = req.get("media_ids") or []
            if not ids or len(ids) > 30 or not all(isinstance(m, str) and m.isdigit() for m in ids): raise ValueError("media_ids: 1-30 numeric ids")
            out = {"ok": True, "result": ig.comments(req["brand"], ids)}
        elif action == "private_reply":
            cid, text, pub = str(req.get("comment_id", "")), str(req.get("text", "")), str(req.get("public", ""))
            if not cid.isdigit(): raise ValueError("comment_id must be numeric")
            if not text or len(text.encode()) > 1000 or len(pub) > 200: raise ValueError("DM text 1-1000 bytes, public reply <= 200 chars")
            out = {"ok": True, "id": ig.private_reply(req["brand"], cid, text, pub)}
        elif action == "check":
            out = {"ok": True, "result": ig.check(req["brand"])}
        elif action == "refresh":
            out = {"ok": True, "result": ig.refresh_all()}
        else:
            raise ValueError(f"unknown action {action!r}")
    except Exception as e:
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"[:800]}
    print(json.dumps(out))


main()
