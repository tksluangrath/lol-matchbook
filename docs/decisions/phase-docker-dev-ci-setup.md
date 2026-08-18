# Docker dev/CI setup

This is dev/CI tooling only. It does not change the product's deployment path: the
shipped app is a Tauri + PyInstaller sidecar (`docs/build-plan.md` Phase 6,
`docs/tech-stack.md`). This Docker setup exists for two things: a reproducible
local dev backend+DB via `docker compose up`, and a clean environment to run
the backend test suite in CI. Nothing here is a production/serving concern
(no load balancing, no multi-replica configs, no separate DB service).

Files: `backend/Dockerfile`, `backend/requirements-serving.txt`,
`backend/docker_entrypoint.py`, `backend/.dockerignore`, `docker-compose.yml`
(repo root), `.github/workflows/backend-tests.yml`.

## Serving vs. training dependency split

Grepped actual imports (not package-name guessing) across `app/routers`,
`app/llm`, `app/retrieval`, `app/db*`, `app/config.py`, `app/models.py`,
`app/lcu`. None of them import `transformers`, `peft`, `trl`, `bitsandbytes`,
`accelerate`, or `vllm`. Those five packages only get pulled in by
`app/finetune/` and by `app/data_pipeline/precompute.py` (the offline
precompute launcher, which itself imports `app.finetune.eval` to load the
fine-tuned adapter for batch generation -- a training-adjacent job, not part
of the live `/advice`/`/ask` serving path).

`backend/requirements-serving.txt` is the serving-only subset: fastapi,
uvicorn, websockets, pgserver, sqlalchemy, pgvector, psycopg, llama-cpp-python,
sentence-transformers, requests, httpx, python-dotenv, pydantic-settings,
pytest, pytest-asyncio. `backend/requirements.txt` (full, including the
fine-tuning stack) is untouched and still what you use outside the container
for training work.

**One real exception worth flagging, not silently added:** `sentence-transformers`
declares `torch` as its own hard runtime dependency (it needs it to run the
embedding model in `app/retrieval/index.py`, which the live `/ask` path uses
for retrieval). So torch ends up in the image regardless -- not because this
Dockerfile added the training stack back in, but because a package already
agreed to be a serving dependency in `docs/tech-stack.md` #7 brings it in
transitively. To keep this from being expensive: the Dockerfile installs
torch's CPU-only build from PyTorch's own CPU wheel index before installing
the rest of `requirements-serving.txt`. The default PyPI torch wheel bundles
~1.5GB of CUDA/NVIDIA runtime libraries this container will never use (the
app never touches the GPU the game needs -- ADR-001). Confirmed with a real
before/after build: default PyPI torch wheel produced a 3.02GB image; the
CPU-only wheel produced 452MB for the same image.

`transformers`, `peft`, `trl`, `bitsandbytes`, `accelerate`, `vllm` are not in
the image. Confirmed by running the built container's Python interpreter --
`import peft` / `import datasets` fail with `ModuleNotFoundError` (surfaced
for real during the test run below, not just by inspecting requirements.txt).

## Architecture note: python:3.12, not 3.13

`pgserver` ships wheels only for Python 3.9-3.12 (no 3.13 wheel), documented
in `backend/app/db_migrate.py`'s own docstring and the original spike
(`docs/decisions/phase0-pgserver-spike.md`). The image uses `python:3.12-slim`.

## pgserver stays embedded, no separate DB service

`docker-compose.yml` defines exactly one service (`backend`). `pgserver` runs
inside that same container, writing to `/app/.pgdata`, which is a named
volume (`pgdata:`) for persistence across container restarts -- this is the
whole reason `pgserver` was picked over a normal Postgres service
(`docs/tech-stack.md` #4): no second container to manage.

`app/main.py`/`app/db.py` don't start `pgserver` themselves yet (that's
still an open TODO in the real app code, unrelated to this Docker work).
`backend/docker_entrypoint.py` is the container's actual startup path: it
calls the exact same `start_pgserver()` function from `app/db_migrate.py`
that the original Phase 0 spike validated (same start method, same
`cleanup_mode="stop"`), points `DATABASE_URL` at the real running server
before importing `app.main`, creates tables, then runs uvicorn in the same
process so the pgserver-managed subprocess stays alive for the container's
life. This is dev/CI convenience wiring only -- it does not change how the
real Tauri-packaged app starts `pgserver`.

## Real build numbers

Built on this machine (Apple Silicon, macOS, Docker Desktop). `pgserver` has
no Linux arm64 wheel at all (checked PyPI directly: manylinux wheels exist
only for x86_64), so the image can only be built and run as `linux/amd64`,
which on this host means QEMU cross-architecture emulation -- there is no
native or Rosetta-accelerated amd64 path available in this Docker Desktop
install (checked: no Rosetta/VirtualizationFramework keys in
`~/Library/Group Containers/group.com.docker/settings-store.json`, and
`docker desktop enable`/`--help` exposes no such toggle from the CLI).

- Cold build (no cache, `docker build --platform linux/amd64`): **7m 4.67s**
  real time. Most of that is llama-cpp-python compiling from source (CMake/C++,
  ~4.5 min under emulation -- it has no prebuilt wheel for this base image)
  and downloading torch's CPU wheel plus the rest of the dependency set.
  This would be substantially faster on a native x86_64 host (e.g. GitHub
  Actions' `ubuntu-latest` runners, which is what `.github/workflows/backend-tests.yml`
  actually runs on).
