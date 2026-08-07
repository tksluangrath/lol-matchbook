"""
Turns raw match data into MatchupStat rows. See docs/system-design.md section
3 (Deep Dive) and docs/testing-strategy.md's data-pipeline test table.

TODO(Phase 0): resolve role-scoping (docs/architecture-evaluation.md critical
finding) before implementing this -- it determines whether aggregation groups
by (champ_a, champ_b) globally or by (champ_a, champ_b, role).
"""


def filter_valid_matches(matches: list[dict]) -> list[dict]:
    """TODO(Phase 1): exclude remakes, early surrenders, non-ranked /
    non-Summoner's-Rift games. See testing-strategy.md input-validation cases."""
    raise NotImplementedError


def aggregate_matchup_stats(matches: list[dict], patch: str) -> list[dict]:
    """TODO(Phase 1): compute win rate and phase-window (early/mid/late)
    outcomes per (champ_a, champ_b, rank_bracket). Phase boundaries derived
    from gold/xp diffs and objective timestamps -- see system-design.md.

    Must be idempotent: running this twice on the same input produces
    identical output, no double-counting. See testing-strategy.md."""
    raise NotImplementedError
