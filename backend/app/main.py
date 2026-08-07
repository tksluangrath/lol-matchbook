"""
FastAPI entrypoint. See docs/system-design.md section 2 (API contracts) and
docs/build-plan.md Phase 4.

Run locally with: uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
"""
from fastapi import FastAPI

from app.config import settings
from app.routers import advice, ask, refresh

app = FastAPI(title="lol-matchup-copilot backend")

app.include_router(advice.router)
app.include_router(ask.router)
app.include_router(refresh.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    # bind to localhost only -- never 0.0.0.0, see docs/testing-strategy.md
    uvicorn.run(app, host=settings.backend_host, port=settings.backend_port)
