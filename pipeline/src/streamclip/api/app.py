from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from streamclip.api.routes import clips, streamers
from streamclip.api.routes import settings as settings_routes
from streamclip.config import Settings
from streamclip.db import init_db, make_engine, make_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db(app.state.engine)
        yield

    app = FastAPI(title="streamclip", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine = make_engine(settings.database_url)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    clips_dir = Path(settings.clips_dir)
    clips_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media/clips", StaticFiles(directory=clips_dir), name="clips")

    app.include_router(streamers.router)
    app.include_router(clips.router)
    app.include_router(settings_routes.router)

    return app
