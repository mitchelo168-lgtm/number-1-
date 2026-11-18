import pytest_asyncio

from streamclip.db import init_db, make_engine, make_session_factory


@pytest_asyncio.fixture
async def engine():
    eng = make_engine("sqlite+aiosqlite://")
    await init_db(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return make_session_factory(engine)


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session
