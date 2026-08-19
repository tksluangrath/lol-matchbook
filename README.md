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

`docs/decisions/*.md` is the real build history — each phase's diagnostics, real measurements, and the reasoning behind every architecture call, written as-they-happened and never edited after the fact (a later correction gets a new doc or an "UPDATE" section, not a rewrite). It's the closest thing to a build plan this repo has publicly. `docs/build-plan.md`, `docs/adr-001-architecture.md`, `docs/system-design.md`, `docs/tech-stack.md`, `docs/testing-strategy.md`, and `docs/architecture-evaluation.md` are the original planning docs referenced throughout those decisions -- they exist locally but are gitignored (internal planning docs, not part of the public repo), so a fresh clone won't have them.

- [`frontend/README.md`](./frontend/README.md) — the chat UI's palette/state-to-color mapping, what's real vs. still mocked, and current test coverage.

## Repo layout

```
backend/    FastAPI app: /advice, /ask (WebSocket), /refresh routes; LCU listener; data pipeline
            (Riot match aggregation, precompute); retrieval; LLM fine-tune + GGUF serving
frontend/   React + Vite chat UI -- slash commands (/advice, /ask, /help), rank/role dropdowns,
            champ-select auto-detect (still mocked, see frontend/README.md)
desktop/    Tauri shell (wraps backend as a sidecar, frontend as the webview) -- not started yet
docs/       docs/decisions/ (public build history) + gitignored internal planning docs
```

## Status

Backend and frontend are both real and running: a tiered precompute pipeline (eager-tier DB
lookups plus a lazy wider-rank/archetype fallback, `docs/decisions/tiered-fallback-design.md`)
backs `/advice`, and a fine-tuned adapter serves live follow-up questions through `/ask`. Desktop
packaging (Tauri, the last build phase) hasn't started -- today this runs as a local dev server
pair, not a packaged app.

## Setup

```
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in your Riot API key
uvicorn app.main:app --reload

# frontend
cd ../frontend
npm install
npm run dev
```

Or `docker compose up` from the repo root for the backend alone (dev/CI convenience, not the
product's eventual packaging path -- see `docs/decisions/phase-docker-dev-ci-setup.md`).

Desktop packaging (Tauri) hasn't been scaffolded yet -- no `desktop/README.md` exists.

## License

Code in this repo: Apache 2.0 (see `LICENSE`). This project uses Riot Games data under Riot's Developer API terms — it is not licensed, sponsored, or endorsed by Riot Games. League of Legends and Riot Games are trademarks of Riot Games, Inc.
