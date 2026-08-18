---
noteId: "2a38c83091f711f1a408bdbca18563c4"
tags: []

---

# lol-matchup-copilot

A local, rank-aware League of Legends matchup assistant. Detects your champ-select pick/ban state automatically and gives instant early/mid/late-game matchup advice through a chat-style interface, backed by a small fine-tuned LLM plus a retrieval layer that stays current with the patch cycle without retraining.

This is an unofficial fan-made project. It is not endorsed by or affiliated with Riot Games.

## Why this exists

Champ select gives you roughly 30 seconds to lock in a pick. This app auto-detects your matchup via the League client's local API and answers from a precomputed lookup table instead of generating live, so the answer is there before the clock matters — and it never competes with the game for GPU while you're playing. The full reasoning for every decision below lives in `docs/`.

## Read this first

Start with [`docs/build-plan.md`](./docs/build-plan.md) — it's the phased build order and the one doc meant to be worked through top to bottom. The rest are reference:

- [`docs/adr-001-architecture.md`](./docs/adr-001-architecture.md) — the core architecture decision (hybrid fine-tune + RAG, precompute over live generation) and why.
- [`docs/system-design.md`](./docs/system-design.md) — components, data flow, storage, APIs, and the testing & evaluation plan for the model itself.
- [`docs/tech-stack.md`](./docs/tech-stack.md) — every stack choice (Tauri, FastAPI, Postgres/pgvector via `pgserver`, `llama-cpp-python`, local embeddings) with pros/cons.
- [`docs/testing-strategy.md`](./docs/testing-strategy.md) — code-level test plan (unit/integration/E2E) by component.
- [`docs/architecture-evaluation.md`](./docs/architecture-evaluation.md) — a critical review of the above, including one open finding (precompute throughput was never sized) that Phase 0 of the build plan exists to resolve.
- [`frontend/README.md`](./frontend/README.md) — the chat UI's palette/state-to-color mapping and which two interfaces (`POST /ask`, LCU auto-detection) are currently mocked and where to swap them in.

## Repo layout

```
backend/    FastAPI app: API routes, LCU listener, data pipeline, retrieval, LLM fine-tune + serving
frontend/   React + Vite chat UI
desktop/    Tauri shell (wraps backend as a sidecar, frontend as the webview)
docs/       Planning docs (read these before touching code)
```

## Status

Pre-build. See `docs/build-plan.md` Phase 0 for what needs deciding before any of the scaffolding below is filled in.

## Setup

Not yet runnable end to end — this is scaffolding, not a working app. Once Phase 0-1 of the build plan are done:

```
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in your Riot API key

# frontend
cd ../frontend
npm install
npm run dev
```

Tauri setup (Phase 6) isn't scaffolded yet — see `desktop/README.md`.

## License

Code in this repo: Apache 2.0 (see `LICENSE`). This project uses Riot Games data under Riot's Developer API terms — it is not licensed, sponsored, or endorsed by Riot Games. League of Legends and Riot Games are trademarks of Riot Games, Inc.
