import httpx
import respx

from streamclip.platforms.youtube import YouTubeAdapter


@respx.mock
async def test_check_live_when_no_live_video():
    respx.get("https://www.googleapis.com/youtube/v3/search").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    async with httpx.AsyncClient() as client:
        adapter = YouTubeAdapter(client, "key")
        status = await adapter.check_live("UC123")

    assert status.is_live is False


@respx.mock
async def test_check_live_when_live():
    respx.get("https://www.googleapis.com/youtube/v3/search").mock(
        return_value=httpx.Response(200, json={"items": [{"id": {"videoId": "vid1"}}]})
    )
    respx.get("https://www.googleapis.com/youtube/v3/videos").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "snippet": {"title": "GTA 6 is live"},
                        "liveStreamingDetails": {
                            "actualStartTime": "2026-11-18T12:00:00Z",
                            "activeLiveChatId": "chat1",
                        },
                    }
                ]
            },
        )
    )
    async with httpx.AsyncClient() as client:
        adapter = YouTubeAdapter(client, "key")
        status = await adapter.check_live("UC123")

    assert status.is_live is True
    assert status.title == "GTA 6 is live"
    assert status.stream_url == "https://www.youtube.com/watch?v=vid1"


@respx.mock
async def test_stream_chat_paginates_and_sleeps_between_polls():
    respx.get("https://www.googleapis.com/youtube/v3/search").mock(
        return_value=httpx.Response(200, json={"items": [{"id": {"videoId": "vid1"}}]})
    )
    respx.get("https://www.googleapis.com/youtube/v3/videos").mock(
        return_value=httpx.Response(
            200,
            json={"items": [{"liveStreamingDetails": {"activeLiveChatId": "chat1"}}]},
        )
    )

    call_count = {"n": 0}

    def chat_responder(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "snippet": {"displayMessage": "hype", "publishedAt": "2026-11-18T12:00:01Z"},
                            "authorDetails": {"displayName": "carl"},
                        }
                    ],
                    "nextPageToken": "page2",
                    "pollingIntervalMillis": 1,
                },
            )
        raise StopAsyncIteration  # sentinel we catch below via sleep override

    respx.get("https://www.googleapis.com/youtube/v3/liveChat/messages").mock(
        side_effect=chat_responder
    )

    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise RuntimeError("stop-after-first-poll")

    async with httpx.AsyncClient() as client:
        adapter = YouTubeAdapter(client, "key", sleep=fake_sleep)
        messages = []
        try:
            async for msg in adapter.stream_chat("UC123"):
                messages.append(msg)
        except RuntimeError:
            pass

    assert len(messages) == 1
    assert messages[0].author == "carl"
    assert messages[0].text == "hype"
    assert sleep_calls == [0.001]
