import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { CredentialStatus as CredentialStatusType } from '../types'

const LABELS: Record<keyof CredentialStatusType, string> = {
  twitch: 'Twitch',
  youtube: 'YouTube',
  kick: 'Kick',
  discord: 'Discord',
  post_for_me: 'Post for Me',
}

export function CredentialStatus() {
  const [status, setStatus] = useState<CredentialStatusType | null>(null)

  useEffect(() => {
    api.getCredentialStatus().then(setStatus).catch(() => setStatus(null))
  }, [])

  if (!status) return null

  return (
    <section className="panel credential-status">
      <h2>Integrations</h2>
      <ul>
        {Object.entries(LABELS).map(([key, label]) => (
          <li key={key}>
            <span className={`dot ${status[key as keyof CredentialStatusType] ? 'ok' : 'missing'}`} />
            <span className="label">{label}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
