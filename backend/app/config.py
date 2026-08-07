"""
App configuration, loaded from environment variables (see .env.example at repo root).

Phase 0 note (docs/build-plan.md): ROLE_SCOPED_MATCHUPS below is a placeholder for
the role-scoping decision flagged in docs/architecture-evaluation.md as the first
thing to resolve -- it changes the DB schema and the precompute combinatorics.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    riot_api_key: str = ""
    riot_platform: str = "na1"
    riot_region: str = "americas"

    database_url: str = "postgresql://localhost:5432/lol_matchup_copilot"

    adapter_path: str = ""
    followup_model_path: str = ""

    backend_host: str = "127.0.0.1"  # localhost only -- see testing-strategy.md security notes
    backend_port: int = 8000

    # TODO(Phase 0): decide True (same-lane pairs only) vs False (all pairs).
    # See docs/architecture-evaluation.md "Critical finding".
    role_scoped_matchups: bool = True

    class Config:
        env_file = "../.env"


settings = Settings()
