import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Platform, Streamer } from '../types'

export function StreamerManager() {
  const [streamers, setStreamers] = useState<Streamer[]>([])
  const [error, setError] = useState<string | null>(null)
  const [platform, setPlatform] = useState<Platform>('twitch')
  const [channelId, setChannelId] = useState('')
  const [displayName, setDisplayName] = useState('')

  async function refresh() {
    try {
      setStreamers(await api.listStreamers())
      setError(null)
    } catch {
      setError('Could not load streamers.')
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!channelId.trim() || !displayName.trim()) return
    await api.createStreamer({ platform, channel_id: channelId.trim(), display_name: displayName.trim() })
    setChannelId('')
    setDisplayName('')
    await refresh()
  }

  async function handleToggle(streamer: Streamer) {
    await api.setStreamerTracked(streamer.id, !streamer.is_tracked)
    await refresh()
  }

  async function handleDelete(streamer: Streamer) {
    await api.deleteStreamer(streamer.id)
    await refresh()
  }

  return (
    <section className="panel">
      <h2>Tracked Streamers</h2>
      {error && <p className="error">{error}</p>}

      <form className="streamer-form" onSubmit={handleAdd}>
        <select value={platform} onChange={(e) => setPlatform(e.target.value as Platform)}>
          <option value="twitch">Twitch</option>
          <option value="youtube">YouTube</option>
          <option value="kick">Kick</option>
        </select>
        <input
          placeholder="channel id / login"
          value={channelId}
          onChange={(e) => setChannelId(e.target.value)}
        />
        <input
          placeholder="display name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
        <button type="submit">Add</button>
      </form>

      {streamers.length === 0 ? (
        <p className="empty">No streamers tracked yet.</p>
      ) : (
        <ul className="streamer-list">
          {streamers.map((streamer) => (
            <li key={streamer.id}>
              <span className="platform-badge">{streamer.platform}</span>
              <span>{streamer.display_name}</span>
              <label>
                <input
                  type="checkbox"
                  checked={streamer.is_tracked}
                  onChange={() => handleToggle(streamer)}
                />
                tracked
              </label>
              <button type="button" onClick={() => handleDelete(streamer)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
