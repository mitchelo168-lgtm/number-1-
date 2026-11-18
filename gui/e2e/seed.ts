import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const DATA_DIR = path.join(__dirname, '.tmp-e2e-data')
const PIPELINE_DIR = path.join(__dirname, '..', '..', 'pipeline')
const DB_PATH = path.join(DATA_DIR, 'e2e.db')
const CLIPS_DIR = path.join(DATA_DIR, 'clips')

export function clipsDir(): string {
  return CLIPS_DIR
}

/** Generates a tiny real .ts clip via ffmpeg and inserts a matching pending
 * Clip row directly into the deterministic e2e sqlite DB the API server
 * under test is already using - this is the one piece the GUI can't create
 * itself over the REST API (clips normally come from the orchestrator). */
export function seedPendingClip(fileName: string, highlightScore = 0.91): number {
  const filePath = path.join(CLIPS_DIR, fileName)
  const channelId = `e2e-${fileName}`
  execFileSync('ffmpeg', [
    '-loglevel', 'error', '-y',
    '-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=10:duration=2',
    '-c:v', 'libx264',
    filePath,
  ])

  const script = `
import asyncio
from streamclip.db import make_engine, make_session_factory
from streamclip.models import Clip, Platform, StreamSession, Streamer

async def main():
    engine = make_engine("sqlite+aiosqlite:///${DB_PATH}")
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        streamer = Streamer(platform=Platform.TWITCH, channel_id="${channelId}", display_name="e2e-streamer")
        session.add(streamer)
        await session.flush()
        stream_session = StreamSession(streamer_id=streamer.id, stream_url="https://twitch.tv/e2e")
        session.add(stream_session)
        await session.flush()
        clip = Clip(
            session_id=stream_session.id,
            file_path="${filePath}",
            trigger_offset_seconds=100.0,
            clip_start_seconds=60.0,
            clip_end_seconds=110.0,
            highlight_score=${highlightScore},
        )
        session.add(clip)
        await session.commit()
        print(clip.id)
    await engine.dispose()

asyncio.run(main())
`
  const output = execFileSync(path.join(PIPELINE_DIR, '.venv', 'bin', 'python'), ['-I', '-c', script], {
    encoding: 'utf-8',
  })
  return Number(output.trim())
}
