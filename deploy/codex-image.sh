#!/usr/bin/env bash
# Generate or edit ONE image with the Codex CLI built-in image tool (ChatGPT login, no OPENAI_API_KEY).
# Usage: codex-image.sh -o OUT.png [-s SIZE] [-i REF]... [-p "BRIEF"]
#   -o  output path; must not exist yet (its folder becomes the Codex workspace)
#   -s  size, e.g. 1024x1536 portrait (default), 1536x1024 landscape, 1024x1024 square
#   -i  reference image, repeatable, max 5 (the tool silently drops extras)
#   -p  image brief; read from stdin when omitted
set -euo pipefail

CODEX="${CODEX_BIN:-$(command -v codex || echo /Applications/ChatGPT.app/Contents/Resources/codex)}"
out=""; size="1024x1536"; brief=""; refs=()
while getopts "o:s:i:p:" opt; do
  case "$opt" in
    o) out="$OPTARG" ;;
    s) size="$OPTARG" ;;
    i) refs+=("$OPTARG") ;;
    p) brief="$OPTARG" ;;
    *) sed -n '2,7p' "$0" >&2; exit 2 ;;
  esac
done

[ -x "$CODEX" ] || { echo "error: codex not found (set CODEX_BIN)" >&2; exit 2; }
[ -n "$out" ] || { echo "error: -o OUT.png is required" >&2; exit 2; }
[ -e "$out" ] && { echo "error: $out already exists; pass a new path" >&2; exit 2; }
[ -n "$brief" ] || brief="$(cat)"
[ -n "$brief" ] || { echo "error: empty brief" >&2; exit 2; }
[ "${#refs[@]}" -le 5 ] || { echo "error: max 5 reference images; combine extras into one labelled sheet" >&2; exit 2; }

mkdir -p "$(dirname "$out")"
dir="$(cd "$(dirname "$out")" && pwd)"
name="$(basename "$out")"
out="$dir/$name"
logdir="$dir/.codex-image-logs"; mkdir -p "$logdir"
marker="$(mktemp)"; trap 'rm -f "$marker"' EXIT   # this run's own start time (parallel runs share logdir)
log="$logdir/${name%.*}.log"

ref_note=""
if [ "${#refs[@]}" -gt 0 ]; then
  ref_note="The attached images are references, numbered in attach order:"
  n=1
  for r in "${refs[@]}"; do
    [ -f "$r" ] || { echo "error: missing reference $r" >&2; exit 2; }
    ref_note="$ref_note image $n = $(basename "$r");"
    n=$((n + 1))
  done
  ref_note="$ref_note Follow the brief for what to take from each reference."
fi

instr="Use your built-in image generation tool (do not write code to draw it) to create exactly ONE image at $size, then copy the resulting PNG to ./$name. $ref_note Pass the IMAGE BRIEF to the image tool VERBATIM; do not paraphrase, shorten or add to it. IMAGE BRIEF: $brief After saving, print only the output path."

if [ "${#refs[@]}" -gt 0 ]; then
  ref_args=()
  for r in "${refs[@]}"; do ref_args+=(-i "$r"); done
  # -i is multi-value and swallows a trailing positional prompt, so the prompt goes on stdin.
  printf '%s' "$instr" | "$CODEX" exec --skip-git-repo-check -s workspace-write -C "$dir" --ephemeral - "${ref_args[@]}" > "$log" 2>&1 || true
else
  "$CODEX" exec --skip-git-repo-check -s workspace-write -C "$dir" --ephemeral "$instr" < /dev/null > "$log" 2>&1 || true
fi

# Newer Codex builds save generated images under ~/.codex/generated_images and sometimes only print that path:
# take the newest image created during this run.
if [ ! -s "$out" ]; then
  # 1) the exact path this run printed; 2) else the newest image in THIS run's session folder (parallel-safe);
  # 3) else the newest image created since this run started
  gen="$(grep -o -E '/[^ `]*/generated_images/[^ `]+\.(png|jpg|webp)' "$log" 2>/dev/null | tail -1)"
  if [ -z "$gen" ] || [ ! -f "$gen" ]; then
    sid="$(grep -m1 -o -E 'session id: [0-9a-f-]+' "$log" | awk '{print $3}')"
    gdir="${CODEX_HOME:-$HOME/.codex}/generated_images/$sid"
    [ -n "$sid" ] && [ -d "$gdir" ] && gen="$(ls -t "$gdir"/*.png "$gdir"/*.jpg "$gdir"/*.webp 2>/dev/null | head -1)"
  fi
  [ -n "$gen" ] && [ -f "$gen" ] || gen="$(cd / && find "${CODEX_HOME:-$HOME/.codex}/generated_images" -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.webp' \) -newer "$marker" 2>/dev/null | xargs -r ls -t 2>/dev/null | head -1)"
  [ -n "$gen" ] && [ -f "$gen" ] && cp "$gen" "$out"
fi

if [ -s "$out" ]; then
  echo "$out"
else
  echo "FAIL: no image written; see $log" >&2
  tail -20 "$log" >&2
  exit 1
fi
