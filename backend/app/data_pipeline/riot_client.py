"""
Riot public API client -- Match-V5 (match history) and League-V4 (rank tier).
See docs/system-design.md and docs/build-plan.md Phase 1.

This is entirely separate from app/lcu/listener.py, which talks to the local
League client instead of Riot's servers.

Phase 0 TODO: a personal/dev key is heavily rate-limited (~100 req/2min) and
expires every 24h. Apply for a production key early (real approval lag) and
have a public-dataset fallback ready to bootstrap the pipeline while waiting --
see docs/build-plan.md Phase 0.
"""
import httpx

from app.config import settings

BASE_HEADERS = {"X-Riot-Token": settings.riot_api_key}


class RiotClient:
    def __init__(self, platform: str = None, region: str = None):
        self.platform = platform or settings.riot_platform
        self.region = region or settings.riot_region

    def get_match(self, match_id: str) -> dict:
        """TODO(Phase 1): GET /lol/match/v5/matches/{matchId} via self.region."""
        raise NotImplementedError

    def get_league_entries(self, summoner_id: str) -> list[dict]:
        """TODO(Phase 1): GET /lol/league/v4/entries/by-summoner/{summonerId} via self.platform,
        for rank-tier resolution -- see docs/system-design.md data model."""
        raise NotImplementedError
