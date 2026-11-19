import httpx
import pytest

from streamclip.api.app import create_app
from streamclip.config import Settings
from streamclip.db import init_db

pytestmark = pytest.mark.integration


@pytest.fixture
async def app(tmp_path):
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    application = create_app(settings)
    await init_db(application.state.engine)
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def api_client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_health_check(api_client):
    resp = await api_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_create_list_update_delete_streamer(api_client):
    create_resp = await api_client.post(
        "/api/streamers", json={"platform": "twitch", "channel_id": "shroud", "display_name": "shroud"}
    )
    assert create_resp.status_code == 201
    streamer = create_resp.json()
    assert streamer["is_tracked"] is True
    streamer_id = streamer["id"]

    list_resp = await api_client.get("/api/streamers")
    assert len(list_resp.json()) == 1

    patch_resp = await api_client.patch(f"/api/streamers/{streamer_id}", json={"is_tracked": False})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_tracked"] is False

    delete_resp = await api_client.delete(f"/api/streamers/{streamer_id}")
    assert delete_resp.status_code == 204

    list_resp_after = await api_client.get("/api/streamers")
    assert list_resp_after.json() == []


async def test_update_unknown_streamer_404s(api_client):
    resp = await api_client.patch("/api/streamers/999", json={"is_tracked": False})
    assert resp.status_code == 404


async def _seed_clip(app) -> int:
    # Creating a clip goes through the orchestrator/DB layer directly in
    # production; streamers/sessions aren't created via the API, so this
    # seeds one straight through the app's own session_factory instead of
    # re-implementing those routes just for a test.
    from streamclip.models import Clip, Platform, Streamer, StreamSession

    async with app.state.session_factory() as session:
        streamer = Streamer(platform=Platform.TWITCH, channel_id="s", display_name="s")
        session.add(streamer)
        await session.flush()
        stream_session = StreamSession(streamer_id=streamer.id, stream_url="https://twitch.tv/s")
        session.add(stream_session)
        await session.flush()
        clip = Clip(
            session_id=stream_session.id,
            file_path="/clips/a.mp4",
            trigger_offset_seconds=10.0,
            clip_start_seconds=5.0,
            clip_end_seconds=15.0,
            highlight_score=0.75,
        )
        session.add(clip)
        await session.commit()
        return clip.id


async def test_list_clips_and_approve_flow(app, api_client):
    clip_id = await _seed_clip(app)

    list_resp = await api_client.get("/api/clips")
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["review_status"] == "pending"
    assert list_resp.json()[0]["video_url"] == "/media/clips/a.mp4"

    pending_resp = await api_client.get("/api/clips", params={"review_status": "pending"})
    assert len(pending_resp.json()) == 1

    approve_resp = await api_client.post(f"/api/clips/{clip_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["review_status"] == "approved"
    assert approve_resp.json()["reviewed_at"] is not None

    pending_after = await api_client.get("/api/clips", params={"review_status": "pending"})
    assert pending_after.json() == []


async def test_reject_unknown_clip_404s(api_client):
    resp = await api_client.post("/api/clips/999/reject")
    assert resp.status_code == 404


async def test_credential_status_reflects_configured_settings(tmp_path):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'c.db'}",
        twitch_client_id="id",
        twitch_client_secret="secret",
        post_for_me_api_key="pfm-key",
    )
    app = create_app(settings)
    await init_db(app.state.engine)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/settings/credential-status")

    assert resp.json() == {
        "twitch": True,
        "youtube": False,
        "kick": False,
        "discord": False,
        "post_for_me": True,
    }
    await app.state.engine.dispose()