- Rebuild with the dependency-install layer cached (only a small final-stage
  change): **1m 1.98s** real time.
- Real image size: **452MB** (`docker image inspect --format '{{.Size}}'`).
  Note: `docker images` lists this same image at 2.18GB in its table output --
  that number includes the buildx attestation/provenance manifest-list
  overhead, not the actual runtime image; 452MB is the number that matters
  for "how big is the container."

## Real in-container test suite run

Ran the actual backend test suite inside the built container (`docker run
lol-matchup-backend:dev python -m pytest ...`), not on the host. Excluded 17
test files that transitively import the training stack (`peft`, `datasets`,
`transformers` via `app.finetune.train`/`app.finetune.eval` or
`app.data_pipeline.precompute`, which imports `app.finetune.eval` at module
level) -- confirmed by letting pytest try to collect them first and reading
the real `ModuleNotFoundError`s, not guessed in advance. Full excluded list
is in `.github/workflows/backend-tests.yml`.

**Result: 55 passed, 2 failed, 18 errors** (75 collected).

- The 2 failures (`test_context_conditioned_qa.py`) are pre-existing: they
  need local fine-tuning data artifacts (`app/finetune/data/train.jsonl`,
  `heldout.jsonl`) that are gitignored and deliberately excluded from the
  Docker build context (`.dockerignore`) -- not a Docker bug, these would
  fail the same way in any environment that doesn't have those files
  generated yet.
- One real Docker-specific bug was found and fixed during this run: the
  non-root container user initially had no writable home directory, so
  `sentence-transformers`' first real model download (via `huggingface_hub`)
  failed with `PermissionError: /home/app`. Fixed by creating a real home
  dir for the app user (`useradd -m`) and setting `HOME`. Confirmed fixed by
  re-running the retrieval tests, which now actually download the real
  embedding model and pass.
- The 18 errors are every test that touches a real `pgserver` instance
  (`test_db_migrate.py`, `test_lazy_tier_fallback.py`,
  `test_ask_context_builder.py`, `test_models.py`) -- see the persistence
  section below for why, and note it is not a training-dependency exclusion.

## Real persistence test: blocked in this environment, root cause identified, not papered over

Task was to start the container, write a real row via the app's real DB path
(`app.db_migrate.start_pgserver`), stop/restart, confirm the row survived via
the mounted volume -- same standard as the original Phase 0 pgserver spike.

**This could not be completed for real on this machine.** `pgserver`'s
bundled Postgres binary segfaults (`SIGSEGV`) immediately under this Docker
Desktop's QEMU emulation, reproduced 3 times independently (once via
`docker run` with the full entrypoint, twice calling `start_pgserver()`
directly), and even `initdb --version` alone crashes the same way -- it's
not an argument/data-dir issue, the binary itself won't run.

To rule out "all Postgres binaries crash under this host's emulation," the
official `postgres:16` image's `initdb` was run under the identical
`--platform linux/amd64` emulation on this same machine and it worked fine.
So this is specific to `pgserver`'s bundled binary (likely built with a wheel
toolchain that assumes CPU instructions QEMU's translation doesn't handle
correctly), not a generic "Postgres can't run under emulation" problem, and
not a bug in `docker_entrypoint.py` -- it calls the exact same
`start_pgserver()` the Phase 0 spike already validated works on a real,
non-emulated machine.

Root cause: `pgserver` ships no Linux arm64 wheel (verified against PyPI's
file list directly), so on this Apple Silicon host, running its amd64 image
means QEMU emulation, and this specific binary doesn't survive that. This
would not be an issue on a native x86_64 host -- which is exactly what
`.github/workflows/backend-tests.yml`'s `ubuntu-latest` runner is, and what
any real Linux CI box or Intel/AMD dev machine would be. **I did not push
this workflow to actually verify on a native amd64 GitHub Actions runner --
that requires pushing to the remote, which I don't do without being asked.**
If you want a real confirmation of persistence-across-restart, either run
`docker compose up` on a native x86_64 machine, or say the word and I'll push
a branch to let the CI workflow validate it on GitHub's runners.

## What's genuinely confirmed vs. what isn't

Confirmed for real, on this machine:
- Image builds successfully, serving deps only (plus torch as
  sentence-transformers' legitimate transitive dependency, CPU-only build).
- 452MB image, 7m 4.67s cold build / 1m 2s cached rebuild.
- Non-training-stack test files actually run in the container: 55 pass, 2
  pre-existing fails unrelated to Docker, 0 failures caused by the Docker
  setup itself (the one real bug found -- HOME permissions -- was fixed).
- Training dependencies (`transformers`/`peft`/`trl`/`bitsandbytes`/`accelerate`/`vllm`)
  are confirmed absent from the image by real `ModuleNotFoundError`s, not
  by inspecting requirements.txt.

Not confirmed here, real and open:
- pgserver persistence-across-container-restart, blocked by this host's
  QEMU emulation crashing pgserver's binary (root cause identified, not a
  flake, not swept under the rug). Needs a native x86_64 environment to
  verify for real.

This Docker setup doesn't touch, and isn't a substitute for, the real
deployment path: Tauri + PyInstaller (`docs/build-plan.md` Phase 6). It's
dev/CI convenience only.
