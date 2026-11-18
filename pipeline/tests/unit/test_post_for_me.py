import httpx
import respx

from streamclip.publisher.post_for_me import BASE_URL, PostForMeClient


@respx.mock
async def test_list_connected_accounts_parses_paginated_response():
    respx.get(f"{BASE_URL}/v1/social-accounts").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": "spc_1", "platform": "tiktok", "username": "kaylumai", "status": "connected"},
                    {"id": "spc_2", "platform": "youtube", "username": None, "status": "connected"},
                ],
                "meta": {"total": 2, "offset": 0, "limit": 50},
            },
        )
    )
    async with httpx.AsyncClient() as http_client:
        client = PostForMeClient(http_client, api_key="key123")
        accounts = await client.list_connected_accounts()

    assert [a.id for a in accounts] == ["spc_1", "spc_2"]
    assert accounts[0].platform == "tiktok"
    assert accounts[1].username is None

    sent_request = respx.calls.last.request
    assert sent_request.headers["authorization"] == "Bearer key123"
    assert sent_request.url.params["status"] == "connected"


@respx.mock
async def test_upload_media_requests_signed_url_then_puts_file_bytes(tmp_path):
    clip_path = tmp_path / "clip.mp4"
    clip_path.write_bytes(b"fake-video-bytes")

    respx.post(f"{BASE_URL}/v1/media/create-upload-url").mock(
        return_value=httpx.Response(
            200, json={"upload_url": "https://storage.example/signed", "media_url": "https://cdn.example/clip.mp4"}
        )
    )
    put_route = respx.put("https://storage.example/signed").mock(return_value=httpx.Response(200))

    async with httpx.AsyncClient() as http_client:
        client = PostForMeClient(http_client, api_key="key123")
        media_url = await client.upload_media(clip_path, content_type="video/mp4")

    assert media_url == "https://cdn.example/clip.mp4"
    assert put_route.called
    put_request = put_route.calls.last.request
    assert put_request.headers["content-type"] == "video/mp4"
    assert put_request.content == b"fake-video-bytes"


@respx.mock
async def test_create_post_sends_expected_body_and_parses_response():
    respx.post(f"{BASE_URL}/v1/social-posts").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "post_1",
                "external_id": None,
                "caption": "clip of the day",
                "status": "processing",
                "scheduled_at": None,
                "platform_configurations": None,
                "account_configurations": None,
                "media": [{"url": "https://cdn.example/clip.mp4"}],
                "social_accounts": [{"id": "spc_1", "platform": "tiktok", "username": "kaylumai"}],
                "created_at": "2026-11-18T12:00:00Z",
                "updated_at": "2026-11-18T12:00:00Z",
            },
        )
    )

    async with httpx.AsyncClient() as http_client:
        client = PostForMeClient(http_client, api_key="key123")
        post = await client.create_post("clip of the day", "https://cdn.example/clip.mp4", ["spc_1"])

    assert post.id == "post_1"
    assert post.status == "processing"
    assert post.social_accounts == ["spc_1"]

    sent_body = respx.calls.last.request.content
    import json

    body = json.loads(sent_body)
    assert body == {
        "caption": "clip of the day",
        "social_accounts": ["spc_1"],
        "media": [{"url": "https://cdn.example/clip.mp4"}],
    }


@respx.mock
async def test_publish_clip_resolves_accounts_uploads_then_posts(tmp_path):
    clip_path = tmp_path / "clip.mp4"
    clip_path.write_bytes(b"bytes")

    respx.get(f"{BASE_URL}/v1/social-accounts").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "spc_1", "platform": "tiktok", "username": "a", "status": "connected"}]}
        )
    )
    respx.post(f"{BASE_URL}/v1/media/create-upload-url").mock(
        return_value=httpx.Response(200, json={"upload_url": "https://storage.example/u", "media_url": "https://cdn/x.mp4"})
    )
    respx.put("https://storage.example/u").mock(return_value=httpx.Response(200))
    post_route = respx.post(f"{BASE_URL}/v1/social-posts").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "post_9",
                "status": "processing",
                "social_accounts": [{"id": "spc_1"}],
            },
        )
    )

    async with httpx.AsyncClient() as http_client:
        client = PostForMeClient(http_client, api_key="key123")
        post = await client.publish_clip(clip_path, caption="auto-clip")

    assert post.id == "post_9"
    import json

    sent_body = json.loads(post_route.calls.last.request.content)
    assert sent_body["social_accounts"] == ["spc_1"]
    assert sent_body["media"] == [{"url": "https://cdn/x.mp4"}]


@respx.mock
async def test_publish_clip_uses_explicit_account_ids_without_listing(tmp_path):
    clip_path = tmp_path / "clip.mp4"
    clip_path.write_bytes(b"bytes")

    accounts_route = respx.get(f"{BASE_URL}/v1/social-accounts")
    respx.post(f"{BASE_URL}/v1/media/create-upload-url").mock(
        return_value=httpx.Response(200, json={"upload_url": "https://storage.example/u", "media_url": "https://cdn/x.mp4"})
    )
    respx.put("https://storage.example/u").mock(return_value=httpx.Response(200))
    respx.post(f"{BASE_URL}/v1/social-posts").mock(
        return_value=httpx.Response(200, json={"id": "post_9", "status": "processing", "social_accounts": [{"id": "spc_9"}]})
    )

    async with httpx.AsyncClient() as http_client:
        client = PostForMeClient(http_client, api_key="key123")
        await client.publish_clip(clip_path, caption="auto-clip", social_account_ids=["spc_9"])

    assert not accounts_route.called
