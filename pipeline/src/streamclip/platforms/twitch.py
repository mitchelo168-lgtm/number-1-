import re
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from streamclip.platforms.base import ChatMessage, LiveStatus, PlatformAdapter

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX_STREAMS_URL = "https://api.twitch.tv/helix/streams"
IRC_WS_URL = "wss://irc-ws.chat.twitch.tv:443"

# Parses a Twitch IRC PRIVMSG line, e.g.:
# ":nick!nick@nick.tmi.twitch.tv PRIVMSG #channel :hello world"
PRIVMSG_RE = re.compile(r"^:(?P<nick>[^!]+)!\S+ PRIVMSG #\S+ :(?P<text>.*)$")


class TwitchTokenProvider:
    """Caches a Twitch app access token (client-credentials flow) until it expires."""

    def __init__(self, client: httpx.AsyncClient, client_id: str, client_secret: str):
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float = 0.0

    async def get_token(self) -> str:
        if self._token and time.monotonic() < self._expires_at:
            return self._token
        resp = await self._client.post(
            TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._expires_at = time.monotonic() + payload.get("expires_in", 3600) - 30
        return self._token


class TwitchAdapter(PlatformAdapter):
    name = "twitch"

    def __init__(
        self,
        client: httpx.AsyncClient,
        client_id: str,
        token_provider: TwitchTokenProvider,
        ws_connect: Callable[[str], Any] | None = None,
    ):
        self._client = client
        self._client_id = client_id
        self._tokens = token_provider
        # Injected for testing; defaults to the real `websockets.connect`.
        self._ws_connect = ws_connect or _default_ws_connect

    async def check_live(self, channel_id: str) -> LiveStatus:
        token = await self._tokens.get_token()
        resp = await self._client.get(
            HELIX_STREAMS_URL,
            params={"user_login": channel_id},
            headers={"Authorization": f"Bearer {token}", "Client-Id": self._client_id},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return LiveStatus(is_live=False)
        stream = data[0]
        started_at = datetime.fromisoformat(stream["started_at"])
        return LiveStatus(
            is_live=True,
            stream_url=f"https://twitch.tv/{channel_id}",
            title=stream.get("title"),
            started_at=started_at,
        )

    async def stream_chat(self, channel_id: str) -> AsyncIterator[ChatMessage]:
        async with self._ws_connect(IRC_WS_URL) as ws:
            await ws.send("CAP REQ :twitch.tv/tags")
            await ws.send("PASS SCHMOOPIIE")
            await ws.send("NICK justinfan12345")
            await ws.send(f"JOIN #{channel_id.lower()}")
            async for raw in ws:
                for line in raw.splitlines():
                    if line.startswith("PING"):
                        await ws.send("PONG :tmi.twitch.tv")
                        continue
                    match = PRIVMSG_RE.match(line)
                    if match:
                        yield ChatMessage(
                            author=match.group("nick"),
                            text=match.group("text"),
                            timestamp=datetime.now(UTC),
                        )


def _default_ws_connect(url: str):
    import websockets

    return websockets.connect(url)
