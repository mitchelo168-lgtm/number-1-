import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import type { Streamer } from '../types'
import { StreamerManager } from './StreamerManager'

vi.mock('../api/client', () => ({
  api: {
    listStreamers: vi.fn(),
    createStreamer: vi.fn(),
    setStreamerTracked: vi.fn(),
    deleteStreamer: vi.fn(),
  },
}))

const streamer: Streamer = {
  id: 1,
  platform: 'twitch',
  channel_id: 'shroud',
  display_name: 'shroud',
  is_tracked: true,
  created_at: '2026-11-18T12:00:00Z',
}

describe('StreamerManager', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('shows an empty state when there are no streamers', async () => {
    vi.mocked(api.listStreamers).mockResolvedValue([])

    render(<StreamerManager />)

    expect(await screen.findByText(/no streamers tracked yet/i)).toBeInTheDocument()
  })

  it('renders fetched streamers', async () => {
    vi.mocked(api.listStreamers).mockResolvedValue([streamer])

    render(<StreamerManager />)

    expect(await screen.findByText('shroud')).toBeInTheDocument()
    expect(screen.getByText('twitch')).toBeInTheDocument()
  })

  it('submits the add-streamer form and refreshes the list', async () => {
    vi.mocked(api.listStreamers).mockResolvedValueOnce([]).mockResolvedValueOnce([streamer])
    vi.mocked(api.createStreamer).mockResolvedValue(streamer)
    const user = userEvent.setup()

    render(<StreamerManager />)
    await screen.findByText(/no streamers tracked yet/i)

    await user.type(screen.getByPlaceholderText(/channel id/i), 'shroud')
    await user.type(screen.getByPlaceholderText(/display name/i), 'shroud')
    await user.click(screen.getByRole('button', { name: /add/i }))

    await waitFor(() =>
      expect(api.createStreamer).toHaveBeenCalledWith({
        platform: 'twitch',
        channel_id: 'shroud',
        display_name: 'shroud',
      })
    )
    expect(await screen.findByText('shroud')).toBeInTheDocument()
  })

  it('does not submit when fields are blank', async () => {
    vi.mocked(api.listStreamers).mockResolvedValue([])
    const user = userEvent.setup()

    render(<StreamerManager />)
    await screen.findByText(/no streamers tracked yet/i)

    await user.click(screen.getByRole('button', { name: /add/i }))

    expect(api.createStreamer).not.toHaveBeenCalled()
  })

  it('toggles tracked state', async () => {
    vi.mocked(api.listStreamers).mockResolvedValueOnce([streamer]).mockResolvedValueOnce([
      { ...streamer, is_tracked: false },
    ])
    vi.mocked(api.setStreamerTracked).mockResolvedValue({ ...streamer, is_tracked: false })
    const user = userEvent.setup()

    render(<StreamerManager />)
    await screen.findByText('shroud')

    await user.click(screen.getByRole('checkbox'))

    expect(api.setStreamerTracked).toHaveBeenCalledWith(1, false)
  })

  it('removes a streamer', async () => {
    vi.mocked(api.listStreamers).mockResolvedValueOnce([streamer]).mockResolvedValueOnce([])
    vi.mocked(api.deleteStreamer).mockResolvedValue(undefined)
    const user = userEvent.setup()

    render(<StreamerManager />)
    await screen.findByText('shroud')

    await user.click(screen.getByRole('button', { name: /remove/i }))

    expect(api.deleteStreamer).toHaveBeenCalledWith(1)
    expect(await screen.findByText(/no streamers tracked yet/i)).toBeInTheDocument()
  })
})
