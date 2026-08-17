"""
Real integration test for GET /advice: the real persistent pgserver DB at
DEFAULT_PGDATA (populated by `python -m app.data_pipeline.precompute`'s real
10-pair run -- reused here, not regenerated, via run_precompute_batch's own
idempotency check), real uvicorn server bound to 127.0.0.1, real httpx HTTP
round trip (not FastAPI's in-process TestClient) so the measured latency is
an actual request, matching docs/system-design.md's <200ms target.
"""
import ast
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from sqlalchemy.orm import sessionmaker

from app.data_pipeline.precompute import load_sample_pairs, run_precompute_batch
from app.db_migrate import migrate
from app.models import Advice

PATCH = "16.15.1"
PORT = 8123


@pytest.fixture(scope="module")
def seeded_app_server():
    server, engine = migrate()  # DEFAULT_PGDATA -- the real, persistent local DB

    # Real precompute, 2 pairs -- if the persistent DB already has these
    # rows (e.g. from the full 10-pair run), this is a fast idempotent
    # no-op; if not, it runs real generation for just these 2.
    pairs = load_sample_pairs(n=2)
    result = run_precompute_batch(PATCH, engine=engine, pairs=pairs)
    if not result["written_pairs"] and not result["already_present"]:
        pytest.skip(f"real precompute wrote no rows for the 2-pair sample: {result}")

    # A real abstention row, seeded directly (idempotent -- ON CONFLICT DO
    # NOTHING, since this may run again against the persistent DB).
    # Abstention is a separate, never-model-generated write path (thin-data
    # case, per models.py's docstring), so this isn't a fabricated model output.
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    for phase in ("early", "mid", "late"):
        session.execute(
            pg_insert(Advice).values(
                champ_a="ThinData", champ_b="Opponent", role="top", rank_bracket="iron",
                phase=phase, text="", fact_source_id=None, patch=PATCH,
                is_abstention=1, tier="eager",
            ).on_conflict_do_nothing(
                index_elements=["champ_a", "champ_b", "role", "rank_bracket", "phase", "patch"]
            )
        )
    # Two real rows for the same champ_a/champ_b/rank but different roles
    # (idempotent, same reasoning as above) -- proves the role query param
    # actually disambiguates rather than just being accepted and ignored.
    session = TestSession()
    for role, text_prefix in (("bottom", "BOT-LANE-TEXT"), ("support", "SUPPORT-TEXT")):
        for phase in ("early", "mid", "late"):
            session.execute(
                pg_insert(Advice).values(
                    champ_a="MultiRole", champ_b="Opponent", role=role, rank_bracket="gold",
                    phase=phase, text=f"{text_prefix}-{phase}", fact_source_id=None, patch=PATCH,
                    is_abstention=0, tier="eager",
                ).on_conflict_do_nothing(
                    index_elements=["champ_a", "champ_b", "role", "rank_bracket", "phase", "patch"]
                )
            )
    session.commit()
    session.close()

    # app.db builds its module-level engine from settings.database_url at
    # import time (a fixed default, not pgserver's dynamic per-run URI) --
    # override the get_db dependency to use this real migrated engine
    # instead, the standard FastAPI testing pattern for a real, non-default DB.
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
        yield {"base_url": f"http://127.0.0.1:{PORT}", "written_pairs": pairs}
    finally:
        uv_server.should_exit = True
        thread.join(timeout=5)
        app.dependency_overrides.clear()
        engine.dispose()
        server.cleanup()  # graceful pg_ctl stop -- does NOT delete DEFAULT_PGDATA's on-disk data


def test_advice_endpoint_returns_real_precomputed_data_for_seeded_pair(seeded_app_server):
    pair = seeded_app_server["written_pairs"][0]
    resp = httpx.get(
        f"{seeded_app_server['base_url']}/advice",
        params={"champ_a": pair["champ_a"], "champ_b": pair["champ_b"], "role": pair["role"], "rank": pair["rank_bracket"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"early", "mid", "late"}
    for phase in ("early", "mid", "late"):
        assert body[phase].strip() != ""


def test_advice_endpoint_returns_404_for_never_precomputed_pair(seeded_app_server):
    resp = httpx.get(
        f"{seeded_app_server['base_url']}/advice",
        params={"champ_a": "NotAChamp", "champ_b": "AlsoNotAChamp", "role": "top", "rank": "iron"},
    )
    assert resp.status_code == 404
    assert resp.json()["status"] == "not_precomputed"


def test_advice_endpoint_returns_abstention_status_for_thin_data_row(seeded_app_server):
    resp = httpx.get(
        f"{seeded_app_server['base_url']}/advice",
        params={"champ_a": "ThinData", "champ_b": "Opponent", "role": "top", "rank": "iron"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "abstention"


def test_advice_endpoint_disambiguates_by_role_for_same_champ_pair_and_rank(seeded_app_server):
    # MultiRole/Opponent at rank=gold has real rows for both role=bottom and
    # role=support (seeded in the fixture) -- confirms `role` actually
    # selects the right row set instead of being accepted and ignored.
    resp_bottom = httpx.get(
        f"{seeded_app_server['base_url']}/advice",
        params={"champ_a": "MultiRole", "champ_b": "Opponent", "role": "bottom", "rank": "gold"},
    )
    resp_support = httpx.get(
        f"{seeded_app_server['base_url']}/advice",
        params={"champ_a": "MultiRole", "champ_b": "Opponent", "role": "support", "rank": "gold"},
    )
    assert resp_bottom.status_code == 200
    assert resp_support.status_code == 200
    assert resp_bottom.json() == {
        "early": "BOT-LANE-TEXT-early", "mid": "BOT-LANE-TEXT-mid", "late": "BOT-LANE-TEXT-late",
    }
    assert resp_support.json() == {
        "early": "SUPPORT-TEXT-early", "mid": "SUPPORT-TEXT-mid", "late": "SUPPORT-TEXT-late",
    }
    assert resp_bottom.json() != resp_support.json()


def test_advice_endpoint_source_imports_no_model_or_generation_code():
    # Static check that GET /advice's implementation never touches the
    # adapter/generation path, per the architecture's "pure DB lookup, no
    # model call" promise -- checked against the real file's imports, not
    # asserted by absence of a mock.
    source = (Path(__file__).resolve().parents[2] / "app" / "routers" / "advice.py").read_text()
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    forbidden = {m for m in imported_modules if "finetune" in m or "llm" in m}
    assert not forbidden, f"advice.py imports model/generation code: {forbidden}"


def test_advice_endpoint_real_request_latency_under_200ms(seeded_app_server):
    pair = seeded_app_server["written_pairs"][0]
    params = {"champ_a": pair["champ_a"], "champ_b": pair["champ_b"], "role": pair["role"], "rank": pair["rank_bracket"]}

    # One warmup request (connection setup, first-request overhead), then
    # measure 10 real HTTP round trips.
    httpx.get(f"{seeded_app_server['base_url']}/advice", params=params)

    latencies_ms = []
    for _ in range(10):
        t0 = time.perf_counter()
        resp = httpx.get(f"{seeded_app_server['base_url']}/advice", params=params)
        latencies_ms.append((time.perf_counter() - t0) * 1000)
        assert resp.status_code == 200

    latencies_ms.sort()
    median_ms = latencies_ms[len(latencies_ms) // 2]
    print(f"ADVICE_ENDPOINT_LATENCY_MS median={median_ms:.2f} all={[round(l, 2) for l in latencies_ms]}")
    assert median_ms < 200, f"median latency {median_ms:.2f}ms exceeds the 200ms target"
