"""Thin discord.py wiring around `DiscordReviewBot`.

Deliberately not unit tested here — exercising it for real needs a live
gateway connection and a real bot token. All the actual decision logic
(updating review status, invoking the publish callback) lives in
`DiscordReviewBot`, which the test suite covers directly; `parse_custom_id`
below is the one pure piece of logic in this module and is tested.
"""

from collections.abc import Awaitable, Callable

import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import async_sessionmaker

from streamclip.discord_bot.review_bot import DiscordReviewBot, ReviewMessage
from streamclip.models import Clip

APPROVE_PREFIX = "streamclip:approve:"
REJECT_PREFIX = "streamclip:reject:"


def parse_custom_id(custom_id: str) -> tuple[str, int] | None:
    for prefix, action in ((APPROVE_PREFIX, "approve"), (REJECT_PREFIX, "reject")):
        if custom_id.startswith(prefix):
            try:
                return action, int(custom_id[len(prefix):])
            except ValueError:
                return None
    return None


class ReviewView(discord.ui.View):
    def __init__(self, clip_id: int):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(label="Approve", style=discord.ButtonStyle.success, custom_id=f"{APPROVE_PREFIX}{clip_id}")
        )
        self.add_item(
            discord.ui.Button(label="Reject", style=discord.ButtonStyle.danger, custom_id=f"{REJECT_PREFIX}{clip_id}")
        )


def build_bot(
    session_factory: async_sessionmaker,
    review_channel_id: int,
    on_approved: Callable[[Clip], Awaitable[None]] | None = None,
) -> tuple[commands.Bot, DiscordReviewBot]:
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

    async def send(message: ReviewMessage) -> None:
        channel = bot.get_channel(message.channel_id) or await bot.fetch_channel(message.channel_id)
        file = discord.File(message.file_path) if message.file_path else None
        view = ReviewView(message.clip_id) if message.clip_id is not None else None
        await channel.send(content=message.content, file=file, view=view)

    review_bot = DiscordReviewBot(session_factory, send, review_channel_id, on_approved)

    @bot.event
    async def on_interaction(interaction: discord.Interaction) -> None:
        custom_id = (interaction.data or {}).get("custom_id", "")
        parsed = parse_custom_id(custom_id)
        if parsed is None:
            return
        action, clip_id = parsed
        clip = await review_bot.handle_review_decision(clip_id, approved=(action == "approve"))
        await interaction.response.send_message(f"Clip {clip_id} marked {clip.review_status.value}.", ephemeral=True)

    return bot, review_bot
