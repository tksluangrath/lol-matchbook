"""
GET /lcu (WebSocket) -- pushes live champ-select state to the frontend, per
docs/system-design.md's LCU listener component ("pushes the current
pick/ban state to the web UI so champ_a/champ_b/rank populate automatically
instead of manual entry"). Internal to this app, not a Riot-facing
endpoint: it forwards app.lcu.listener.LCUListener's real polling loop
one-to-one, translating None (client not running / no active pick) into an
explicit `{"type": "idle"}` push rather than silence, so the frontend can
distinguish "still waiting to hear anything" from "confirmed nothing to
show right now."

docs/system-design.md's own load estimate assumes "at most one request at
a time (one player, one client)" for this whole app -- one LCUListener per
connection, not a shared singleton, keeps that assumption honest rather
than adding multi-subscriber fan-out this project doesn't need yet.
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.lcu.listener import LCUListener

router = APIRouter()


@router.websocket("/lcu")
async def lcu(websocket: WebSocket):
    await websocket.accept()
    listener = LCUListener()
    try:
        async for state in listener.poll_session():
            if state is None:
                await websocket.send_json({"type": "idle"})
            else:
                await websocket.send_json({"type": "champ_select", **state})
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
