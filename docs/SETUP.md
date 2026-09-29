# Setup

The studio expects this layout on the server (override the root with `STUDIO_ROOT`):

```
/opt/studio/
  app/        this repo (studio/, prompts/, skills/, deploy/)            owner root, read-only to the pipeline
  tools/      tools/kinetic from this repo + codex-image.sh (installed)   owner root
  rules/      your house rules (the editing rules, the frozen format)     owner root
  examples/   reference posts for the writers (optional)                   owner root
  data/       studio.db (SQLite)                                          owner studio
  media/      what gets posted (served publicly by Caddy at /m/)          owner studio
  work/       per-item working folders                                    owner studio
  assets/     logos, the media library, brand music beds                   owner studio
  venvs/qwen/ the Python env for TTS + rendering helpers                   owner studio
  dash/       the generated dashboard (served behind basic auth)           owner studio
  logs/
  .env        Telegram + optional stock-photo keys (600, owner studio)
  secrets/instagram.json   Instagram tokens (600, owner studioig — nobody else)
```

## 1. Server

1. Ubuntu 24.04, a user `ubuntu` with sudo, a service user `studio` (runs the worker, the timers and Hermes).
2. Install: `python3.12`, [`uv`](https://docs.astral.sh/uv/), Node 20+, `ffmpeg`, `caddy`, `bubblewrap` (the Codex sandbox;
   `deploy/apparmor-bwrap` lets it run under AppArmor).
3. Copy this repo to `/opt/studio/app` and `tools/kinetic` to `/opt/studio/tools/kinetic`, then run
   `bash /opt/studio/app/deploy/setup.sh` (idempotent: users, permissions, systemd units, Caddy, the Hermes plugin).
4. Create the TTS/render env: `uv venv /opt/studio/venvs/qwen` and install the TTS model you use (the kinetic tools ship
   adapters for Qwen3-TTS and Chatterbox in `voice_qwen.py` / `voice_cb.py`), plus `pillow numpy scipy soundfile requests`.
5. HyperFrames renders reels in headless Chrome: `npx hyperframes@<version>` (pinned in `studio/config.py`).

## 2. Accounts and secrets (never commit these)

- **Telegram:** create a bot with @BotFather; put the token and your numeric user id in `/opt/studio/.env`
  (see `.env.example`).
- **Instagram:** a Meta developer app with the *Instagram API with Instagram Login* product; each brand account must be a
  professional (Business/Creator) account. Generate a long-lived token per account and fill
  `/opt/studio/secrets/instagram.json` (see `secrets/instagram.example.json`); `studio check` refreshes tokens before they
  expire. Permissions used: `instagram_business_basic`, `instagram_business_content_publish`,
  `instagram_business_manage_comments` (comment → DM).
- **Codex CLI:** log in once as the `studio` user; the LLM and image calls go through `studio/llm.py` and
  `deploy/codex-image.sh`.
- **Stock photos (optional):** free Unsplash / Pexels / Pixabay keys in `.env` enable open-licence photo search.

## 3. Brands

Edit `BRANDS`, `CADENCE`, `SLOTS` and `OFFSET_MIN` in `studio/config.py`: name, handle, beat, greeting, TTS voice direction,
news focus, image style, posting slots. Put each brand's kinetic theme (colours, fonts, logo, emoji set, music beds) in
`tools/kinetic/brands/<theme>/` — see `tools/kinetic/ASSETS.md`.

## 4. Web

`deploy/Caddyfile` serves `/m/*` (public media — Instagram fetches posts from these URLs), `/dash/*` (basic auth) and
`/api/*` (the dashboard's actions → `studio` CLI). Set your domain there and export `STUDIO_PUBLIC=https://your.domain`
for the services.
The dashboard password is never stored in the repo: generate a hash with `caddy hash-password` and give it to Caddy as the
`DASH_HASH` environment variable (e.g. a systemd drop-in for caddy.service).

## 5. Hermes (chat control)

Install Hermes for the `studio` user, point it at your Telegram bot, and copy `skills/*` into its skills folder. The plugin
in `deploy/hermes-plugin/studio-commands` adds instant, zero-token commands (`/pause`, `/approvals`, `/dash`, `/queue`,
`/today`, `/scout` …). Everything else is natural language through the `studio-operator` skill, which only ever calls the
`studio` CLI.

## 6. Run

```
studio check            # accounts, token expiry, quota, disk, services
studio plan --days 7    # book a week
studio status           # what's due, making, ready
studio dash             # rebuild the dashboard (also every minute by timer)
```
