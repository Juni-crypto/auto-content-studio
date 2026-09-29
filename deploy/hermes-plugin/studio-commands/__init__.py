"""Zero-token studio commands: they run the `studio` control panel directly, no model call, so they work even when the
ChatGPT quota is out. /freeze [45m|2h|3d] (default 24h) stops all making and posting; /unfreeze restarts it.
(/pause, /resume and /stop are Hermes built-ins that control the agent itself, so the studio switch is /freeze.)"""
import os, shlex, subprocess


def _run(args):
    try:
        p = subprocess.run(["/usr/local/bin/studio", *args], capture_output=True, text=True, timeout=90,
                           env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": os.path.expanduser("~")})
        return ((p.stdout or "") + (p.stderr or "")).strip()[:3500] or "done"
    except Exception as e:
        return f"studio command failed: {e}"


def _pause(raw):
    return _run(["pause", *shlex.split(raw or "")])


PUBLIC = os.environ.get("STUDIO_PUBLIC", "https://studio.example.com")
APPROVALS = f"{PUBLIC}/dash/approve.html"


def _num(raw):
    import re
    m = re.findall(r"\d+", raw or "")
    return m[0] if m else None


def _top(raw):
    n = _num(raw)
    return _run(["priority", n, "top"]) if n else "Which post? e.g. /top 29"


def _today(raw):
    n = _num(raw) or "20"
    return _run(["today", n])


def _scout(raw):
    """Starts a scout in the background and answers at once (the ideas arrive in Approvals in a few minutes)."""
    topic = (raw or "").strip()[:160]
    try:
        subprocess.Popen(["/usr/local/bin/studio", "scout", "--by", "dashboard", *(["--topic", topic] if topic else [])],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                         env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": os.path.expanduser("~")})
        return f"🔎 Scouting{' for ' + repr(topic) if topic else ''} — ideas land in Approvals in ~3–5 min: {APPROVALS}"
    except Exception as e:
        return f"scout failed to start: {e}"


def register(ctx):
    ctx.register_command("approvals", lambda raw: f"✅ {APPROVALS}", "Link to everything waiting for your OK")
    ctx.register_command("dash", lambda raw: f"📅 {PUBLIC}/dash/  ·  ✅ {APPROVALS}  ·  ⚙️ {PUBLIC}/dash/auto.html",
                         "Dashboard links")
    ctx.register_command("queue", lambda raw: _run(["queue"]), "What's being made and the queue order")
    ctx.register_command("top", _top, "Make a post next (jump the queue), e.g. /top 29", args_hint="ID")
    ctx.register_command("today", _today, "N more posts today across all accounts, e.g. /today 10", args_hint="[N]")
    ctx.register_command("scout", _scout, "Scout for fresh ideas now, e.g. /scout IPL auction", args_hint="[topic]")
    ctx.register_command("freeze", _pause, "Pause the studio: nothing is made or posted (default 24h), e.g. /freeze 3d", args_hint="[45m|2h|3d]")
    ctx.register_command("unfreeze", lambda raw: _run(["resume"]), "Resume the studio")
    ctx.register_command("unpause", lambda raw: _run(["resume"]), "Resume the studio (same as /unfreeze)")
    ctx.register_command("studio", lambda raw: _run(["status"]), "Studio status: paused?, next 24 h, making, problems")
    ctx.register_command("lineup", lambda raw: _run(["list", "--days", "2"]), "Everything booked for the next 2 days")
