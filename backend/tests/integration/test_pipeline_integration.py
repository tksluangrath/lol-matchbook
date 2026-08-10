"""
Integration test: real BoostedJonP/league_of_legends_match_data HF dataset ->
riot_client.load_hf_csv_matches -> aggregate.filter_valid_matches ->
aggregate.aggregate_matchup_stats, end to end.

Downloads the Emerald CSV export (~11.6MB, well under the 500MB resource
gate) via huggingface_hub on first run; huggingface_hub caches it locally
afterward. Skipped if the download isn't possible in this environment (e.g.
no network) rather than failing the whole suite.
"""
import json

import pytest

from app.data_pipeline.aggregate import (
    PHASE,
    RANK,
    RANKED_SOLO_DUO_QUEUE_ID,
    aggregate_matchup_stats,
    filter_valid_matches,
)
from app.data_pipeline.riot_client import load_hf_csv_matches

HF_REPO_ID = "BoostedJonP/league_of_legends_match_data"
HF_FILENAME = "league_of_legends_emerald_match_data.csv"


@pytest.fixture(scope="module")
def csv_path():
    hf_hub_download = pytest.importorskip("huggingface_hub").hf_hub_download
    try:
        return hf_hub_download(repo_id=HF_REPO_ID, filename=HF_FILENAME, repo_type="dataset")
    except Exception as exc:  # network unavailable, etc.
        pytest.skip(f"could not download HF dataset: {exc}")


@pytest.fixture(scope="module")
def raw_matches(csv_path):
    return load_hf_csv_matches(csv_path)


def test_loader_produces_the_documented_normalized_shape(raw_matches):
    assert len(raw_matches) > 0
    sample = raw_matches[0]
    assert set(sample.keys()) == {"match_id", "queue_id", "surrendered", "participants"}
    assert isinstance(sample["queue_id"], int)
    assert isinstance(sample["surrendered"], bool)
    for p in sample["participants"]:
        assert set(p.keys()) == {"champion", "team_position", "team_id", "win"}


def test_dataset_is_not_already_queue_filtered_verifies_the_assumption(raw_matches):
    """The phase1-role-pair-count.md decision doc's premise ("queue_id
    already filtered to ranked 420") does not hold for the raw export --
    verified here against the real file, not assumed. This is exactly why
    filter_valid_matches's queue_id check is load-bearing."""
    queue_ids = {m["queue_id"] for m in raw_matches}
    assert queue_ids != {RANKED_SOLO_DUO_QUEUE_ID}, (
        "expected the raw dataset to contain non-420 queues too; if this "
        "assertion fails the dataset changed and the queue filter may now "
        "be dead code -- worth re-checking, not silently accepting"
    )


def test_filter_valid_matches_on_real_data_keeps_only_ranked_non_surrendered(raw_matches):
    filtered = filter_valid_matches(raw_matches)
    assert len(filtered) > 0
    assert len(filtered) < len(raw_matches)
    assert all(m["queue_id"] == RANKED_SOLO_DUO_QUEUE_ID for m in filtered)
    assert all(not m["surrendered"] for m in filtered)


def test_aggregate_on_real_data_never_emits_a_real_phase_bucket(raw_matches):
    rows = aggregate_matchup_stats(filter_valid_matches(raw_matches))
    assert len(rows) > 0
    assert all(r["phase"] not in {"early", "mid", "late"} for r in rows)
    assert all(r["phase"] == PHASE for r in rows)


def test_aggregate_on_real_data_always_uses_the_fixed_emerald_rank(raw_matches):
    rows = aggregate_matchup_stats(filter_valid_matches(raw_matches))
    assert len(rows) > 0
    assert all(r["rank"] == RANK for r in rows)


def test_aggregate_on_real_data_win_rates_are_valid_probabilities(raw_matches):
    rows = aggregate_matchup_stats(filter_valid_matches(raw_matches))
    for r in rows:
        assert 0.0 <= r["win_rate"] <= 1.0
        assert r["sample_size"] >= 1


def test_end_to_end_pipeline_is_idempotent(raw_matches):
    filtered = filter_valid_matches(raw_matches)
    rows_first = aggregate_matchup_stats(filtered)
    rows_second = aggregate_matchup_stats(filtered)
    assert json.dumps(rows_first) == json.dumps(rows_second)
