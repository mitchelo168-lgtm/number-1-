import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import type { Clip } from '../types'
import { ClipReviewQueue } from './ClipReviewQueue'

vi.mock('../api/client', () => ({
  api: {
    listClips: vi.fn(),
    approveClip: vi.fn(),
    rejectClip: vi.fn(),
  },
  BASE_URL: 'http://localhost:8000',
}))

const clip: Clip = {
  id: 42,
  session_id: 1,
  file_path: '/clips/a.mp4',
  trigger_offset_seconds: 100,
  clip_start_seconds: 60,
  clip_end_seconds: 110,
  highlight_score: 0.87,
  signal_breakdown: { chat: 0.9, audio: 0.5 },
  review_status: 'pending',
  publish_status: 'not_published',
  created_at: '2026-11-18T12:00:00Z',
  reviewed_at: null,
  video_url: '/media/clips/a.mp4',
}

describe('ClipReviewQueue', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('shows an empty state when nothing is pending', async () => {
    vi.mocked(api.listClips).mockResolvedValue([])

    render(<ClipReviewQueue />)

    expect(await screen.findByText(/nothing waiting for review/i)).toBeInTheDocument()
    expect(api.listClips).toHaveBeenCalledWith('pending')
  })

  it('renders a pending clip with its score and window', async () => {
    vi.mocked(api.listClips).mockResolvedValue([clip])

    render(<ClipReviewQueue />)

    expect(await screen.findByText(/score: 0.87/)).toBeInTheDocument()
    expect(screen.getByText(/60s/)).toBeInTheDocument()
    const videoEl = document.querySelector('video') as HTMLVideoElement
    expect(videoEl.src).toBe('http://localhost:8000/media/clips/a.mp4')
  })

  it('approves a clip and refreshes the queue', async () => {
    vi.mocked(api.listClips).mockResolvedValueOnce([clip]).mockResolvedValueOnce([])
    vi.mocked(api.approveClip).mockResolvedValue({ ...clip, review_status: 'approved' })
    const user = userEvent.setup()

    render(<ClipReviewQueue />)
    await screen.findByText(/score: 0.87/)

    await user.click(screen.getByRole('button', { name: /approve/i }))

    await waitFor(() => expect(api.approveClip).toHaveBeenCalledWith(42))
    expect(await screen.findByText(/nothing waiting for review/i)).toBeInTheDocument()
  })

  it('rejects a clip and refreshes the queue', async () => {
    vi.mocked(api.listClips).mockResolvedValueOnce([clip]).mockResolvedValueOnce([])
    vi.mocked(api.rejectClip).mockResolvedValue({ ...clip, review_status: 'rejected' })
    const user = userEvent.setup()

    render(<ClipReviewQueue />)
    await screen.findByText(/score: 0.87/)

    await user.click(screen.getByRole('button', { name: /reject/i }))

    await waitFor(() => expect(api.rejectClip).toHaveBeenCalledWith(42))
  })
})
