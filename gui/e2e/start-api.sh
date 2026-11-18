#!/usr/bin/env bash
# Starts the real FastAPI backend against a fresh, deterministic temp DB/clips
# directory for e2e test runs. Nothing here talks to Twitch/YouTube/Kick/
# Discord/Post for Me - those integrations live outside the GUI's REST API,
# so an e2e run against this backend never makes an external network call
# and needs no credentials, without having to mock anything by hand.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/.tmp-e2e-data"

rm -rf "$DATA_DIR"
mkdir -p "$DATA_DIR/clips" "$DATA_DIR/recordings"

export DATABASE_URL="sqlite+aiosqlite:///$DATA_DIR/e2e.db"
export CLIPS_DIR="$DATA_DIR/clips"
export RECORDINGS_DIR="$DATA_DIR/recordings"

cd "$SCRIPT_DIR/../../pipeline"
exec .venv/bin/python -m uvicorn streamclip.api.app:create_app --factory --host 127.0.0.1 --port 8010
