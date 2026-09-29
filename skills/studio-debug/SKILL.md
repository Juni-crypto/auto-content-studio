---
name: studio-debug
description: Diagnose and fix problems in the owner's Instagram studio server — failed or rejected items, posts that didn't go out, expired Instagram tokens, Codex login, voice/render failures, services down, disk space.
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [instagram, studio, debugging, ops]
    category: studio
    requires_toolsets: [terminal]
---

# Studio debug

## Where things are
- App code: `/opt/studio/app` (package `studio`, prompts, skills, deploy). Tools: `/opt/studio/tools` (kinetic engine `kinetic/kreel.py`, voice `kinetic/voice_qwen.py`).
- Library DB: `/opt/studio/data/studio.db` (use `studio` commands, not raw SQL writes).
- Work folders: `/opt/studio/work/item-NNNNN/` (research.json, spec.json, vo/, build/, frames/, slides/, CREDITS.json).
- Public media: `/opt/studio/media/` → https://studio.example.com/m/...
- Services: `studio-worker` (makes items), `studio-tick.timer` (every 5 min: publish/start/expire/digest), `caddy`, the Hermes gateway (user service).
- Secrets (never print): `/opt/studio/.env`, `/opt/studio/secrets/instagram.json`.

## First look
1. `studio check` — accounts, publishing quota, disk, services, Codex login.
2. `studio status` and `studio log -n 40` (or `studio log <ID>` / `studio show <ID>`).
3. `journalctl -u studio-worker -n 80 --no-pager` · `journalctl -u studio-tick -n 40 --no-pager`.

## Known failures
| Symptom | Cause / fix |
|---|---|
| "Instagram helper failed" / sudo error | The token helper `/usr/local/bin/studio-ig` (runs as `studioig`, the only reader of the tokens) or its sudo rule `/etc/sudoers.d/studio-ig` is broken — needs the operator; you can't and mustn't read the tokens. |
| Instagram error code 190 / "Error validating access token" | Token expired or revoked (e.g. after a username/password change). Tell the owner to generate a new token for that account in the Meta app (Instagram → API setup → Generate token) and send it privately; it must be written into `/opt/studio/secrets/instagram.json` by the operator, never pasted in a group. |
| "video_url is required" on a story | Stories must be a public URL (the studio already does this); check Caddy (`systemctl status caddy`, `curl -I https://studio.example.com/m/<folder>/<file>`). |
| Instagram "media not ready"/timeout | Retry once: `studio post <ID>`. Check the file plays and is under Instagram limits. |
| `codex exec gave no reply` / login errors | `codex login status`. If logged out, run `codex login --device-auth` and send the owner the URL + code (they approve on their phone). |
| voice failed | `journalctl -u studio-worker`; the voice runs on CPU (~5x real time, 10–15 min per reel). Out of memory → check `free -g`; another heavy process? |
| render failed | Look at `work/item-N/build/<theme>/`; run `cd` there and `npx --yes hyperframes@0.8.79 render . -o test.mp4` to see the error. |
| BLANK CENTRE / picture rejected twice | The writer couldn't satisfy the picture editor; `studio retry <ID>` (new take) or give a new angle. |
| Committee "block" | Read `studio show <ID>`; explain the reason to the owner in one or two lines; offer a new angle. Never force it. |
| Disk low | Old work folders: `du -sh /opt/studio/work/* | sort -h | tail`; delete work folders of published/removed items older than 14 days (not media of live posts). |

## Rules while debugging
Fix causes, not symptoms; don't disable the committee, the pause switch or the checks; don't change the frozen rules or
brand settings without the owner's explicit OK; report what you changed. The studio code, rules and skills are read-only to you (root-owned) by design: if code must change, describe the
exact fix to the owner so it can be deployed from the Mac (tech-brand/SERVER.md has the deploy command). More detail: `/opt/studio/rules/SERVER.md`.
