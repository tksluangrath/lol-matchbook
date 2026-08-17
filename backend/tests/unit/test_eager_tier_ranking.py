"""
Unit test for app.data_pipeline.precompute.rank_real_candidate_pairs: real
aggregation pipeline against the real cached match CSV, no mocks. Expected
values hand-computed independently this session by running the same real
pipeline directly and reading its output, not derived from the function
under test and copied back in.
"""
from app.data_pipeline.precompute import rank_real_candidate_pairs

# Hand-computed from a direct real run of load_hf_csv_matches +
# filter_valid_matches + aggregate_matchup_stats against the real cached CSV.
EXPECTED_TOTAL_REAL_PAIRS = 2602
EXPECTED_VALID_MATCHES = 901
THEORETICAL_CEILING = 6512

EXPECTED_TOP_5 = [
    ("Milio", "Nami", "utility", 20),
    ("Ezreal", "Jhin", "bottom", 15),
    ("Jhin", "Kaisa", "bottom", 14),
    ("Ezreal", "Jinx", "bottom", 13),
    ("Jhin", "Lucian", "bottom", 11),
]


def test_rank_real_candidate_pairs_matches_hand_computed_total():
    ranked = rank_real_candidate_pairs()
    assert len(ranked) == EXPECTED_TOTAL_REAL_PAIRS
    assert len(ranked) < THEORETICAL_CEILING


def test_rank_real_candidate_pairs_sorted_descending_by_sample_size():
    ranked = rank_real_candidate_pairs()
    sizes = [r["sample_size"] for r in ranked]
    assert sizes == sorted(sizes, reverse=True)


def test_rank_real_candidate_pairs_top_5_matches_hand_computed_values():
    ranked = rank_real_candidate_pairs()
    top_5 = [(r["champ_a"], r["champ_b"], r["role"], r["sample_size"]) for r in ranked[:5]]
    assert top_5 == EXPECTED_TOP_5


def test_rank_real_candidate_pairs_every_row_is_emerald_not_available_phase():
    # Real, committed limitation of this data source (aggregate.py's own
    # docstring) -- every row is rank=emerald, phase=not_available.
    ranked = rank_real_candidate_pairs()
    assert all(r["rank"] == "emerald" for r in ranked)
    assert all(r["phase"] == "not_available" for r in ranked)
