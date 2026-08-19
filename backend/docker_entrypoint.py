"""
Container entrypoint for the dev/CI Docker image (see
docs/decisions/phase-docker-dev-ci-setup.md). NOT part of the product's real
deployment path -- the shipped app is a Tauri + PyInstaller sidecar
(docs/build-plan.md Phase 6), which starts pgserver its own way. This script
only exists so `docker compose up` gives a working local backend+DB.

Starts pgserver embedded in this same container/process using the exact
start_pgserver() method validated in docs/decisions/phase0-pgserver-spike.md
(app/db_migrate.py), writing to PGDATA (a mounted volume for persistence
across container restarts -- see docs/tech-stack.md #4 on why pgserver was
chosen: no separate Postgres service). Then points the app at the real
running server via DATABASE_URL before importing app.main, and runs uvicorn
in this same process so pgserver's managed subprocess stays alive for the
container's lifetime.
"""
import os
import subprocess

from app.db_migrate import start_pgserver

PGDATA = os.environ.get("PGDATA", "/app/.pgdata")

server = start_pgserver(PGDATA)
os.environ["DATABASE_URL"] = server.get_uri()

from app.models import Base  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

engine = create_engine(server.get_uri())
Base.metadata.create_all(engine)

# Seed real precomputed data on a fresh DB -- there's no persistent disk on
# a free-tier host, so PGDATA (and everything create_all just made) starts
# empty on every container start there. Guarded by a real row count, not a
# marker file, so this is safe to run every time regardless of host: a
# populated DB (a real disk that did persist, or a restart of the same
# container) is left alone.
SEED_DATA_PATH = os.path.join(os.path.dirname(__file__), "app", "data_pipeline", "seed_data.sql")
with engine.connect() as conn:
    advice_count = conn.execute(text("SELECT count(*) FROM advice")).scalar()
if advice_count == 0 and os.path.exists(SEED_DATA_PATH):
    import pgserver

    psql = os.path.join(os.path.dirname(pgserver.__file__), "pginstall", "bin", "psql")
    subprocess.run([psql, server.get_uri(), "-f", SEED_DATA_PATH], check=True)

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402 -- import after DATABASE_URL is set, so app.config picks it up

# ponytail: 0.0.0.0 here (not settings.backend_host's 127.0.0.1) so the port
# mapping in docker-compose.yml can reach it from the host -- this is a
# container-networking necessity for dev/CI, not a change to the real app's
# localhost-only bind policy (docs/testing-strategy.md security notes),
# which still applies to the actual Tauri-packaged app.
uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("BACKEND_PORT", 8000)))
