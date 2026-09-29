#!/bin/bash
# Hermes no-agent cron (every 30 min): prints only when something needs the owner's attention; silence = healthy.
out=$(/usr/local/bin/studio check 2>&1)
bad=$(echo "$out" | grep -E "PROBLEM|: (inactive|failed)|Not logged in" )
free=$(df -BG --output=avail /opt/studio | tail -1 | tr -dc 0-9)
[ -n "$bad" ] && echo "⚠️ Studio health: $bad"
[ "${free:-99}" -lt 10 ] && echo "⚠️ Studio disk low: ${free} GB free"
exit 0
