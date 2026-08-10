"""
Riot public API client -- Match-V5 (match history) and League-V4 (rank tier).
See docs/system-design.md and docs/build-plan.md Phase 1.

This is entirely separate from app/lcu/listener.py, which talks to the local
League client instead of Riot's servers.

Phase 0 TODO: a personal/dev key is heavily rate-limited (~100 req/2min) and
expires every 24h. Apply for a production key early (real approval lag) and
have a public-dataset fallback ready to bootstrap the pipeline while waiting --
see docs/build-plan.md Phase 0.

--- Data-source-agnostic match shape ----------------------------------------
app.data_pipeline.aggregate never sees a raw CSV row or a raw Match-V5 JSON
blob -- it only ever consumes a plain "normalized match" dict, regardless of
which of the two loaders below produced it:

    {
        "match_id": str,
        "queue_id": int,
        "surrendered": bool,          # game_ended_in_surrender
        "participants": [
            {
                "champion": str,       # champion_name
                "team_position": str,  # TOP | JUNGLE | MIDDLE | BOTTOM | UTILITY
                "team_id": int,        # 100 | 200 -- which side, for opposing-lane pairing
                "win": bool,
            },
            ...
        ],
    }

`load_hf_csv_matches` builds this shape from the BoostedJonP HF dataset export
today; `normalize_riot_match` is the not-yet-implemented adapter for a real
Match-V5 pull later. aggregate.py is written against this shape only, so
swapping the source later requires no change there.
"""
import csv

import httpx

from app.config import settings

BASE_HEADERS = {"X-Riot-Token": settings.riot_api_key}


def normalize_riot_match(raw: dict) -> dict:
    """TODO(Phase 1, real API): convert a raw Match-V5 `/matches/{id}` response
    (raw["info"]["participants"], raw["info"]["queueId"], ...) into the
    normalized match shape documented in this module's docstring. Not
    implemented -- no production Riot API key yet (see phase0-riot-api-access
    decision doc); load_hf_csv_matches below is the loader actually exercised
    until one is available."""
    raise NotImplementedError


def load_hf_csv_matches(csv_path: str) -> list[dict]:
    """Read the BoostedJonP/league_of_legends_match_data CSV export (one row
    per player-match) and group rows by match_id into the normalized match
    shape documented in this module's docstring.

    Two data-quality quirks found by actually inspecting the file (not
    assumed) and handled here so aggregate.py never has to know about them:

    - The export contains whole-row duplicate participant rows within some
      matches (verified: ~9.2K of ~24.6K rows in the Emerald CSV are exact
      duplicates of another row in the same match) -- deduped per match on
      (champion, team_position, team_id, win) so sample counts aren't
      artificially inflated.
    - ~135 rows have an empty team_position (can't be placed in a lane) --
      skipped, they can't contribute to a same-lane matchup.
    """
    by_match: dict[str, dict] = {}
    seen_participants: dict[str, set] = {}

    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            position = row["team_position"]
            if not position:
                continue

            match_id = row["match_id"]
            match = by_match.setdefault(
                match_id,
                {
                    "match_id": match_id,
                    "queue_id": int(row["queue_id"]),
                    "surrendered": row["game_ended_in_surrender"].strip().upper() == "TRUE",
                    "participants": [],
                },
            )

            dedup_key = (row["champion_name"], position, row["team_id"], row["win"])
            seen = seen_participants.setdefault(match_id, set())
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            match["participants"].append(
                {
                    "champion": row["champion_name"],
                    "team_position": position,
                    "team_id": int(row["team_id"]),
                    "win": row["win"].strip().upper() == "TRUE",
                }
            )

    return list(by_match.values())


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
