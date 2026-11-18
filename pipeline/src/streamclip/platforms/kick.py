"""Kick platform adapter.

Kick's public API (https://api.kick.com/public/v1) and its chat transport
(Pusher websockets) are newer and less stable than Twitch/YouTube's, and
fields below are mapped from the documented shape at the time this was
written. If Kick's response schema has shifted, this is the first adapter
to re-verify against current docs — the field names in `check_live` /
`_get_chatroom_id` are the most likely things to need adjusting; the
request/response flow and the Pusher chat protocol itself are stable.
"""

import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from streamclip.platforms.base import ChatMessage, LiveStatus, PlatformAdapter

API_BASE = "https://api.kick.com/public/v1"
TOKEN_URL = "https://id.kick.com/oauth/token"
PUSHER_APP_KEY = "32cbd69e4b950bf97679"
PUSHER_WS_URL = f"wss://ws-us2.pusher.com/app/{PUSHER_APP_KEY}?protocol=7&client=streamclip&version=1.0&flash=false"


class KickTokenProvider:
    def __init__(self, client: httpx.AsyncClient, client_id: str, client_secret: str):
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None

    async def get_token(self) -> str:
        if self._token:
            return self._token
        resp = await self._client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token


class KickAdapter(PlatformAdapter):
    name = "kick"

    def __init__(
        self,
        client: httpx.AsyncClient,
        token_provider: KickTokenProvider,
        ws_connect: Callable[[str], Any] | None = None,
    ):
        self._client = client
        self._tokens = token_provider
        self._ws_connect = ws_connect or _default_ws_connect

    async def _get_channel(self, channel_id: str) -> dict | None:
        token = await self._tokens.get_token()
        resp = await self._client.get(
            f"{API_BASE}/channels",
            params={"slug": channel_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        items = resp.json().get("data", [])
        return items[0] if items else None

    async def check_live(self, channel_id: str) -> LiveStatus:
        channel = await self._get_channel(channel_id)
        if not channel:
            return LiveStatus(is_live=False)

        stream = channel.get("stream") or {}
        if not stream.get("is_live"):
            return LiveStatus(is_live=False)

        started_at = None
        if stream.get("started_at"):
            started_at = datetime.fromisoformat(stream["started_at"])

        return LiveStatus(
            is_live=True,
            stream_url=f"https://kick.com/{channel_id}",
            title=stream.get("stream_title") or channel.get("stream_title"),
            started_at=started_at,
        )

    async def stream_chat(self, channel_id: str) -> AsyncIterator[ChatMessage]:
        channel = await self._get_channel(channel_id)
        if not channel:
            return
        chatroom_id = channel.get("chatroom", {}).get("id")
        if not chatroom_id:
            return

        async with self._ws_connect(PUSHER_WS_URL) as ws:
            subscribe = {
                "event": "pusher:subscribe",
                "data": {"channel": f"chatrooms.{chatroom_id}.v2"},
            }
            await ws.send(json.dumps(subscribe))
            async for raw in ws:
                envelope = json.loads(raw)
                if envelope.get("event") != "App\\Events\\ChatMessageEvent":
                    continue
                payload = json.loads(envelope["data"])
                yield ChatMessage(
                    author=payload.get("sender", {}).get("username", "unknown"),
                    text=payload.get("content", ""),
                    timestamp=datetime.now(UTC),
                )


def _default_ws_connect(url: str):
    import websockets

    return websockets.connect(url)
