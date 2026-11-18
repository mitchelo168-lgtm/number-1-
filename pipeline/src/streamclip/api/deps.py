from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from streamclip.config import Settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def get_session_factory(request: Request) -> async_sessionmaker:
    return request.app.state.session_factory


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings
