#!/bin/bash
# Launch the backend from WSL -- vllm and llama-cpp-python have no Windows
# wheels (vllm is Linux/CUDA-only by design; llama-cpp-python has no PyPI
# Windows wheel and needs a source build), so the full backend runs from
# here instead of the native Windows venv used for /lcu and /advice-only dev.
cd "$(dirname "${BASH_SOURCE[0]}")/backend"
source .venv-wsl/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
