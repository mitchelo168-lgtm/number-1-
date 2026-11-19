from streamclip.config import Settings


def test_blank_env_values_fall_back_to_field_defaults(tmp_path, monkeypatch):
    """Regression test: .env.example leaves every unused credential as
    `KEY=` (blank). A blank value for an int field like
    discord_review_channel_id must not crash startup - it should behave
    exactly as if the key were absent."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TWITCH_CLIENT_ID=\n"
        "DISCORD_REVIEW_CHANNEL_ID=\n"
        "POST_FOR_ME_API_KEY=real-key\n"
    )

    settings = Settings(_env_file=env_file)

    assert settings.twitch_client_id is None
    assert settings.discord_review_channel_id is None
    assert settings.post_for_me_api_key == "real-key"


def test_non_blank_int_env_value_is_still_parsed(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_REVIEW_CHANNEL_ID=123456789\n")

    settings = Settings(_env_file=env_file)

    assert settings.discord_review_channel_id == 123456789
