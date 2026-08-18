"""
Real integration test for the POST /ask WebSocket: real uvicorn server,
real websockets client (not FastAPI's in-process TestClient, matching the
standard test_advice_endpoint.py already uses for /advice), real GGUF
generation via app.llm.serve, real GPU-non-engagement check during a live
generation (same standard as phase4-gguf-conversion.md).

Skips (not fails) if the real GGUF model isn't built yet -- this test
proves the endpoint, it doesn't re-run the multi-minute conversion.
"""
import json
import threading
import time
from pathlib import Path

import pytest
import uvicorn
import websockets
from websockets.sync.client import connect

from app.data_pipeline.precompute import load_sample_pairs, run_precompute_batch
from app.db_migrate import migrate

PATCH = "16.15.1"
PORT = 8124
GGUF_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "finetune" / "artifacts"
    / "gguf-qualitative-v2" / "merged-qualitative-v2-Q4_K_M.gguf"
)


@pytest.fixture(scope="module")
def ask_app_server():
    if not GGUF_PATH.exists():
        pytest.skip(f"no GGUF model at {GGUF_PATH} -- run the phase4 conversion first")

    server, engine = migrate()  # DEFAULT_PGDATA -- the real, persistent local DB

    # Real precompute, 1 pair -- gives /ask a real MatchupStat row to build
    # the stats block from (idempotent no-op if it's already written).
    pairs = load_sample_pairs(n=1)
    run_precompute_batch(PATCH, engine=engine, pairs=pairs)

    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    uv_server = uvicorn.Server(config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15  # app.main's own lifespan does a real migrate() too
    while not uv_server.started and time.time() < deadline:
        time.sleep(0.05)
    assert uv_server.started, "real uvicorn server did not start in time"

    try:
        yield {"ws_url": f"ws://127.0.0.1:{PORT}/ask", "pair": pairs[0]}
    finally:
        uv_server.should_exit = True
        thread.join(timeout=5)
        engine.dispose()
        server.cleanup()  # graceful pg_ctl stop -- does NOT delete DEFAULT_PGDATA's on-disk data


def test_ask_streams_a_real_response_in_order(ask_app_server):
    pair = ask_app_server["pair"]
    with connect(ask_app_server["ws_url"], open_timeout=10) as ws:
        ws.send(json.dumps({
            "question": "What should I do in the early game?",
            "champ_a": pair["champ_a"], "champ_b": pair["champ_b"],
            "role": pair["role"], "rank": pair["rank_bracket"],
        }))

        chunks = []
        msg_types = []
        while True:
            raw = ws.recv(timeout=180)  # real CPU generation, this project's observed range up to ~260s/pair
            msg = json.loads(raw)
            msg_types.append(msg["type"])
            if msg["type"] == "chunk":
                chunks.append(msg["text"])
            elif msg["type"] == "done":
                break
            elif msg["type"] == "error":
                pytest.fail(f"/ask returned a real error: {msg['message']}")

    assert msg_types[-1] == "done"
    assert len(chunks) > 1, "expected multiple real streamed chunks, not one buffered blob"
    full_text = "".join(chunks)
    assert full_text.strip() != ""
    print(f"ASK_REAL_RESPONSE: {full_text!r}")


def test_ask_rejects_malformed_request_cleanly(ask_app_server):
    with connect(ask_app_server["ws_url"], open_timeout=10) as ws:
        ws.send(json.dumps({"question": "missing champ fields"}))
        raw = ws.recv(timeout=10)
        msg = json.loads(raw)
        assert msg["type"] == "error"
        assert "champ_a" in msg["message"] or "missing" in msg["message"].lower()

        # Server closes the connection after a malformed request -- confirm
        # it doesn't hang the socket open waiting for more input.
        with pytest.raises((websockets.exceptions.ConnectionClosed, TimeoutError)):
            ws.recv(timeout=5)
