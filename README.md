# LoL Matchbook

A local, rank-aware League of Legends matchup assistant. Detects your champ-select pick/ban state automatically and gives instant early/mid/late-game matchup advice through a chat-style interface, backed by a small fine-tuned LLM plus a retrieval layer that stays current with the patch cycle without retraining.

This is an unofficial fan-made project. It is not endorsed by or affiliated with Riot Games.

## Why this exists

Champ select gives you roughly 30 seconds to lock in a pick. This app auto-detects your matchup via the League client's local API and answers from a precomputed lookup table instead of generating live, so the answer is there before the clock matters — and it never competes with the game for GPU while you're playing. The full reasoning for every decision below lives in `docs/`.

## Read this first

`docs/build-plan.md`, `docs/adr-001-architecture.md`, `docs/system-design.md`, `docs/tech-stack.md`, `docs/testing-strategy.md`, and `docs/architecture-evaluation.md` are the original planning docs -- they exist locally but are gitignored (internal planning docs, not part of the public repo), so a fresh clone won't have them.

- [`frontend/README.md`](./frontend/README.md) — the chat UI's palette/state-to-color mapping, what's real vs. still mocked, and current test coverage.

## Repo layout

```
backend/    FastAPI app: /advice, /ask (WebSocket), /refresh routes; LCU listener; data pipeline
            (Riot match aggregation, precompute); retrieval; LLM fine-tune + GGUF serving
frontend/   React + Vite chat UI -- slash commands (/advice, /ask, /help), rank/role dropdowns,
            champ-select auto-detect (real, local-League-client only -- see frontend/README.md)
desktop/    Tauri shell (wraps backend as a sidecar, frontend as the webview) -- not started yet
docs/       gitignored internal planning docs
```

## Status

Backend and frontend are both real and running: a tiered precompute pipeline (eager-tier DB
lookups plus a lazy wider-rank/archetype fallback) backs `/advice`, and a fine-tuned adapter
serves live follow-up questions through `/ask`. Desktop
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
product's eventual packaging path).

Desktop packaging (Tauri) hasn't been scaffolded yet -- no `desktop/README.md` exists.

## Local Development (Windows + WSL)

`vllm` (the precompute batch job) is Linux/CUDA-only -- no Windows wheel exists at any version.
`llama-cpp-python` (the `/ask` live-chat path) has no PyPI Windows wheel either. The native Windows
venv above works fine for `/lcu` and `/advice` dev without either package. For the full backend
including `/ask` and precompute, you need WSL2 with a real Ubuntu distro (Docker Desktop's own
internal WSL VM doesn't count -- no real Python userspace):

```
wsl --install -d Ubuntu   # admin, requires a restart

# inside WSL, from the repo's backend/ dir (e.g. /mnt/c/.../backend)
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
pip install -r requirements.txt

# then from the repo root:
bash wsl-dev.sh
```

`python3` above may not be new enough as-is: a fresh Ubuntu install can ship a Python newer than
`vllm`/`torch` currently support (confirmed on Ubuntu 26.04, whose only default Python was 3.14 --
too new, and no 3.10-3.12 packages existed in its default apt repos). Check `python3 --version`
first; if it's too new, you'll need an older interpreter via the deadsnakes PPA or a source build,
and `apt install` will prompt for your WSL user's sudo password interactively.

## License

Code in this repo: MIT (see `LICENSE`). This project uses Riot Games data under Riot's Developer API terms — it is not licensed, sponsored, or endorsed by Riot Games. League of Legends and Riot Games are trademarks of Riot Games, Inc.
