import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import { CredentialStatus } from './CredentialStatus'

vi.mock('../api/client', () => ({
  api: { getCredentialStatus: vi.fn() },
}))

describe('CredentialStatus', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('renders nothing until the status loads', () => {
    vi.mocked(api.getCredentialStatus).mockReturnValue(new Promise(() => {}))

    const { container } = render(<CredentialStatus />)

    expect(container).toBeEmptyDOMElement()
  })

  it('marks configured integrations as ok and the rest as missing', async () => {
    vi.mocked(api.getCredentialStatus).mockResolvedValue({
      twitch: true,
      youtube: false,
      kick: false,
      discord: true,
      post_for_me: false,
    })

    render(<CredentialStatus />)

    expect(await screen.findByText('Twitch')).toBeInTheDocument()
    const twitchDot = screen.getByText('Twitch').previousElementSibling
    expect(twitchDot).toHaveClass('ok')

    const youtubeDot = screen.getByText('YouTube').previousElementSibling
    expect(youtubeDot).toHaveClass('missing')
  })

  it('renders nothing if the request fails', async () => {
    vi.mocked(api.getCredentialStatus).mockRejectedValue(new Error('network error'))

    const { container } = render(<CredentialStatus />)

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(container).toBeEmptyDOMElement()
  })
})
