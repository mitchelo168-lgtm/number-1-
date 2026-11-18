import pytest

from streamclip.discord_bot.bot import parse_custom_id
from streamclip.discord_bot.review_bot import DiscordReviewBot, ReviewMessage
from streamclip.models import Clip, Platform, ReviewStatus, StreamSession, Streamer


@pytest.mark.parametrize(
    "custom_id,expected",
    [
        ("streamclip:approve:42", ("approve", 42)),
        ("streamclip:reject:7", ("reject", 7)),
        ("streamclip:approve:nope", None),
        ("something:else:1", None),
        ("", None),
    ],
)
def test_parse_custom_id(custom_id, expected):
    assert parse_custom_id(custom_id) == expected


async def _make_clip(session_factory) -> int:
    async with session_factory() as session:
        streamer = Streamer(platform=Platform.TWITCH, channel_id="shroud", display_name="shroud")
        session.add(streamer)
        await session.flush()
        stream_session = StreamSession(streamer_id=streamer.id, stream_url="https://twitch.tv/shroud")
        session.add(stream_session)
        await session.flush()
        clip = Clip(
            session_id=stream_session.id,
            file_path="/clips/a.mp4",
            trigger_offset_seconds=100.0,
            clip_start_seconds=60.0,
            clip_end_seconds=110.0,
            highlight_score=0.8,
        )
        session.add(clip)
        await session.commit()
        return clip.id


async def test_notify_live_sends_expected_message(session_factory):
    sent = []

    async def fake_send(message: ReviewMessage) -> None:
        sent.append(message)

    bot = DiscordReviewBot(session_factory, send=fake_send, review_channel_id=123)
    await bot.notify_live("shroud", "twitch")

    assert len(sent) == 1
    assert sent[0].channel_id == 123
    assert "shroud" in sent[0].content
    assert "twitch" in sent[0].content
    assert sent[0].clip_id is None


async def test_notify_clip_ready_includes_file_and_clip_id(session_factory):
    clip_id = await _make_clip(session_factory)
    sent = []

    async def fake_send(message: ReviewMessage) -> None:
        sent.append(message)

    bot = DiscordReviewBot(session_factory, send=fake_send, review_channel_id=123)

    async with session_factory() as session:
        clip = await session.get(Clip, clip_id)
        await bot.notify_clip_ready(clip, "shroud")

    assert sent[0].clip_id == clip_id
    assert sent[0].file_path == "/clips/a.mp4"
    assert "0.80" in sent[0].content


async def test_handle_review_decision_approve_updates_db_and_fires_callback(session_factory):
    clip_id = await _make_clip(session_factory)
    approved_clips = []

    async def on_approved(clip: Clip) -> None:
        approved_clips.append(clip.id)

    bot = DiscordReviewBot(
        session_factory, send=lambda m: None, review_channel_id=123, on_approved=on_approved
    )

    clip = await bot.handle_review_decision(clip_id, approved=True)

    assert clip.review_status == ReviewStatus.APPROVED
    assert clip.reviewed_at is not None
    assert approved_clips == [clip_id]

    async with session_factory() as session:
        persisted = await session.get(Clip, clip_id)
        assert persisted.review_status == ReviewStatus.APPROVED


async def test_handle_review_decision_reject_does_not_fire_approved_callback(session_factory):
    clip_id = await _make_clip(session_factory)
    approved_clips = []

    async def on_approved(clip: Clip) -> None:
        approved_clips.append(clip.id)

    bot = DiscordReviewBot(
        session_factory, send=lambda m: None, review_channel_id=123, on_approved=on_approved
    )

    clip = await bot.handle_review_decision(clip_id, approved=False)

    assert clip.review_status == ReviewStatus.REJECTED
    assert approved_clips == []


async def test_handle_review_decision_unknown_clip_raises(session_factory):
    bot = DiscordReviewBot(session_factory, send=lambda m: None, review_channel_id=123)

    with pytest.raises(ValueError, match="no clip with id 999"):
        await bot.handle_review_decision(999, approved=True)
