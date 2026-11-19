# streamclip

An automated stream-to-social clip pipeline: watches Twitch/YouTube/Kick
streamers, records live streams, detects highlight moments from chat
activity and audio events (laughter/cheering), clips them, sends them to
Discord for a human approve/reject, and auto-publishes approved clips to
your connected social accounts via [Post for Me](https://postforme.dev).

Built from the pipeline described in [this TikTok](https://www.tiktok.com/@kaylumai)
(`@kaylumai`, "GTA clipping system setup").

## Architecture

```
platform adapters (Twitch/YouTube/Kick)
        |  live-detection + chat
        v
   StreamlinkRecorder  --(10-min chunks)-->  chunk files on disk
        |
        v
  ChatSignalDetector  +  AudioEventClassifier
        |  (message-rate/emote spikes)  (laughter/cheering, HF AudioSet model)
        v
      HighlightScorer  -- combines signals, applies 35-45s pre-roll + cooldown
        |
        v
      FfmpegClipper  -- trims/concats the recorded chunks into a clip file
        |
        v
    Clip (DB, pending review)
        |
        +--> Discord bot: "clip ready" message + Approve/Reject buttons
        |
        +--> GUI (React): same review queue, in a browser
                |
                v (on approve)
        PostForMeClient -- uploads + posts the clip to your connected accounts
```

`pipeline/src/streamclip/orchestrator/worker.py` is what wires all of this
into one running session; `worker_main.py` is the process entrypoint that
builds it from real settings/credentials and keeps it running.

## Repo layout

```
pipeline/   Python backend: platform adapters, recorder, detection, clipper,
            orchestrator, Discord bot, Post for Me publisher, FastAPI app
gui/        React + TypeScript dashboard: streamer management, clip review
docker-compose.yml, pipeline/Dockerfile, gui/Dockerfile
.env.example
```

## Testing pyramid

**Backend** (`pipeline/`, pytest): 81 tests.
- **Unit** (`tests/unit/`): pure logic and every external call (HTTP via
  `respx`, subprocesses, websockets) mocked/injected - the chat/audio
  scoring math, clip-window calculation, chunk-offset math, platform adapter
  request/response handling, Discord review logic, Post for Me client.
- **Integration** (`tests/integration/`): the same components exercised
  against *real* ffmpeg, a real segmented recording, a real multi-chunk clip
  extraction, and the full FastAPI app over a real (temp-file) SQLite DB.
- A `slow` marker exists for a real-model audio-classification test, which
  needs `pip install -e ".[audio]"` (downloads ML model weights) and is
  excluded from the default run: `pytest -m slow`.

Run: `cd pipeline && .venv/bin/python -m pytest`

**GUI** (`gui/`):
- **Unit/component** (Vitest + React Testing Library, `npm test`): every
  component with the API client mocked - 13 tests.
- **End-to-end** (Playwright, `npm run test:e2e`): drives a real browser
  against the real FastAPI backend (temp DB) and a real Vite dev server -
  add/untrack/remove a streamer, seed a clip (via a tiny real ffmpeg-made
  video + direct DB insert, since clips normally come from the orchestrator,
  not a GUI action) and approve/reject it end to end. No external platform
  credentials are reachable from this path, so nothing needs mocking by hand.

## Running it

### Locally, without Docker

```bash
# Backend
cd pipeline
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp ../.env.example ../.env   # fill in whichever credentials you have
python -m uvicorn streamclip.api.app:create_app --factory --reload &
python -m streamclip.worker_main &   # the always-on polling/recording/clipping loop

# GUI
cd ../gui
npm install
npm run dev
```

### With Docker Compose

```bash
cp .env.example .env   # fill in credentials
```

If this is running on a real server (not your own laptop), edit `.env` and
set `VITE_API_BASE_URL` to that server's public IP or domain, e.g.
`VITE_API_BASE_URL=http://203.0.113.5:8000` - it gets baked into the GUI's
JavaScript and runs in every visitor's browser, so "localhost" only works
when you're browsing from the same machine the server is on.

```bash
docker compose up --build
```

This starts the API (`:8000`), the worker (polling/recording/clipping, no
exposed port), and the GUI (`:5173`), sharing a `streamclip-data` volume for
the SQLite DB, recordings, and clips.

## Known limitations / things to verify before relying on this in production

- **Kick adapter** (`platforms/kick.py`): Kick's public API is newer and
  less documented than Twitch/YouTube's. The request/response field names
  used there are the best available at time of writing and are the first
  thing to re-check against Kick's current docs if it starts failing.
- **YouTube API quota**: polling many channels every couple of minutes via
  `search.list` (≈100 quota units/call) can exhaust the free 10,000/day
  quota quickly with more than a handful of tracked channels.
- **Audio classification** needs the optional `audio` extras
  (`pip install -e ".[audio]"`, pulls in `torch`/`transformers` and
  downloads a pretrained AudioSet model on first use) - without it, highlight
  detection still works from chat signals alone.
- **`npm audit`** flags a ReDoS advisory (`GHSA-fc5q-39xc-vjpf`) against
  `picomatch`, pulled in transitively by Vite/Vitest. At time of writing
  there is no upstream-patched `picomatch` release yet, and it's a
  build-tool-only dependency (never shipped to the browser bundle, not
  reachable by end users of the built GUI) - nothing to act on beyond
  periodically re-running `npm audit`.
- This worker process needs to run continuously (it's not something a cloud
  dev session can host long-term) - see "Running it" above for a real
  host/VPS via Docker Compose.

## Credentials needed

See `.env.example` for the full list with setup links. Nothing is required
to run the API/GUI and explore the UI - each integration simply shows as
"not configured" (`GET /api/settings/credential-status`) until you add it.
