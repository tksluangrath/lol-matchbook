"""
Unit tests for app.data_pipeline.aggregate, against small hand-authored
fixtures (no HF dataset download needed here -- see
tests/integration/test_pipeline_integration.py for the real-dataset checks).

Expected values below are computed by hand from the fixture matches, not by
running the implementation and copying its output back in.
"""
import json

from app.data_pipeline.aggregate import (
    PHASE,
    RANK,
    RANKED_SOLO_DUO_QUEUE_ID,
    aggregate_matchup_stats,
    filter_valid_matches,
)


def _match(match_id, participants, queue_id=420, surrendered=False):
    return {
        "match_id": match_id,
        "queue_id": queue_id,
        "surrendered": surrendered,
        "participants": participants,
    }


def _p(champion, team_position, team_id, win):
    return {"champion": champion, "team_position": team_position, "team_id": team_id, "win": win}


# Three ranked (queue 420), non-surrendered matches with a TOP lane
# Darius-vs-Garen matchup: Darius wins twice, loses once -> 2/3 win rate for
# the alphabetically-first champ (Darius). Each match also has an independent
# JUNGLE matchup (Vi vs Zac) that Vi wins once, loses once -> 1/2.
VALID_MATCHES = [
    _match(
        "M1",
        [
            _p("Darius", "TOP", 100, True),
            _p("Garen", "TOP", 200, False),
            _p("Vi", "JUNGLE", 100, True),
            _p("Zac", "JUNGLE", 200, False),
        ],
    ),
    _match(
        "M2",
        [
            _p("Garen", "TOP", 100, False),
            _p("Darius", "TOP", 200, True),
            _p("Vi", "JUNGLE", 100, False),
            _p("Zac", "JUNGLE", 200, True),
        ],
    ),
    _match(
        "M3",
        [
            _p("Darius", "TOP", 100, False),
            _p("Garen", "TOP", 200, True),
        ],
    ),
]

# Should be excluded by filter_valid_matches.
SURRENDERED_MATCH = _match(
    "M4",
    [_p("Darius", "TOP", 100, True), _p("Garen", "TOP", 200, False)],
    surrendered=True,
)
NON_RANKED_MATCH = _match(
    "M5",
    [_p("Darius", "TOP", 100, True), _p("Garen", "TOP", 200, False)],
    queue_id=440,  # ranked flex, not solo/duo
)


def test_filter_valid_matches_excludes_surrenders_and_non_ranked_queue():
    matches = VALID_MATCHES + [SURRENDERED_MATCH, NON_RANKED_MATCH]
    result = filter_valid_matches(matches)
    assert result == VALID_MATCHES
    assert all(m["queue_id"] == RANKED_SOLO_DUO_QUEUE_ID for m in result)
    assert all(not m["surrendered"] for m in result)


def test_aggregate_matchup_stats_hand_computed_win_rate():
    rows = aggregate_matchup_stats(VALID_MATCHES)

    by_key = {(r["champ_a"], r["champ_b"], r["role"]): r for r in rows}

    darius_garen = by_key[("Darius", "Garen", "top")]
    assert darius_garen["sample_size"] == 3
    assert darius_garen["win_rate"] == 2 / 3  # hand count: 2 Darius wins, 1 loss, of 3 games

    vi_zac = by_key[("Vi", "Zac", "jungle")]
    assert vi_zac["sample_size"] == 2
    assert vi_zac["win_rate"] == 1 / 2  # hand count: 1 Vi win, 1 loss, of 2 games

    assert len(rows) == 2


def test_aggregate_matchup_stats_dedupes_unordered_pair_direction():
    # M2 lists Garen on team 100 and Darius on team 200 (reversed from M1) --
    # both must land under the same (Darius, Garen) key, not two separate rows.
    rows = aggregate_matchup_stats(VALID_MATCHES)
    keys = [(r["champ_a"], r["champ_b"], r["role"]) for r in rows]
    assert ("Garen", "Darius", "top") not in keys
    assert keys.count(("Darius", "Garen", "top")) == 1


def test_no_row_ever_has_a_real_phase_bucket():
    """Committed behavior: this data source has no timeline data, so no row
    this pipeline produces may ever claim early/mid/late phase granularity."""
    rows = aggregate_matchup_stats(VALID_MATCHES)
    assert len(rows) > 0
    for row in rows:
        assert row["phase"] not in {"early", "mid", "late"}
        assert row["phase"] == PHASE == "not_available"


def test_every_row_uses_the_fixed_emerald_rank():
    """Committed behavior: this data source is Emerald-only, so no row may
    claim a different rank bracket."""
    rows = aggregate_matchup_stats(VALID_MATCHES)
    assert len(rows) > 0
    for row in rows:
        assert row["rank"] == RANK == "emerald"


def test_aggregate_matchup_stats_is_idempotent():
    rows_first = aggregate_matchup_stats(VALID_MATCHES)
    rows_second = aggregate_matchup_stats(VALID_MATCHES)
    assert json.dumps(rows_first) == json.dumps(rows_second)
