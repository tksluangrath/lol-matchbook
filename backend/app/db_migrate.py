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
import sys

import pgserver
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.models import Base


def _default_pgdata() -> str:
    # A PyInstaller onefile bundle (Phase 6's packaged desktop app) extracts
    # to a fresh, randomly-named temp dir on every single launch --
    # __file__-relative resolution would then put pgdata inside that
    # ephemeral tree too, so the app's data would vanish on every restart
    # (worse, macOS/Windows periodically clear their temp dirs outright).
    # Confirmed for real during Phase 6's fresh-install smoke test: the
    # frozen binary's Postgres process was found running with
    # `-D $TMPDIR/.pgdata`, not a stable location.
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            # Real, separate gap found and left as a known limitation
            # (untested here -- no Windows access this session): a
            # username with a space (e.g. "C:\Users\John Doe\...") hits
            # the same pgserver space-splitting bug as the one fixed
            # below for macOS. %APPDATA% isn't swappable the way macOS's
            # base dir choice was -- would need a real Windows fix (e.g.
            # a short-path/8.3 conversion) verified on that platform.
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
            return os.path.join(base, "lol-matchbook", "pgdata")
        # Not `~/Library/Application Support` (the normal macOS
        # convention) -- confirmed for real during this session's
        # fresh-install smoke test that pgserver's socket-dir handling
        # breaks on that path's space: it embeds the dir in a
        # `pg_ctl -o "-k <dir>"` string that gets re-split on whitespace,
        # and only swaps to a fallback directory when the path is too
        # long, never when it contains a space. Real error observed:
        # `postgres: invalid argument: "Support/lol-matchbook/pgdata"`.
        # A home dotdir has no such space on macOS or Linux.
        return os.path.join(os.path.expanduser("~"), ".lol-matchbook", "pgdata")
    # ponytail: repo-relative default so `python -m app.db_migrate` works
    # out of the box in source form (dev, tests, Docker).
    return os.path.join(os.path.dirname(__file__), "..", "..", ".pgdata")


# Override via the pgdata= argument (e.g. a temp dir in tests), or the
# PGDATA env var (set by Dockerfile to /app/.pgdata -- the repo-relative
# "../.." path resolves outside /app inside the container, which the
# non-root app user can't write to; real PermissionError caught by CI).
DEFAULT_PGDATA = os.environ.get("PGDATA") or _default_pgdata()


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
