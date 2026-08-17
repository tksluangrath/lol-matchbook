"""
Real integration test for app.data_pipeline.precompute.run_precompute_batch:
real pgserver DB, real dedicated qualitative adapter generation (no mocks).
Expected values in the pure-logic tests are hand-computed independently by
reading app/finetune/data/heldout_context.jsonl directly (see this session's
investigation), not derived by running the code and copying its output back
in as "expected".
"""
import shutil
import tempfile

import pytest
from sqlalchemy import select

from app.data_pipeline.precompute import load_sample_pairs, run_precompute_batch, split_into_sections
from app.db_migrate import migrate
from app.models import Advice, MatchupStat

PATCH = "16.15.1"

# Hand-computed from app/finetune/data/heldout_context.jsonl's real 'prompt'
# context-block text (champ_a, champ_b, role) -> (rank, sample_size, win_rate_pct).
EXPECTED_PAIR_STATS = {
    ("Aatrox", "Kayle", "top"): ("emerald", 4, 50),
    ("Aatrox", "Quinn", "top"): ("emerald", 2, 0),
    ("Aatrox", "Vladimir", "top"): ("emerald", 3, 33),
    ("Ahri", "AurelionSol", "middle"): ("emerald", 2, 50),
    ("Ahri", "Lissandra", "middle"): ("emerald", 2, 0),
    ("Ahri", "Naafiri", "middle"): ("emerald", 2, 50),
    ("Ahri", "Sylas", "middle"): ("emerald", 4, 50),
    ("Ahri", "Xerath", "middle"): ("emerald", 3, 67),
    ("Akali", "Renekton", "top"): ("emerald", 2, 0),
    ("Akali", "Talon", "middle"): ("emerald", 2, 100),
}


def test_load_sample_pairs_returns_10_real_pairs_with_hand_computed_values():
    pairs = load_sample_pairs()
    assert len(pairs) == 10
    for pair in pairs:
        key = (pair["champ_a"], pair["champ_b"], pair["role"])
        rank, sample_size, win_rate_pct = EXPECTED_PAIR_STATS[key]
        assert pair["rank_bracket"] == rank
        assert pair["sample_size"] == sample_size
        assert pair["win_rate"] == win_rate_pct / 100
        assert "Context:" in pair["generation_prompt"]
        assert "kit:" in pair["generation_prompt"]


def test_split_into_sections_exact_labels():
    text = "Early:  \nfoo bar.\n\nMid:  \nbaz qux.\n\nLate:  \nend text."
    sections = split_into_sections(text)
    assert sections == {"early": "foo bar.", "mid": "baz qux.", "late": "end text."}


def test_split_into_sections_accepts_real_label_variants():
    # "Mid-game:"/"Late game:" are real variants found in the v2 adapter's
    # held-out generations (two-adapter diagnostic) with full real content.
    text = "Early:  \nfoo.\n\nMid-game:  \nbar.\n\nLate game:  \nbaz."
    sections = split_into_sections(text)
    assert sections == {"early": "foo.", "mid": "bar.", "late": "baz."}


def test_split_into_sections_returns_none_when_a_label_is_missing():
    text = "Early:  \nfoo.\n\nMid:  \nbar."  # no Late section at all
    assert split_into_sections(text) is None


@pytest.fixture(scope="module")
def migrated_db():
    pgdata = tempfile.mkdtemp(prefix="precompute_test_")
    server, engine = migrate(pgdata=pgdata)
    try:
        yield engine
    finally:
        engine.dispose()
        server.cleanup()
        shutil.rmtree(pgdata, ignore_errors=True)


@pytest.fixture(scope="module")
def precompute_result(migrated_db):
    return run_precompute_batch(PATCH, engine=migrated_db)


def test_precompute_batch_writes_30_real_advice_rows_for_10_pairs(migrated_db, precompute_result):
    with migrated_db.connect() as conn:
        advice_rows = conn.execute(select(Advice)).fetchall()
    # 10 pairs * 3 phases, minus any real grounding/section-split failures
    # (logged in precompute_result["skipped"], never silently written).
    expected_written_pairs = 10 - len(precompute_result["skipped"])
    assert len(precompute_result["written_pairs"]) == expected_written_pairs
    assert len(advice_rows) == expected_written_pairs * 3
    for row in advice_rows:
        assert row.text.strip() != ""
        assert row.tier == "eager"
        assert row.fact_source_id is not None


def test_precompute_batch_matchup_stats_written_per_phase(migrated_db, precompute_result):
    with migrated_db.connect() as conn:
        stat_rows = conn.execute(select(MatchupStat)).fetchall()
    expected_written_pairs = 10 - len(precompute_result["skipped"])
    assert len(stat_rows) == expected_written_pairs * 3
    for row in stat_rows:
        key = (row.champ_a, row.champ_b, row.role)
        _, sample_size, win_rate_pct = EXPECTED_PAIR_STATS[key]
        assert row.sample_size == sample_size
        assert row.win_rate == win_rate_pct / 100


def test_precompute_batch_rerun_is_idempotent(migrated_db, precompute_result):
    with migrated_db.connect() as conn:
        before_advice = conn.execute(select(Advice)).fetchall()
        before_stats = conn.execute(select(MatchupStat)).fetchall()

    rerun_result = run_precompute_batch(PATCH, engine=migrated_db)
    # Second run must skip every pair before generating (no new model call
    # needed) -- all 10 should show up as already_present, none regenerated.
    assert len(rerun_result["written_pairs"]) == 0
    assert len(rerun_result["already_present"]) == 10

    with migrated_db.connect() as conn:
        after_advice = conn.execute(select(Advice)).fetchall()
        after_stats = conn.execute(select(MatchupStat)).fetchall()
    assert len(after_advice) == len(before_advice)
    assert len(after_stats) == len(before_stats)


def test_precompute_batch_logs_incomplete_generation_instead_of_writing_fabricated_row(migrated_db):
    # Real generation, deliberately budget-starved (max_new_tokens=5) so it
    # cannot possibly complete all three labeled sections -- a real,
    # reliable way to trigger split_into_sections returning None without
    # mocking model output. (A wrong win_rate was considered instead, but
    # this adapter almost never cites a percentage at all -- established in
    # the two-adapter diagnostic -- so it would not reliably trigger
    # fact_grounding_check's mismatch path.)
    pairs = load_sample_pairs(n=1)

    result = run_precompute_batch(
        "16.99.9-badpatch-test", engine=migrated_db, pairs=pairs, max_new_tokens=5
    )

    assert len(result["written_pairs"]) == 0
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["reason"] == "could_not_split_sections"

    with migrated_db.connect() as conn:
        rows = conn.execute(
            select(Advice).where(Advice.patch == "16.99.9-badpatch-test")
        ).fetchall()
    assert len(rows) == 0
