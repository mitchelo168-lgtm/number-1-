import type { Clip, CredentialStatus, Platform, ReviewStatus, Streamer } from '../types'

export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    throw new Error(`${init?.method ?? 'GET'} ${path} failed with ${response.status}`)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  listStreamers: () => request<Streamer[]>('/api/streamers'),

  createStreamer: (payload: { platform: Platform; channel_id: string; display_name: string }) =>
    request<Streamer>('/api/streamers', { method: 'POST', body: JSON.stringify(payload) }),

  setStreamerTracked: (id: number, is_tracked: boolean) =>
    request<Streamer>(`/api/streamers/${id}`, { method: 'PATCH', body: JSON.stringify({ is_tracked }) }),

  deleteStreamer: (id: number) => request<void>(`/api/streamers/${id}`, { method: 'DELETE' }),

  listClips: (reviewStatus?: ReviewStatus) =>
    request<Clip[]>(`/api/clips${reviewStatus ? `?review_status=${reviewStatus}` : ''}`),

  approveClip: (id: number) => request<Clip>(`/api/clips/${id}/approve`, { method: 'POST' }),

  rejectClip: (id: number) => request<Clip>(`/api/clips/${id}/reject`, { method: 'POST' }),

  getCredentialStatus: () => request<CredentialStatus>('/api/settings/credential-status'),
}
