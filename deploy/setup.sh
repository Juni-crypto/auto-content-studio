#!/bin/bash
# Idempotent server setup for the studio app (run as ubuntu, uses sudo). Safe to re-run after every sync.
#
# Ownership model (Hermes runs as `studio` and reads untrusted web pages, so it must never reach the Instagram tokens):
#   root     : /opt/studio itself, app/ (code, prompts, skills), rules/, tools/, examples/  -> read-only to studio/Hermes
#   studio   : data/ media/ work/ logs/ assets/ venvs/ and .env (Telegram)                   -> the pipeline's working area
#   studioig : secrets/instagram.json (600); only /usr/local/bin/studio-ig reads it, via one sudo rule
set -euo pipefail
S=/opt/studio
id studioig >/dev/null 2>&1 || sudo useradd -r -M -s /usr/sbin/nologin -d /nonexistent studioig
sudo mkdir -p $S/{data,media,work,logs,secrets,assets/logos,dash} /var/log/caddy
sudo install -o root -g root -m 755 $S/app/deploy/studio /usr/local/bin/studio
sudo install -o root -g root -m 755 $S/app/deploy/studio-ig /usr/local/bin/studio-ig
sudo install -o root -g root -m 755 $S/app/deploy/codex-image.sh $S/tools/codex-image.sh
sudo install -o root -g root -m 440 $S/app/deploy/sudoers-studio-ig /etc/sudoers.d/studio-ig && sudo visudo -cf /etc/sudoers.d/studio-ig >/dev/null
sudo install -o root -g root -m 644 $S/app/deploy/apparmor-bwrap /etc/apparmor.d/bwrap && sudo apparmor_parser -r /etc/apparmor.d/bwrap
sudo -u studio -H bash -c "cd $S/work && /home/studio/.local/bin/uv pip install -q -p $S/venvs/qwen/bin/python pillow requests numpy scipy soundfile"
sudo chown root:root $S && sudo chmod 755 $S
for d in app rules tools examples; do sudo chown -R root:root $S/$d; sudo chmod -R u+rwX,go+rX,go-w $S/$d; done
for d in data media work logs assets venvs dash; do sudo chown -R studio:studio $S/$d; done
sudo chmod 755 $S/dash
sudo chmod 755 $S/media
[ -f $S/.env ] && sudo chown studio:studio $S/.env && sudo chmod 600 $S/.env
sudo chown -R studioig:studioig $S/secrets && sudo chmod 700 $S/secrets
[ -f $S/secrets/instagram.json ] && sudo chmod 600 $S/secrets/instagram.json
# Hermes: the zero-token /pause plugin and the health script (installed into the studio user's Hermes home)
sudo -u studio mkdir -p /home/studio/.hermes/plugins /home/studio/.hermes/scripts
sudo rm -rf /home/studio/.hermes/plugins/studio-commands && sudo cp -r $S/app/deploy/hermes-plugin/studio-commands /home/studio/.hermes/plugins/
sudo install -o studio -g studio -m 755 $S/app/deploy/studio-health.sh /home/studio/.hermes/scripts/studio-health.sh
sudo chown -R studio:studio /home/studio/.hermes/plugins
sudo cp $S/app/deploy/studio-worker.service $S/app/deploy/studio-tick.service $S/app/deploy/studio-tick.timer $S/app/deploy/studio-dash.service $S/app/deploy/studio-dash.timer $S/app/deploy/studio-dash-api.service /etc/systemd/system/
sudo cp $S/app/deploy/Caddyfile /etc/caddy/Caddyfile && sudo chown caddy:caddy /var/log/caddy
sudo systemctl daemon-reload
sudo systemctl enable --now caddy studio-worker studio-tick.timer studio-dash.timer studio-dash-api >/dev/null
sudo systemctl restart studio-dash-api
# code updates: a graceful reload (finish jobs in hand, then restart) unless RESTART_WORKER=1 forces it now
if [ "${RESTART_WORKER:-0}" = 1 ]; then sudo systemctl restart studio-worker; else /usr/local/bin/studio reload >/dev/null; fi
sudo systemctl reload caddy
sudo loginctl enable-linger studio
echo SETUP_OK
