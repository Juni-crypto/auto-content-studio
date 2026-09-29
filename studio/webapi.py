"""The dashboard's action buttons: a tiny local endpoint (127.0.0.1:8765) that Caddy exposes at /dash/api/ behind the same
password as the dashboard. It runs only whitelisted `studio` commands on one item, then rebuilds the page.

Cross-site protection: requests must carry the X-Studio header and come from the dashboard's own origin (a foreign page cannot
set custom headers without a CORS preflight, which this server never answers).
"""
import json, re, subprocess
from .config import PUBLIC
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ACTIONS = {"post": ["post"], "approve": ["approve"], "override": ["override"], "retry": ["retry"], "make": ["make"], "hold": ["hold"],
           "release": ["release"], "remove": ["remove"], "accept": ["accept"], "decline": ["decline"], "when-ready": ["post", "--when-ready"],
           "animate": ["motion", "animated"], "still": ["motion", "still"],
           "top": ["priority", "top"], "high": ["priority", "high"], "normal": ["priority", "normal"], "low": ["priority", "low"]}
ORIGIN = PUBLIC


def studio(*args, timeout=600):
    p = subprocess.run(["/usr/local/bin/studio", *args], capture_output=True, text=True, timeout=timeout)
    return p.returncode == 0, ((p.stdout or "") + (p.stderr or "")).strip()[-1200:]


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def do_POST(self):
        if self.path.rstrip("/") not in ("/api/act", "/api/scout"): return self.reply(404, {"error": "not found"})
        if self.headers.get("X-Studio") != "1" or (self.headers.get("Origin") or ORIGIN) != ORIGIN:
            return self.reply(403, {"error": "forbidden"})
        if self.path.rstrip("/") == "/api/scout":   # a scout takes minutes: start it and answer at once
            try:
                req = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 4096)) or b"{}")
                brand = req.get("brand") or "all"; n = int(req.get("n") or 5)
                topic = re.sub(r"[\x00-\x1f]", " ", str(req.get("topic") or "")).strip()[:160]
            except (ValueError, TypeError):
                return self.reply(400, {"error": "bad request"})
            if brand not in ("all", "sportsdesk", "techdesk", "bizdesk") or not 1 <= n <= 10: return self.reply(400, {"error": "bad brand or count"})
            subprocess.Popen(["/usr/local/bin/studio", "scout", "--brand", brand, "--n", str(n), "--by", "dashboard"] + (["--topic", topic] if topic else []),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return self.reply(200, {"ok": True, "output": "Scouting now — the ideas reach Telegram and the Approvals tab in about 3–5 minutes."})
        try:
            req = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 4096)) or b"{}")
            action, item = req.get("action"), int(req.get("id"))
        except (ValueError, TypeError):
            return self.reply(400, {"error": "bad request"})
        if action == "schedule":   # approve it for a time the owner picked (IST, from the dashboard's date-time picker)
            at = str(req.get("at") or "")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", at): return self.reply(400, {"error": "pick a date and time"})
            when = at.replace("T", " ")
            ok, out = studio("move", str(item), when)
            if ok:
                ok2, out2 = studio("approve", str(item)); ok, out = ok2, f"#{item} approved to post at {when} IST." if ok2 else out2
            studio("dash", timeout=60)
            return self.reply(200 if ok else 409, {"ok": ok, "output": out})
        if action == "animate_slide":   # one slide of a finished carousel
            try:
                slide = int(req.get("slide"))
            except (ValueError, TypeError):
                return self.reply(400, {"error": "bad slide"})
            if not 1 <= slide <= 10: return self.reply(400, {"error": "bad slide"})
            ok, out = studio("motion", str(item), "animated", "--slides", str(slide)); studio("dash", timeout=60)
            return self.reply(200 if ok else 409, {"ok": ok, "output": out})
        if action not in ACTIONS: return self.reply(400, {"error": f"unknown action {action}"})
        cmd = ACTIONS[action]
        args = [cmd[0], str(item), *cmd[1:]]
        if action == "retry":   # retry = back to the plan and make it now
            ok, out = studio("retry", str(item))
            if ok: ok, out2 = studio("make", str(item)); out = out + "\n" + out2
        else:
            ok, out = studio(*args)
        studio("dash", timeout=60)
        self.reply(200 if ok else 409, {"ok": ok, "output": out})

    def log_message(self, fmt, *args):   # quiet; systemd keeps errors
        pass


def main():
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()


if __name__ == "__main__":
    main()
