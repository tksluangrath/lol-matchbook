"""
CPU-quantized generation for the live /ask follow-up path, via
llama-cpp-python against the real GGUF build already proven in
docs/decisions/phase4-gguf-conversion.md (Q4_K_M, n_gpu_layers=0,
CPU-only confirmed there by direct process/GPU monitoring, not assumed
from this module reusing the same flag).

Deliberately a different tool from the vLLM-based precompute path (see
docs/architecture-evaluation.md's critical finding on why): precompute is
an offline batch job free to use the GPU, /ask runs live while the game
itself needs the GPU, so it must never touch it.
"""
from __future__ import annotations

import asyncio
import functools
from pathlib import Path
from typing import AsyncIterator, Iterator

from app.finetune.prompts import SYSTEM_PROMPT

GGUF_PATH = (
    Path(__file__).resolve().parents[1] / "finetune" / "artifacts"
    / "gguf-qualitative-v2" / "merged-qualitative-v2-Q4_K_M.gguf"
)
MAX_TOKENS = 400


@functools.lru_cache(maxsize=1)
def _load_model():
    """Loads the real quantized model once per process (~2-3s, per the
    conversion doc) and caches it -- every /ask request after the first
    reuses this instance rather than reloading per request."""
    from llama_cpp import Llama

    if not GGUF_PATH.exists():
        raise FileNotFoundError(
            f"No GGUF model at {GGUF_PATH} -- run the phase4 conversion first "
            "(see docs/decisions/phase4-gguf-conversion.md)."
        )
    return Llama(model_path=str(GGUF_PATH), n_ctx=4096, n_threads=8, n_gpu_layers=0, verbose=False)


def _generate_sync(prompt: str) -> Iterator[str]:
    """Real, blocking, CPU-bound generation -- greedy (temperature=0.0),
    matching the deterministic generation this project uses everywhere
    else. Yields each token's incremental text as llama-cpp produces it."""
    llm = _load_model()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    for chunk in llm.create_chat_completion(messages=messages, max_tokens=MAX_TOKENS, temperature=0.0, stream=True):
        delta = chunk["choices"][0]["delta"]
        text = delta.get("content")
        if text:
            yield text


async def stream_tokens(prompt: str) -> AsyncIterator[str]:
    """Bridges the blocking, CPU-bound generator above onto the asyncio
    event loop: runs it in a worker thread and forwards each chunk through
    a queue as it's produced, rather than blocking the loop (and every
    other open connection) until the whole response is ready. ponytail:
    single dedicated thread -- generation is inherently serial on this
    box anyway (one CPU-bound model, real 4-10x throughput variance
    already documented this project), a pool wouldn't parallelize it."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()

    def produce() -> None:
        try:
            for chunk in _generate_sync(prompt):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:  # surfaced to the async side, not swallowed
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, produce)
    while True:
        item = await queue.get()
        if item is None:
            return
        if isinstance(item, Exception):
            raise item
        yield item
