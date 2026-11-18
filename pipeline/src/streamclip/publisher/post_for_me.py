"""Client for the Post for Me unified social-posting API
(https://api.postforme.dev) — fans an approved clip out to every connected
social account. Endpoint paths and field names below were pulled directly
from the API's live OpenAPI spec (https://api.postforme.dev/docs), not
guessed.
"""

from dataclasses import dataclass
from pathlib import Path

import httpx

BASE_URL = "https://api.postforme.dev"


@dataclass(frozen=True)
class SocialAccount:
    id: str
    platform: str
    username: str | None
    status: str


@dataclass(frozen=True)
class PublishedPost:
    id: str
    status: str
    social_accounts: list[str]


class PostForMeClient:
    def __init__(self, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def list_connected_accounts(self) -> list[SocialAccount]:
        resp = await self._client.get(
            f"{BASE_URL}/v1/social-accounts",
            headers=self._headers(),
            params={"status": "connected"},
        )
        resp.raise_for_status()
        return [
            SocialAccount(id=a["id"], platform=a["platform"], username=a.get("username"), status=a["status"])
            for a in resp.json()["data"]
        ]

    async def upload_media(self, file_path: Path, content_type: str = "video/mp4") -> str:
        resp = await self._client.post(f"{BASE_URL}/v1/media/create-upload-url", headers=self._headers())
        resp.raise_for_status()
        payload = resp.json()

        put_resp = await self._client.put(
            payload["upload_url"], content=file_path.read_bytes(), headers={"Content-Type": content_type}
        )
        put_resp.raise_for_status()
        return payload["media_url"]

    async def create_post(self, caption: str, media_url: str, social_account_ids: list[str]) -> PublishedPost:
        body = {
            "caption": caption,
            "social_accounts": social_account_ids,
            "media": [{"url": media_url}],
        }
        resp = await self._client.post(f"{BASE_URL}/v1/social-posts", headers=self._headers(), json=body)
        resp.raise_for_status()
        payload = resp.json()
        return PublishedPost(
            id=payload["id"],
            status=payload["status"],
            social_accounts=[a["id"] for a in payload["social_accounts"]],
        )

    async def publish_clip(
        self, file_path: Path, caption: str, social_account_ids: list[str] | None = None
    ) -> PublishedPost:
        """High-level helper: resolves every connected account if none are
        given, uploads the clip, and creates the post."""
        if social_account_ids is None:
            social_account_ids = [a.id for a in await self.list_connected_accounts()]
        media_url = await self.upload_media(file_path)
        return await self.create_post(caption, media_url, social_account_ids)
