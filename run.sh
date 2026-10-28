#!/usr/bin/env bash
# One-command start. The first run creates a virtualenv with the engines your .env asks for.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { cp .env.example .env; echo "Created .env. Add your ANTHROPIC_API_KEY to it, then run ./run.sh again."; exit 1; }

extras=$(grep -E '^VIPLAV_(TTS|STT)=' .env | cut -d= -f2 | tr ',' '\n' | grep -E '^(kokoro|mms|indic-parler|whisper)$' | sort -u | paste -sd, - || true)
if [ ! -d .venv ] || [ "$(cat .venv/.extras 2>/dev/null)" != "$extras" ]; then
  # Kokoro's dependencies don't build on Python 3.13 yet, so prefer 3.12 or 3.11 when present.
  py=$(command -v python3.12 || command -v python3.11 || command -v python3)
  [ -d .venv ] || "$py" -m venv .venv
  echo "Installing VIPLAV${extras:+ with $extras} (the first time takes a few minutes)…"
  .venv/bin/pip install -q -e ".${extras:+[$extras]}"
  echo "$extras" > .venv/.extras
fi
exec .venv/bin/viplav
