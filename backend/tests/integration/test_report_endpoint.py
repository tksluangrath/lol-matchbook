"""
Real integration test for POST /report: real uvicorn server, real httpx
round trip, real persistent-DB-shaped engine (a fresh tempdir pgdata here,
not the shared dev DB -- report rows are trivial writes with no
idempotency/precompute concerns worth isolating against). Same
dependency_overrides pattern as test_lazy_tier_fallback.py.
"""
import tempfile
import threading
import time

import httpx
import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db_migrate import migrate
from app.models import Report

PORT = 8125


@pytest.fixture(scope="module")
def app_server():
    pgdata = tempfile.mkdtemp(prefix="report_endpoint_test_")
    server, engine = migrate(pgdata=pgdata)
    TestSession = sessionmaker(bind=engine)

    from app.db import get_db
    from app.main import app

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    uv_server = uvicorn.Server(config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not uv_server.started and time.time() < deadline:
        time.sleep(0.05)
    assert uv_server.started, "real uvicorn server did not start in time"

    try:
        yield {"base_url": f"http://127.0.0.1:{PORT}", "engine": engine, "TestSession": TestSession}
    finally:
        uv_server.should_exit = True
        thread.join(timeout=5)
        app.dependency_overrides.clear()
        engine.dispose()
        server.cleanup()


def _report_count(app_server):
    with app_server["engine"].connect() as conn:
        return len(conn.execute(select(Report)).fetchall())


def test_matchup_mistake_report_with_champ_select_context_is_written(app_server):
    before = _report_count(app_server)
    resp = httpx.post(
        f"{app_server['base_url']}/report",
        json={
            "category": "matchup_mistake",
            "message": "Says Milio has no early advantage but this feels off for Aatrox top.",
            "champ_a": "Aatrox", "champ_b": "Kayle", "role": "top", "rank": "emerald",
        },
        timeout=10,
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}
    assert _report_count(app_server) == before + 1

    with app_server["TestSession"]() as session:
        row = session.execute(
            select(Report).where(Report.champ_a == "Aatrox", Report.champ_b == "Kayle")
        ).scalar_one()
        assert row.category == "matchup_mistake"
        assert row.role == "top"
        assert row.rank_bracket == "emerald"


def test_general_bug_report_with_no_champ_select_context_is_written(app_server):
    before = _report_count(app_server)
    resp = httpx.post(
        f"{app_server['base_url']}/report",
        json={"category": "bug", "message": "The rank dropdown reset after I sent a message."},
        timeout=10,
    )
    assert resp.status_code == 200
    assert _report_count(app_server) == before + 1

    with app_server["TestSession"]() as session:
        row = session.execute(
            select(Report).where(Report.message.like("%rank dropdown%"))
        ).scalar_one()
        assert row.champ_a is None
        assert row.champ_b is None


def test_invalid_category_is_rejected_not_silently_written(app_server):
    before = _report_count(app_server)
    resp = httpx.post(
        f"{app_server['base_url']}/report",
        json={"category": "not_a_real_category", "message": "x"},
        timeout=10,
    )
    assert resp.status_code == 422
    assert _report_count(app_server) == before
