import httpx
import respx

from streamclip.platforms.base import ChatMessage
from streamclip.platforms.twitch import TOKEN_URL, TwitchAdapter, TwitchTokenProvider


class FakeWebSocket:
    def __init__(self, lines: list[str]):
        self._lines = lines
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for line in self._lines:
            yield line


class FakeWSConnect:
    def __init__(self, ws: FakeWebSocket):
        self._ws = ws

    def __call__(self, url: str):
        return self

    async def __aenter__(self):
        return self._ws

    async def __aexit__(self, *exc):
        return False


@respx.mock
async def test_token_provider_fetches_and_caches():
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "abc123", "expires_in": 3600})
    )
    async with httpx.AsyncClient() as client:
        provider = TwitchTokenProvider(client, "cid", "secret")
        token1 = await provider.get_token()
        token2 = await provider.get_token()

    assert token1 == "abc123"
    assert token2 == "abc123"
    assert route.call_count == 1  # cached on second call


@respx.mock
async def test_check_live_when_offline():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
    )
    respx.get("https://api.twitch.tv/helix/streams").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    async with httpx.AsyncClient() as client:
        provider = TwitchTokenProvider(client, "cid", "secret")
        adapter = TwitchAdapter(client, "cid", provider)
        status = await adapter.check_live("shroud")

    assert status.is_live is False


@respx.mock
async def test_check_live_when_online():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
    )
    respx.get("https://api.twitch.tv/helix/streams").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "title": "Playing GTA 6",
                        "started_at": "2026-11-18T12:00:00Z",
                    }
                ]
            },
        )
    )
    async with httpx.AsyncClient() as client:
        provider = TwitchTokenProvider(client, "cid", "secret")
        adapter = TwitchAdapter(client, "cid", provider)
        status = await adapter.check_live("shroud")

    assert status.is_live is True
    assert status.title == "Playing GTA 6"
    assert status.stream_url == "https://twitch.tv/shroud"


async def test_stream_chat_parses_privmsg_and_handles_ping():
    fake_ws = FakeWebSocket(
        [
            "PING :tmi.twitch.tv",
            ":alice!alice@alice.tmi.twitch.tv PRIVMSG #shroud :pog moment",
            ":bob!bob@bob.tmi.twitch.tv PRIVMSG #shroud :lol that was insane",
        ]
    )

    async with httpx.AsyncClient() as client:
        provider = TwitchTokenProvider(client, "cid", "secret")
        adapter = TwitchAdapter(client, "cid", provider, ws_connect=FakeWSConnect(fake_ws))

        messages: list[ChatMessage] = []
        async for msg in adapter.stream_chat("shroud"):
            messages.append(msg)

    assert [m.author for m in messages] == ["alice", "bob"]
    assert messages[0].text == "pog moment"
    assert "PONG :tmi.twitch.tv" in fake_ws.sent
