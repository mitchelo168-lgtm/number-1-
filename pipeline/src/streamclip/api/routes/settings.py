from fastapi import APIRouter, Depends

from streamclip.api.deps import get_settings_dep
from streamclip.api.schemas import CredentialStatusOut
from streamclip.config import Settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/credential-status", response_model=CredentialStatusOut)
async def credential_status(settings: Settings = Depends(get_settings_dep)):
    return CredentialStatusOut(
        twitch=bool(settings.twitch_client_id and settings.twitch_client_secret),
        youtube=bool(settings.youtube_api_key),
        kick=bool(settings.kick_client_id and settings.kick_client_secret),
        discord=bool(settings.discord_bot_token and settings.discord_review_channel_id),
        post_for_me=bool(settings.post_for_me_api_key),
    )
