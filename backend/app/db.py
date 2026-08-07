"""
Postgres + pgvector via pgserver (embedded, pip-installable Postgres).

Phase 0 TODO: this is the pgserver spike from docs/build-plan.md -- validate
start/stop/restart reliability before anything else depends on this module.
See docs/tech-stack.md #4 for why pgserver was chosen over a system-installed
Postgres service (keeps this an installable app with no separate DB install step).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# TODO(Phase 1): decide whether pgserver is started here (in-process) or by the
# Tauri sidecar wrapper before the backend launches. Either way, this module
# should not assume Postgres is already running -- handle connection retry.
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
