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

# Decided: pgserver starts in-process, via app.main's lifespan handler
# (app.db_migrate.migrate()), which reassigns `engine`/`SessionLocal` below
# to the real pgserver URI before the app accepts requests. This module-level
# engine is just a placeholder so `from app.db import get_db` doesn't fail
# at import time -- get_db() re-reads SessionLocal from this module's
# namespace on every call, so the lifespan's reassignment takes effect.
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
