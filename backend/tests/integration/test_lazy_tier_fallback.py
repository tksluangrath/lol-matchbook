"""
Real integration test for GET /advice's lazy-tier miss fallback, implementing
docs/system-design.md's Error Handling section verbatim: "Missing/incomplete
data for a rare champion pair ... -> fall back to a wider rank bracket or a
general champion-archetype blurb rather than showing nothing." Real
persistent pgserver DB, real uvicorn server, real httpx round trips, real
Data Dragon fetch for the archetype-blurb case (not mocked).
"""
import threading
import time

import httpx
import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from app.db_migrate import migrate
from app.models import Advice, BackfillQueue

PATCH = "16.15.1"
PORT = 8124

# A real pair with an eager row precomputed under one rank_bracket only --
# a request at a different rank must fall back to this real content rather
# than 404ing, since every real precomputed row in this system only ever
# exists at rank_bracket="emerald" in production but this test uses an
# arbitrary real bracket name to isolate the fallback logic from that fact.
WIDER_RANK_CHAMP_A, WIDER_RANK_CHAMP_B, WIDER_RANK_ROLE = "WiderRankChamp", "Opponent", "jungle"
WIDER_RANK_SEEDED_BRACKET = "platinum"
WIDER_RANK_REQUESTED_BRACKET = "bronze"  # never seeded -- forces the fallback path

# A real pair with real champion names (so the real Data Dragon fetch
# succeeds) that has never been precomputed at any rank -- forces the
# deepest fallback, the general archetype blurb.
ARCHETYPE_CHAMP_A, ARCHETYPE_CHAMP_B, ARCHETYPE_ROLE, ARCHETYPE_RANK = "Yasuo", "Zed", "middle", "diamond"


@pytest.fixture(scope="module")
def app_server():
    server, engine = migrate()  # DEFAULT_PGDATA -- the real, persistent local DB
    TestSession = sessionmaker(bind=engine)

    session = TestSession()
    for phase in ("early", "mid", "late"):
        session.execute(
            pg_insert(Advice).values(
                champ_a=WIDER_RANK_CHAMP_A, champ_b=WIDER_RANK_CHAMP_B, role=WIDER_RANK_ROLE,
                rank_bracket=WIDER_RANK_SEEDED_BRACKET, phase=phase,
                text=f"WIDER-RANK-REAL-TEXT-{phase}", fact_source_id=None, patch=PATCH,
                is_abstention=0, tier="eager",
            ).on_conflict_do_nothing(
                index_elements=["champ_a", "champ_b", "role", "rank_bracket", "phase", "patch"]
            )
        )
    session.commit()
    session.close()

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


def _backfill_row_count(app_server, champ_a, champ_b, rank):
    with app_server["engine"].connect() as conn:
        rows = conn.execute(
            select(BackfillQueue).where(
                BackfillQueue.champ_a == champ_a, BackfillQueue.champ_b == champ_b,
                BackfillQueue.rank_bracket == rank,
            )
        ).fetchall()
    return len(rows)


def test_wider_rank_fallback_returns_real_precomputed_content_not_404(app_server):
    before = _backfill_row_count(app_server, WIDER_RANK_CHAMP_A, WIDER_RANK_CHAMP_B, WIDER_RANK_REQUESTED_BRACKET)

    resp = httpx.get(
        f"{app_server['base_url']}/advice",
        params={
            "champ_a": WIDER_RANK_CHAMP_A, "champ_b": WIDER_RANK_CHAMP_B,
            "role": WIDER_RANK_ROLE, "rank": WIDER_RANK_REQUESTED_BRACKET,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "wider_rank_fallback"
    assert body["early"] == "WIDER-RANK-REAL-TEXT-early"
    assert body["mid"] == "WIDER-RANK-REAL-TEXT-mid"
    assert body["late"] == "WIDER-RANK-REAL-TEXT-late"

    after = _backfill_row_count(app_server, WIDER_RANK_CHAMP_A, WIDER_RANK_CHAMP_B, WIDER_RANK_REQUESTED_BRACKET)
    assert after == before + 1, "exactly one real backfill_queue row must be written per miss"


def test_archetype_blurb_fallback_returns_real_champion_blurbs_not_404(app_server):
    before = _backfill_row_count(app_server, ARCHETYPE_CHAMP_A, ARCHETYPE_CHAMP_B, ARCHETYPE_RANK)

    resp = httpx.get(
        f"{app_server['base_url']}/advice",
        params={
            "champ_a": ARCHETYPE_CHAMP_A, "champ_b": ARCHETYPE_CHAMP_B,
            "role": ARCHETYPE_ROLE, "rank": ARCHETYPE_RANK,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "archetype_fallback"
    assert body["source"] == "archetype_fallback"
    # Real Data Dragon lore blurbs -- not empty, not matchup-specific advice.
    assert len(body["champ_a_blurb"]) > 20
    assert len(body["champ_b_blurb"]) > 20

    after = _backfill_row_count(app_server, ARCHETYPE_CHAMP_A, ARCHETYPE_CHAMP_B, ARCHETYPE_RANK)
    assert after == before + 1, "exactly one real backfill_queue row must be written per miss"


def test_wider_rank_fallback_latency_with_backfill_write_under_200ms(app_server):
    # Uses a fresh rank string each call so the backfill write always
    # actually happens (not an idempotency no-op) -- isolates the write's
    # real cost inside the measured path every time, matching the required
    # "with the queue write included" measurement.
    latencies_ms = []
    for i in range(10):
        params = {
            "champ_a": WIDER_RANK_CHAMP_A, "champ_b": WIDER_RANK_CHAMP_B,
            "role": WIDER_RANK_ROLE, "rank": f"latency-test-rank-{i}",
        }
        t0 = time.perf_counter()
        resp = httpx.get(f"{app_server['base_url']}/advice", params=params)
        latencies_ms.append((time.perf_counter() - t0) * 1000)
        assert resp.status_code == 200
        assert resp.json()["source"] == "wider_rank_fallback"

    latencies_ms.sort()
    median_ms = latencies_ms[len(latencies_ms) // 2]
    print(f"WIDER_RANK_FALLBACK_LATENCY_MS median={median_ms:.2f} all={[round(l, 2) for l in latencies_ms]}")
    assert median_ms < 200, f"median latency {median_ms:.2f}ms exceeds the 200ms target"
