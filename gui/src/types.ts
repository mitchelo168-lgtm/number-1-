export type Platform = 'twitch' | 'youtube' | 'kick'
export type ReviewStatus = 'pending' | 'approved' | 'rejected'
export type PublishStatus = 'not_published' | 'queued' | 'published' | 'failed'

export interface Streamer {
  id: number
  platform: Platform
  channel_id: string
  display_name: string
  is_tracked: boolean
  created_at: string
}

export interface Clip {
  id: number
  session_id: number
  file_path: string
  trigger_offset_seconds: number
  clip_start_seconds: number
  clip_end_seconds: number
  highlight_score: number
  signal_breakdown: Record<string, number | null>
  review_status: ReviewStatus
  publish_status: PublishStatus
  created_at: string
  reviewed_at: string | null
  video_url: string
}

export interface CredentialStatus {
  twitch: boolean
  youtube: boolean
  kick: boolean
  discord: boolean
  post_for_me: boolean
}
