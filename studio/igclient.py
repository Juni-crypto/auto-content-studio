"""Instagram calls from the studio user, through the token helper.

The tokens live in /opt/studio/secrets/instagram.json, owned by the system user `studioig` (mode 600). The studio user (and so
Hermes) can't read them; it can only run the root-owned helper /usr/local/bin/studio-ig as studioig (one sudo rule), which
accepts publish / check / refresh as JSON on stdin and only publishes media served from the studio's own /m/ folder.
"""
import json, subprocess

HELPER = "/usr/local/bin/studio-ig"


def _call(payload, timeout=900):
    p = subprocess.run(["sudo", "-n", "-u", "studioig", HELPER], input=json.dumps(payload), text=True, capture_output=True, timeout=timeout)
    try:
        r = json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        raise RuntimeError(f"Instagram helper failed (exit {p.returncode}): {(p.stderr or p.stdout)[-400:]}") from None
    if not r.get("ok"): raise RuntimeError(r.get("error", "unknown Instagram error"))
    return r


def publish(brand, kind, urls, caption=""):
    r = _call({"action": "publish", "brand": brand, "kind": kind, "urls": urls, "caption": caption})
    return r["id"], r.get("permalink")


def comments(brand, media_ids):
    return _call({"action": "comments", "brand": brand, "media_ids": [str(m) for m in media_ids]}, timeout=300)["result"]


def private_reply(brand, comment_id, text, public=""):
    return _call({"action": "private_reply", "brand": brand, "comment_id": str(comment_id), "text": text, "public": public}, timeout=120)["id"]


def check(brand):
    return _call({"action": "check", "brand": brand}, timeout=120)["result"]


def refresh_all():
    return _call({"action": "refresh"}, timeout=300)["result"]
