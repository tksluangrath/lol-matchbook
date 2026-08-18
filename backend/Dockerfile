# Dev/CI convenience image only -- NOT the product's real deployment path.
# The shipped app is a Tauri + PyInstaller sidecar (docs/build-plan.md Phase 6,
# docs/tech-stack.md). This image exists to give a reproducible local dev
# backend+DB (`docker compose up`) and a clean environment to run the test
# suite in CI. See docs/decisions/phase-docker-dev-ci-setup.md.
#
# python:3.12, not 3.13: pgserver ships wheels only for 3.9-3.12
# (app/db_migrate.py docstring, docs/decisions/phase0-pgserver-spike.md).
#
# Installs ONLY the serving dependency set (requirements-serving.txt) -- the
# fine-tuning stack (torch/transformers/peft/trl/bitsandbytes/accelerate/vllm)
# is not imported by anything on the serving path and is deliberately
# excluded. Note: sentence-transformers (a genuine serving dependency, used
# by app/retrieval/index.py for local embeddings) pulls in torch itself as
# its own transitive dependency -- that's not this Dockerfile adding the
# training stack back in, it's sentence-transformers' own runtime requirement.

FROM python:3.12-slim AS builder

WORKDIR /app

# llama-cpp-python has no prebuilt wheel for this base image and compiles
# from source (CMake/C++) -- build tools live only in this discarded builder
# stage, not the final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY requirements-serving.txt .
# sentence-transformers pulls in torch as its own transitive dependency
# (see requirements-serving.txt header). Install the CPU-only torch build
# first, from PyTorch's CPU wheel index -- the default PyPI wheel drags in
# ~1.5GB of CUDA/NVIDIA runtime libs this container will never use (this
# app never touches the GPU the game needs, per ADR-001/tech-stack.md #5).
RUN pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements-serving.txt

FROM python:3.12-slim

# -m so the app user gets a real, owned home dir -- sentence-transformers
# (via huggingface_hub) writes its model cache to $HOME/.cache by default,
# and a home-less -r user can't write there (caught by actually running the
# retrieval test suite as this user, not assumed fine).
RUN groupadd -r app && useradd -r -m -d /home/app -g app app

COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1 HOME=/home/app

WORKDIR /app
COPY app ./app
COPY tests ./tests
COPY docker_entrypoint.py .

RUN mkdir -p /app/.pgdata && chown -R app:app /app /home/app
ENV PGDATA=/app/.pgdata
VOLUME /app/.pgdata

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["python", "docker_entrypoint.py"]
