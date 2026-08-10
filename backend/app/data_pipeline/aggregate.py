"""
Turns normalized match dicts (see app.data_pipeline.riot_client's
data-source-agnostic match shape) into matchup win-rate rows. See
docs/system-design.md section 3 (Deep Dive) and docs/testing-strategy.md's
data-pipeline test table.

Committed limitations of the current data source (BoostedJonP HF CSV export),
both load-bearing for every row this module produces -- see
docs/decisions/phase1-role-pair-count.md and phase0-pgserver-spike.md context:

- No timeline data, only final-match totals -- genuine early/mid/late
  bucketing needs gold/xp diffs at timestamps, which this source doesn't
  have. Every row's phase is PHASE ("not_available"), never early/mid/late,
  until a timeline-capable source exists.
- Emerald-only sample -- every row's rank is RANK ("emerald"), not a real
  multi-bracket split.

Role is NOT filtered by the phase1-role-pair-count.md >10% viability
threshold here -- that threshold answers "which pairs are common enough to
eagerly precompute" (docs/decisions/tiered-fallback-design.md), a later
tiering concern, not per-match aggregation. Every match's real per-player
team_position is used directly.
"""

RANKED_SOLO_DUO_QUEUE_ID = 420
PHASE = "not_available"
RANK = "emerald"


def filter_valid_matches(matches: list[dict]) -> list[dict]:
    """Exclude surrendered games and anything that isn't ranked solo/duo
    (queue_id 420).

    Verified by actually inspecting the BoostedJonP Emerald CSV rather than
    trusting its description: the file is NOT already filtered to queue_id
    420 alone -- it contains 420 (ranked solo/duo, 21,360 rows), 440 (ranked
    flex, 3,140 rows) and 1700 (arena, 118 rows). The queue_id check below is
    therefore load-bearing, not defensive dead code.
    """
    return [
        m
        for m in matches
        if not m.get("surrendered")
        and m.get("queue_id") == RANKED_SOLO_DUO_QUEUE_ID
    ]


def _lane_matchups(match: dict):
    """Yield (champ_lo, champ_hi, role, champ_lo_won) for each pair of
    participants in `match` who shared a lane (same team_position, opposing
    team_id). champ_lo/champ_hi are alphabetically ordered so a pair is
    counted once regardless of which side of the lane provided the row."""
    by_role: dict[str, list[dict]] = {}
    for p in match["participants"]:
        by_role.setdefault(p["team_position"], []).append(p)

    for role, players in by_role.items():
        for i in range(len(players)):
            for j in range(i + 1, len(players)):
                a, b = players[i], players[j]
                if a["team_id"] == b["team_id"]:
                    continue  # same side -- not an opposing-lane matchup
                if a["champion"] == b["champion"]:
                    continue  # a champion can't matchup against itself
                lo, hi = sorted((a, b), key=lambda p: p["champion"])
                yield lo["champion"], hi["champion"], role.lower(), lo["win"]


def aggregate_matchup_stats(matches: list[dict]) -> list[dict]:
    """Compute win rate per (champ_a, champ_b, role), where champ_a < champ_b
    alphabetically (each unordered pair counted once). rank and phase are the
    fixed values documented in this module's docstring -- see the two
    committed-behavior tests in test_aggregate.py.

    Idempotent: identical input (any order) always produces identical,
    identically-ordered output -- callers can rely on running this twice
    over the same matches never double-counting or reordering rows.
    """
    counts: dict[tuple[str, str, str], list[int]] = {}
    for match in matches:
        for champ_a, champ_b, role, champ_a_won in _lane_matchups(match):
            key = (champ_a, champ_b, role)
            wins_games = counts.setdefault(key, [0, 0])
            wins_games[1] += 1
            if champ_a_won:
                wins_games[0] += 1

    rows = [
        {
            "champ_a": champ_a,
            "champ_b": champ_b,
            "role": role,
            "rank": RANK,
            "phase": PHASE,
            "win_rate": wins / games,
            "sample_size": games,
        }
        for (champ_a, champ_b, role), (wins, games) in counts.items()
    ]
    rows.sort(key=lambda r: (r["champ_a"], r["champ_b"], r["role"]))
    return rows
