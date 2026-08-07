"""
POST /ask (WebSocket) -- the live follow-up path. Retrieval + the CPU-quantized
model from app/llm/serve.py. This is the slower path; a few seconds of latency
is acceptable here, unlike /advice. See docs/build-plan.md Phase 4.
"""
from fastapi import APIRouter, WebSocket

router = APIRouter()


@router.websocket("/ask")
async def ask(websocket: WebSocket):
    """
    TODO(Phase 4): accept {question, champ_a, champ_b, rank}, run retrieval
    (app/retrieval/index.py) for context, stream tokens back from the quantized
    model (app/llm/serve.py) as they're generated.

    TODO: this must never touch the GPU while the game is running -- confirm
    app/llm/serve.py is CPU-bound (llama-cpp-python, not the vLLM batch tool
    used for precompute). See docs/architecture-evaluation.md critical finding
    for why these two are deliberately different tools.
    """
    await websocket.accept()
    raise NotImplementedError
