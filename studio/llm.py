"""Codex CLI (the owner's ChatGPT login on this server) as the studio's researcher, writer and review committee.

ask() sends one prompt through `codex exec` in a read-only sandbox and returns the reply; ask_json() parses the first JSON
object in it and retries once when the reply is not valid JSON. Web search is switched on only for research and fact-checks.
"""
import json, pathlib, re, subprocess, tempfile

CODEX = "codex"


def ask(prompt, images=(), search=False, timeout=1200, model=None):
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "reply.txt"
        cmd = [CODEX, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-C", tmp, "-o", str(out)]
        if search: cmd += ["-c", 'web_search="live"']
        if model: cmd += ["-m", model]
        cmd += ["-"]                                # the prompt goes on stdin: -i takes many values and would swallow it
        for im in images: cmd += ["-i", str(im)]
        p = subprocess.run(cmd, input=prompt, text=True, capture_output=True, timeout=timeout)
        reply = out.read_text().strip() if out.exists() else ""
        if not reply:
            raise RuntimeError(f"codex exec gave no reply (exit {p.returncode}): {(p.stderr or p.stdout)[-1200:]}")
        return reply


def first_json(text):
    """The JSON object in a reply: a ```json fence if there is one, else the outermost {...}."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m: return json.loads(m.group(1))
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a: raise ValueError("no JSON object in the reply")
    return json.loads(text[a:b + 1])


def ask_json(prompt, **kw):
    reply = ask(prompt, **kw)
    try:
        return first_json(reply)
    except ValueError as e:   # json.JSONDecodeError is a ValueError
        fix = (f"{prompt}\n\nYour previous reply was not valid JSON ({e}). Reply again with ONLY the JSON object, "
               "no prose, no code fence.")
        return first_json(ask(fix, **kw))


def fill(template, **values):
    """Fill {{name}} slots in a prompt template (single braces are left alone, so JSON examples stay intact)."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), m.group(0))), template)
