import { useEffect, useState } from 'react'
import { api, BASE_URL } from '../api/client'
import type { Clip } from '../types'

export function ClipReviewQueue() {
  const [clips, setClips] = useState<Clip[]>([])
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    try {
      setClips(await api.listClips('pending'))
      setError(null)
    } catch {
      setError('Could not load clips.')
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleApprove(clip: Clip) {
    await api.approveClip(clip.id)
    await refresh()
  }

  async function handleReject(clip: Clip) {
    await api.rejectClip(clip.id)
    await refresh()
  }

  return (
    <section className="panel">
      <h2>Clips awaiting review</h2>
      {error && <p className="error">{error}</p>}

      {clips.length === 0 ? (
        <p className="empty">Nothing waiting for review right now.</p>
      ) : (
        <ul className="clip-list">
          {clips.map((clip) => (
            <li key={clip.id} className="clip-card">
              <video controls src={`${BASE_URL}${clip.video_url}`} />
              <div className="clip-meta">
                <span>score: {clip.highlight_score.toFixed(2)}</span>
                <span>
                  {clip.clip_start_seconds.toFixed(0)}s &rarr; {clip.clip_end_seconds.toFixed(0)}s
                </span>
              </div>
              <div className="clip-actions">
                <button type="button" className="approve" onClick={() => handleApprove(clip)}>
                  Approve
                </button>
                <button type="button" className="reject" onClick={() => handleReject(clip)}>
                  Reject
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
