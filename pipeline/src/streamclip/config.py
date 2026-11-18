from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All external configuration. Every field is optional so the app can boot,
    run its full test suite, and serve the GUI with zero credentials configured;
    each integration simply reports itself as "not configured" until its
    fields are set.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./streamclip.db"

    # Twitch (developer console: https://dev.twitch.tv/console/apps)
    twitch_client_id: str | None = None
    twitch_client_secret: str | None = None

    # YouTube Data API v3 (Google Cloud Console)
    youtube_api_key: str | None = None

    # Kick (public API token, if/when required)
    kick_client_id: str | None = None
    kick_client_secret: str | None = None

    # Discord bot
    discord_bot_token: str | None = None
    discord_review_channel_id: int | None = None

    # Post for Me (https://postforme.dev or similar unified posting API)
    post_for_me_api_key: str | None = None

    # Storage
    recordings_dir: str = "./data/recordings"
    clips_dir: str = "./data/clips"

    # Highlight detection tuning
    highlight_pre_roll_seconds: float = 40.0
    highlight_post_roll_seconds: float = 10.0
    chat_rate_zscore_threshold: float = 2.5
    audio_event_confidence_threshold: float = 0.6

    poll_interval_seconds: float = 120.0
    chunk_duration_seconds: float = 600.0


def get_settings() -> Settings:
    return Settings()
