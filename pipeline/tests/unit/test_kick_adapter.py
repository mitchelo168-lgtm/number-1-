import json

import httpx
import respx

from streamclip.platforms.kick import (
    API_BASE,
    TOKEN_URL,
    KickAdapter,
    KickTokenProvider,
)


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
async def test_check_live_when_offline():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.get(f"{API_BASE}/channels").mock(
        return_value=httpx.Response(200, json={"data": [{"stream": {"is_live": False}}]})
    )
    async with httpx.AsyncClient() as client:
        provider = KickTokenProvider(client, "cid", "secret")
        adapter = KickAdapter(client, provider)
        status = await adapter.check_live("xqc")

    assert status.is_live is False


@respx.mock
async def test_check_live_when_online():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.get(f"{API_BASE}/channels").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "stream": {
                            "is_live": True,
                            "stream_title": "GTA 6 release stream",
                            "started_at": "2026-11-18T12:00:00Z",
                        },
                        "chatroom": {"id": 999},
                    }
                ]
            },
        )
    )
    async with httpx.AsyncClient() as client:
        provider = KickTokenProvider(client, "cid", "secret")
        adapter = KickAdapter(client, provider)
        status = await adapter.check_live("xqc")

    assert status.is_live is True
    assert status.title == "GTA 6 release stream"
    assert status.stream_url == "https://kick.com/xqc"


@respx.mock
async def test_stream_chat_subscribes_and_parses_messages():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.get(f"{API_BASE}/channels").mock(
        return_value=httpx.Response(200, json={"data": [{"chatroom": {"id": 999}}]})
    )

    chat_event = {
        "event": "App\\Events\\ChatMessageEvent",
        "data": json.dumps({"sender": {"username": "dave"}, "content": "no way"}),
    }
    fake_ws = FakeWebSocket([json.dumps({"event": "pusher:connection_established"}), json.dumps(chat_event)])

    async with httpx.AsyncClient() as client:
        provider = KickTokenProvider(client, "cid", "secret")
        adapter = KickAdapter(client, provider, ws_connect=FakeWSConnect(fake_ws))

        messages = []
        async for msg in adapter.stream_chat("xqc"):
            messages.append(msg)

    assert len(messages) == 1
    assert messages[0].author == "dave"
    assert messages[0].text == "no way"
    subscribe_payload = json.loads(fake_ws.sent[0])
    assert subscribe_payload["data"]["channel"] == "chatrooms.999.v2"
