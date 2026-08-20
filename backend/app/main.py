"""
FastAPI entrypoint. See docs/system-design.md section 2 (API contracts) and
docs/build-plan.md Phase 4.

Run locally with: uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

import app.db as db
from app.config import settings
from app.db_migrate import migrate
from app.routers import advice, ask, lcu, refresh


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Starts pgserver in-process and points app.db's engine/SessionLocal at
    # it -- the decision app/db.py's module docstring used to leave open.
    # get_db() re-reads SessionLocal from app.db's namespace on every call,
    # so reassigning it here (after routers already imported get_db) still
    # takes effect for every request.
    server, engine = migrate()
    db.engine = engine
    db.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield
    engine.dispose()
    server.cleanup()


app = FastAPI(title="lol-matchbook backend", lifespan=lifespan)

# Dev-scoped Vite origins plus the real deployed Render Static Site.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://lol-matchup-copilot.onrender.com",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(advice.router)
app.include_router(ask.router)
app.include_router(refresh.router)
app.include_router(lcu.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    # bind to localhost only -- never 0.0.0.0, see docs/testing-strategy.md
    uvicorn.run(app, host=settings.backend_host, port=settings.backend_port)
