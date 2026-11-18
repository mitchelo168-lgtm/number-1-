import asyncio
from collections.abc import AsyncIterator
from datetime import datetime

import httpx

from streamclip.platforms.base import ChatMessage, LiveStatus, PlatformAdapter

API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeAdapter(PlatformAdapter):
    name = "youtube"

    def __init__(self, client: httpx.AsyncClient, api_key: str, sleep: callable = asyncio.sleep):
        self._client = client
        self._api_key = api_key
        self._sleep = sleep

    async def _find_live_video_id(self, channel_id: str) -> str | None:
        resp = await self._client.get(
            f"{API_BASE}/search",
            params={
                "part": "snippet",
                "channelId": channel_id,
                "eventType": "live",
                "type": "video",
                "key": self._api_key,
            },
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return None
        return items[0]["id"]["videoId"]

    async def check_live(self, channel_id: str) -> LiveStatus:
        video_id = await self._find_live_video_id(channel_id)
        if not video_id:
            return LiveStatus(is_live=False)

        resp = await self._client.get(
            f"{API_BASE}/videos",
            params={"part": "liveStreamingDetails,snippet", "id": video_id, "key": self._api_key},
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return LiveStatus(is_live=False)

        item = items[0]
        details = item.get("liveStreamingDetails", {})
        started_at = None
        if details.get("actualStartTime"):
            started_at = datetime.fromisoformat(details["actualStartTime"])

        return LiveStatus(
            is_live=True,
            stream_url=f"https://www.youtube.com/watch?v={video_id}",
            title=item.get("snippet", {}).get("title"),
            started_at=started_at,
        )

    async def _get_active_live_chat_id(self, channel_id: str) -> str | None:
        video_id = await self._find_live_video_id(channel_id)
        if not video_id:
            return None
        resp = await self._client.get(
            f"{API_BASE}/videos",
            params={"part": "liveStreamingDetails", "id": video_id, "key": self._api_key},
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return None
        return items[0].get("liveStreamingDetails", {}).get("activeLiveChatId")

    async def stream_chat(self, channel_id: str) -> AsyncIterator[ChatMessage]:
        live_chat_id = await self._get_active_live_chat_id(channel_id)
        if not live_chat_id:
            return

        page_token: str | None = None
        while True:
            params = {
                "liveChatId": live_chat_id,
                "part": "snippet,authorDetails",
                "key": self._api_key,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await self._client.get(f"{API_BASE}/liveChat/messages", params=params)
            resp.raise_for_status()
            payload = resp.json()

            for item in payload.get("items", []):
                snippet = item["snippet"]
                yield ChatMessage(
                    author=item["authorDetails"]["displayName"],
                    text=snippet.get("displayMessage", ""),
                    timestamp=datetime.fromisoformat(snippet["publishedAt"]),
                )

            page_token = payload.get("nextPageToken")
            await self._sleep(payload.get("pollingIntervalMillis", 5000) / 1000)
