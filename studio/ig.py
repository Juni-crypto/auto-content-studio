"""Publish through the official Instagram API with Instagram Login tokens (graph.instagram.com). Never prints tokens.

Instagram fetches every file from a public HTTPS URL (Caddy serves /opt/studio/media at PUBLIC/m/). Stories need a URL;
the resumable upload is refused for them with these tokens. Deleting a published post is NOT possible with these tokens
(that needs Facebook Login + instagram_manage_contents), so the library can only remove unpublished items.
"""
import json, os, time, urllib.error, urllib.parse, urllib.request
from .config import SECRETS

GRAPH, V = "https://graph.instagram.com", "v23.0"


def accounts():
    return json.loads(SECRETS.read_text())


def account(brand):
    return next(a for a in accounts() if a["brand"] == brand)


def call(method, path, token, params=None):
    url = f"{GRAPH}/{path}" if path.startswith(V) or path.startswith("refresh") or path.startswith("me") else f"{GRAPH}/{V}/{path}"
    data = None
    if method == "POST":
        data = urllib.parse.urlencode(params or {}).encode()
    elif params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"OAuth {token}", "User-Agent": "Studio/1.0"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        raise RuntimeError(f"Instagram {method} {path.split('?')[0]} -> HTTP {e.code}: {body}") from None


def wait_ready(cid, tok, tries=90):
    for _ in range(tries):
        st = call("GET", cid, tok, {"fields": "status_code,status"})
        if st.get("status_code") == "FINISHED": return
        if st.get("status_code") in ("ERROR", "EXPIRED"): raise RuntimeError(f"Instagram processing failed: {st}")
        time.sleep(5)
    raise RuntimeError(f"Instagram processing timed out for container {cid}")


def publish(brand, kind, urls, caption=""):
    """kind: reel | story | carousel | image. urls: public HTTPS URLs (one, or 2-10 for a carousel: .jpg slides and/or .mp4
    animated slides). Returns (media_id, permalink)."""
    a = account(brand); tok, uid = a["token"], a["ig_user_id"]
    if kind == "carousel":   # slides are images or short videos (animated carousels); videos take a while to process
        kids = [call("POST", f"{uid}/media", tok, {**({"media_type": "VIDEO", "video_url": u} if u.endswith(".mp4") else {"image_url": u}),
                                                   "is_carousel_item": "true"})["id"] for u in urls]
        for k in kids: wait_ready(k, tok)
        cid = call("POST", f"{uid}/media", tok, {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption})["id"]
    elif kind == "reel":
        cid = call("POST", f"{uid}/media", tok, {"media_type": "REELS", "video_url": urls[0], "caption": caption, "share_to_feed": "true"})["id"]
    elif kind == "story":
        key = "video_url" if urls[0].endswith(".mp4") else "image_url"
        cid = call("POST", f"{uid}/media", tok, {"media_type": "STORIES", key: urls[0]})["id"]
    else:
        cid = call("POST", f"{uid}/media", tok, {"image_url": urls[0], "caption": caption})["id"]
    wait_ready(cid, tok)
    mid = call("POST", f"{uid}/media_publish", tok, {"creation_id": cid})["id"]
    try:
        link = call("GET", mid, tok, {"fields": "permalink"}).get("permalink")
    except RuntimeError:
        link = None
    return mid, link


def comments(brand, media_ids, limit=50):
    """Top-level comments on our own posts: {media_id: [{id, text, username, timestamp}]} (instagram_business_manage_comments)."""
    a = account(brand); out = {}
    for m in media_ids:
        out[m] = call("GET", f"{m}/comments", a["token"], {"fields": "id,text,username,timestamp", "limit": limit}).get("data", [])
    return out


def private_reply(brand, comment_id, text, public=""):
    """One private DM to the person who wrote comment_id (Instagram allows exactly one, within 7 days of the comment), then an
    optional short public reply under their comment. Returns the message id."""
    a = account(brand); tok, uid = a["token"], a["ig_user_id"]
    r = call("POST", f"{uid}/messages", tok, {"recipient": json.dumps({"comment_id": comment_id}), "message": json.dumps({"text": text})})
    if public:
        try:
            call("POST", f"{comment_id}/replies", tok, {"message": public})
        except RuntimeError:
            pass
    return r.get("message_id")


def check(brand):
    a = account(brand)
    me = call("GET", f"{V}/me", a["token"], {"fields": "user_id,username,account_type"})
    lim = call("GET", f"{a['ig_user_id']}/content_publishing_limit", a["token"], {"fields": "quota_usage,config"})
    return {"username": me.get("username"), "type": me.get("account_type"), "quota": (lim.get("data") or [{}])[0]}


def refresh_all(min_age_days=20):
    """Long-lived tokens last 60 days and can be refreshed once they are 24 h old. Refresh every ~20 days; rewrite the file (600)."""
    accs = accounts(); changed = []
    for a in accs:
        age = (time.time() - a.get("refreshed", 0)) / 86400
        if age < min_age_days: continue
        r = call("GET", "refresh_access_token", a["token"], {"grant_type": "ig_refresh_token", "access_token": a["token"]})
        a["token"], a["refreshed"], a["expires_in"] = r["access_token"], int(time.time()), r.get("expires_in")
        changed.append(a["brand"])
    if changed:
        tmp = SECRETS.with_suffix(".tmp"); tmp.write_text(json.dumps(accs, indent=1)); os.chmod(tmp, 0o600); tmp.replace(SECRETS)
    return changed
