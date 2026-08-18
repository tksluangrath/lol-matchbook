"""
Create all tables from app.models.Base against a pgserver-managed embedded
Postgres instance, using the start/stop method validated in
docs/decisions/phase0-pgserver-spike.md: `pgserver.get_server(pgdata,
cleanup_mode="stop")` to start (graceful `pg_ctl stop -w` on cleanup), and a
fresh process per "restart" rather than trusting an in-process cache -- see
that doc's note on `get_server()` caching a handle without re-checking
liveness. This module only starts/stops the same way the spike validated;
it doesn't add its own retry/caching logic on top.

pgserver ships wheels only for Python 3.9-3.12 (no 3.13 wheel/sdist as of
this writing, per the spike doc's "Environment note") -- run this under a
<=3.12 interpreter.
"""
from __future__ import annotations

import os

import pgserver
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.models import Base

# ponytail: repo-relative default so `python -m app.db_migrate` works out of
# the box; override via the pgdata= argument (e.g. a temp dir in tests), or
# the PGDATA env var (set by Dockerfile to /app/.pgdata -- the repo-relative
# "../.." path resolves outside /app inside the container, which the
# non-root app user can't write to; real PermissionError caught by CI).
DEFAULT_PGDATA = os.environ.get("PGDATA") or os.path.join(
    os.path.dirname(__file__), "..", "..", ".pgdata"
)


def start_pgserver(pgdata: str) -> "pgserver.PostgresServer":
    """Start (or attach to) the embedded Postgres instance at `pgdata`,
    per the validated method in docs/decisions/phase0-pgserver-spike.md."""
    os.makedirs(pgdata, exist_ok=True)
    return pgserver.get_server(pgdata, cleanup_mode="stop")


def migrate(pgdata: str = DEFAULT_PGDATA) -> tuple["pgserver.PostgresServer", Engine]:
    """Start pgserver at `pgdata` and create every table declared on
    app.models.Base (idempotent -- create_all only adds missing tables, so
    re-running against an existing pgdata dir is safe).

    Returns (server, engine); the caller owns calling `server.cleanup()`
    (and `engine.dispose()`) when done, matching the spike's graceful-stop
    method rather than this module silently tearing the server down.
    """
    srv = start_pgserver(pgdata)
    engine = create_engine(srv.get_uri())
    Base.metadata.create_all(engine)
    return srv, engine


if __name__ == "__main__":
    server, eng = migrate()
    try:
        print(f"Migrated tables at {server.get_uri()}")
        print("Tables:", sorted(Base.metadata.tables.keys()))
    finally:
        eng.dispose()
        server.cleanup()
