"""
POST /ask (WebSocket) -- the live follow-up path. Retrieval + the CPU-quantized
model from app/llm/serve.py. This is the slower path; a few seconds of latency
is acceptable here, unlike /advice. See docs/system-design.md section 2 and
docs/build-plan.md Phase 4.

Request/response shape confirmed and reconciled against two real sources
that disagreed: system-design.md's documented contract omits `role`
(`{question, champ_a, champ_b, rank}`), but build_ask_context() (app/llm/
context.py) requires it -- role is a first-class identity column
(app/models.py) since a champion can be viable in more than one lane
(phase0-role-scoping.md). This is the exact same multi-lane ambiguity gap
already fixed for GET /advice (commit 06c5b41, "Require role on GET
/advice"). Treated consistently here rather than reintroducing the gap:
`role` is required in the request.
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import app.db as db
from app.llm.context import build_ask_context
from app.llm.serve import stream_tokens

router = APIRouter()

REQUIRED_FIELDS = ("question", "champ_a", "champ_b", "role", "rank")


@router.websocket("/ask")
async def ask(websocket: WebSocket):
    await websocket.accept()
    try:
        payload = await websocket.receive_json()
    except (WebSocketDisconnect, ValueError):
        return

    missing = [f for f in REQUIRED_FIELDS if not payload.get(f)]
    if missing:
        await websocket.send_json({"type": "error", "message": f"missing required field(s): {', '.join(missing)}"})
        await websocket.close()
        return

    session = db.SessionLocal()
    try:
        try:
            # Retrieval (real DB query + real Data Dragon fetches) is
            # blocking I/O -- off the event loop, same reasoning as
            # stream_tokens for the generation itself.
            prompt = await asyncio.to_thread(
                build_ask_context,
                session,
                payload["champ_a"],
                payload["champ_b"],
                payload["role"],
                payload["rank"],
                payload["question"],
            )
        except Exception as exc:
            await websocket.send_json({"type": "error", "message": f"could not build context: {exc}"})
            await websocket.close()
            return

        try:
            async for chunk in stream_tokens(prompt):
                await websocket.send_json({"type": "chunk", "text": chunk})
        except WebSocketDisconnect:
            return
        except Exception as exc:
            await websocket.send_json({"type": "error", "message": f"generation failed: {exc}"})
            await websocket.close()
            return

        await websocket.send_json({"type": "done"})
        await websocket.close()
    finally:
        session.close()
