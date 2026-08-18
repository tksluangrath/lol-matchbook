---
noteId: "phase4askendpoint0001"
tags: []

---

# Phase 4: The `/ask` Endpoint — Real WebSocket, Real GGUF Generation, Real CPU-Only Confirmation

**Status: DONE.** Real WebSocket round trip against a real running server,
real streamed multi-chunk response, real CPU-only confirmation during live
generation, malformed-request handling tested.

## Contract reconciled: `role` is required, despite the doc omitting it

`docs/system-design.md` documents `POST /ask` as
`{question, champ_a, champ_b, rank} -> streamed text` — no `role`. But
`build_ask_context()` (`app/llm/context.py`, built earlier this session)
requires `role` to look up the real `MatchupStat` row, because role is a
first-class identity column (`app/models.py`): a champion can be viable in
more than one lane (`docs/decisions/phase0-role-scoping.md`).

This is the exact same multi-lane ambiguity gap already found and fixed for
`GET /advice` (commit `06c5b41`, "Require role on GET /advice"). Rather than
reintroduce that gap here because the doc happens to omit it, `role` is
required in the real request payload, consistent with `/advice`.

## Real files

- `backend/app/llm/serve.py` (new) — the CPU-quantized generation wrapper.
  Loads the real GGUF model built in `docs/decisions/phase4-gguf-conversion.md`
  (`Q4_K_M`, `n_gpu_layers=0`), cached per-process via `functools.lru_cache`.
  Generation itself is real, blocking, CPU-bound work — bridged onto the
  asyncio event loop via a worker thread + queue (`stream_tokens()`), so one
  slow `/ask` request doesn't block every other open connection.
- `backend/app/routers/ask.py` (implemented, was a stub) — accepts
  `{question, champ_a, champ_b, role, rank}` over the WebSocket, builds
  context via `build_ask_context()` (off the event loop, since it does real
  blocking DB + Data Dragon HTTP calls), streams `{"type": "chunk", "text":
  ...}` messages as they're generated, then `{"type": "done"}`. A malformed
  request (missing required fields) gets `{"type": "error", "message": ...}`
  followed by a clean close — never left to hang or crash the connection.
- `backend/tests/integration/test_ask_endpoint.py` (new) — real uvicorn
  server, real `websockets.sync.client` connection (not FastAPI's in-process
  `TestClient`, matching the standard `test_advice_endpoint.py` already
  uses), real GGUF generation, real malformed-request rejection.

## Real bug found and fixed: `GGUF_PATH` off-by-one

`serve.py`'s first version computed `GGUF_PATH` via
`Path(__file__).resolve().parents[2]`, which resolves from
`app/llm/serve.py` to `backend/`, then appended `finetune/artifacts/...` —
missing the `app/` path segment entirely
(`backend/finetune/artifacts/...` instead of
`backend/app/finetune/artifacts/...`). Caught immediately by the real
integration test failing with a real `FileNotFoundError`, not silently
producing a wrong result. Fixed to `parents[1]`, verified the corrected
path resolves and `.exists()` is `True` before rerunning.

## Real environment gap found and fixed: `llama-cpp-python` missing from the pgserver-compatible env

`llama-cpp-python` was only installed under the 3.13.7 ML-stack environment
(from the GGUF conversion work) — not under the 3.12.5 environment
`pgserver` requires. Since `/ask`'s real integration test needs *both* (a
real DB via pgserver and real generation via llama-cpp-python) in the same
process, this is the same cross-environment split this project has hit
before (peft/bitsandbytes needed installing into 3.12 for `precompute.py`
for the same reason). Fixed the same way: `CMAKE_ARGS="-DGGML_METAL=OFF"
pip install llama-cpp-python` into the 3.12.5 environment. Not committed as
a requirements change beyond what's already in `requirements-serving.txt`
(it was already listed there for the Docker image; this was a local-dev-env
gap, not a missing dependency declaration).

## Real streamed response (Aatrox/Kayle, top, emerald)

Real question: "What should I do in the early game?" Real response,
streamed as multiple real chunks (not one buffered blob — the test asserts
`len(chunks) > 1`):

> In the early game, Aatrox and Kayle have similar levels of presence in
> the top lane, but Kayle's ability to heal allies and grant Move Speed
> with Celestial Blessing gives her an edge in sustain and team
> coordination. Aatrox's Deathbringer Stance provides an advantage in
> damaging and healing himself, but he lacks crowd control early on.
>
> Aatrox should focus on engaging with the first enemy unit he can hit
> with The Darkin Blade or Umbral Dash to gain experience and pressure...
> *(full real response in the test's own stdout capture)*

## Real CPU-only confirmation during a live `/ask` request

Not assumed from `n_gpu_layers=0` alone — measured directly during an
actual generation, the same standard `phase4-gguf-conversion.md` already
used:

```
sample 1: Device Utilization % = 0   backend process CPU = 48.0%   (context build / model warm-up)
sample 2: Device Utilization % = 0   backend process CPU = 896.0%  (active generation)
sample 3: Device Utilization % = 0   backend process CPU = 859.8%  (active generation)
sample 4: Device Utilization % = 0   backend process CPU = 88.8%   (winding down)
sample 5: Device Utilization % = 0   backend process CPU = 97.7%   (idle after DONE)
```

Real GPU utilization stayed at 0% throughout while the backend process
drove 8-9 CPU cores — confirms `/ask` never touches the GPU, the hard
architectural constraint this project's docs specify (must not contend
with the game's own GPU usage).

## Real regression check

Ran the existing HTTP integration suite (`test_advice_endpoint.py`,
`test_lazy_tier_fallback.py`) after adding `/ask`'s WebSocket route, since
both spin up a real `app.main.app` via `uvicorn.Server` and that app's
`lifespan` handler (added in a prior session, `a0d4905`) now calls
`migrate()` on startup — on top of those tests' own fixtures *also* calling
`migrate()` before starting the server. Confirmed this double-`migrate()`
combination is safe (pgserver's `get_server()` attaches to the already-running
instance rather than erroring): all 9 existing HTTP tests still pass.

## Next step

Not done in this slice: swapping the frontend's `mockAskClient` (behind the
already-established `AskClient` interface in `frontend/src/api/ask.mock.ts`)
for a real WebSocket client. The wire shape (`{type: "chunk"|"done"|"error",
...}`) is designed to be a small, contained swap — one new file
(`frontend/src/api/ask.ts`), one import change in `App.tsx`, per the
interface's own documented swap-in contract.
