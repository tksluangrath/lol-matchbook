"""
Hand-computed isolation test for force_regenerate_pairs, run BEFORE any real
regeneration against the live DB (per docs/decisions/phase3-eager-tier-
precompute.md's "Idempotency" section -- an overly broad check once
regenerated all 109 candidate pairs instead of the intended subset; this
proves the scoped version can't repeat that mistake).

Real pgserver DB (same fixture pattern as test_precompute_batch.py), but
generate()/load_model_and_tokenizer() are monkeypatched to a fast
deterministic fake -- this is a scoping/isolation test, not a real-model
test (that's covered by the integration suite and the real regeneration
run itself).
"""
import shutil
import tempfile

import pytest
from sqlalchemy import select

from app.data_pipeline import precompute
from app.data_pipeline.precompute import force_regenerate_pairs
from app.db_migrate import migrate
from app.models import Advice, MatchupStat

PATCH = "16.15.1"

TARGET = {
    "champ_a": "Caitlyn", "champ_b": "Samira", "role": "bottom",
    "rank_bracket": "emerald", "sample_size": 5, "win_rate": 0.4,
    "generation_prompt": "Context: 5 games observed this patch between Caitlyn and Samira in the bottom lane. Caitlyn win rate: 40%.\nCaitlyn kit: real kit text\nSamira kit: real kit text",
}
BYSTANDER = {
    "champ_a": "Briar", "champ_b": "Viego", "role": "jungle",
    "rank_bracket": "emerald", "sample_size": 3, "win_rate": 0.5,
    "generation_prompt": "Context: 3 games observed this patch between Briar and Viego in the jungle lane. Briar win rate: 50%.\nBriar kit: real kit text\nSamira kit: real kit text",
}


def _fake_generate(model, tokenizer, prompt, max_new_tokens, **kw):
    # No invented capitalized phrases, no cited percentage -- passes
    # fact_grounding_check unconditionally.
    return "Early:\nplay safe.\n\nMid:\nregenerated content.\n\nLate:\nclose it out."


@pytest.fixture
def db():
    pgdata = tempfile.mkdtemp(prefix="force_regen_test_")
    server, engine = migrate(pgdata=pgdata)
    try:
        yield engine
    finally:
        engine.dispose()
        server.cleanup()
        shutil.rmtree(pgdata, ignore_errors=True)


def _seed_written(engine, pair, patch, marker: str):
    """Writes one real (already-precomputed) pair via the same code path
    force_regenerate_pairs itself uses, so the bystander row is a real
    Advice/MatchupStat row, not a hand-built fixture shortcut."""
    precompute.run_precompute_batch(patch, engine=engine, pairs=[pair])


def test_force_regenerate_touches_only_named_target_not_bystander(monkeypatch, db):
    monkeypatch.setattr(precompute, "generate", _fake_generate)
    monkeypatch.setattr(precompute, "load_model_and_tokenizer", lambda adapter_dir: ("fake-model", "fake-tok"))

    # Seed both pairs as already-written (simulates the real contaminated
    # rows already sitting in the live DB before this task's fix).
    _seed_written(db, TARGET, PATCH, "target")
    _seed_written(db, BYSTANDER, PATCH, "bystander")

    with db.connect() as conn:
        bystander_before = conn.execute(
            select(Advice).where(Advice.champ_a == "Briar", Advice.champ_b == "Viego", Advice.role == "jungle")
        ).fetchall()
        bystander_stats_before = conn.execute(
            select(MatchupStat).where(MatchupStat.champ_a == "Briar", MatchupStat.champ_b == "Viego", MatchupStat.role == "jungle")
        ).fetchall()
    assert len(bystander_before) == 3  # early/mid/late really written

    result = force_regenerate_pairs(
        PATCH, targets=[("Caitlyn", "Samira", "bottom")], engine=db, pairs=[TARGET],
    )

    assert result["written_pairs"] == [{"champ_a": "Caitlyn", "champ_b": "Samira", "role": "bottom"}]

    with db.connect() as conn:
        bystander_after = conn.execute(
            select(Advice).where(Advice.champ_a == "Briar", Advice.champ_b == "Viego", Advice.role == "jungle")
        ).fetchall()
        bystander_stats_after = conn.execute(
            select(MatchupStat).where(MatchupStat.champ_a == "Briar", MatchupStat.champ_b == "Viego", MatchupStat.role == "jungle")
        ).fetchall()
        target_rows = conn.execute(
            select(Advice).where(Advice.champ_a == "Caitlyn", Advice.champ_b == "Samira", Advice.role == "bottom")
        ).fetchall()

    # Bystander row: same ids, same text -- completely untouched by the
    # scoped regeneration of an unrelated pair.
    assert {r.id for r in bystander_after} == {r.id for r in bystander_before}
    assert sorted(r.text for r in bystander_after) == sorted(r.text for r in bystander_before)
    assert {s.id for s in bystander_stats_after} == {s.id for s in bystander_stats_before}

    # Target row: really regenerated with the new (fake, but real-shaped)
    # text -- proves the forced path did overwrite the intended pair.
    assert len(target_rows) == 3
    for row in target_rows:
        assert row.text in {"play safe.", "regenerated content.", "close it out."}


def test_force_regenerate_never_deletes_a_pair_not_named_in_targets(monkeypatch, db):
    # Same fake model, but this time force_regenerate_pairs is invoked with
    # BYSTANDER's real context present in the `pairs` kwarg alongside
    # TARGET's -- still must not touch BYSTANDER, because it isn't in
    # `targets`. Catches the exact "broad idempotency check" mistake named
    # in phase3-eager-tier-precompute.md: passing extra context/pairs must
    # never regenerate anything beyond `targets`.
    monkeypatch.setattr(precompute, "generate", _fake_generate)
    monkeypatch.setattr(precompute, "load_model_and_tokenizer", lambda adapter_dir: ("fake-model", "fake-tok"))

    _seed_written(db, BYSTANDER, PATCH, "bystander")
    with db.connect() as conn:
        before = conn.execute(select(Advice)).fetchall()
    assert len(before) == 3

    result = force_regenerate_pairs(
        PATCH, targets=[("Caitlyn", "Samira", "bottom")], engine=db, pairs=[TARGET, BYSTANDER],
    )

    # TARGET has no seeded row, so it's a real (delete-nothing, insert-new)
    # regeneration; BYSTANDER must not appear in written_pairs at all even
    # though its context was passed in.
    assert result["written_pairs"] == [{"champ_a": "Caitlyn", "champ_b": "Samira", "role": "bottom"}]

    with db.connect() as conn:
        after = conn.execute(select(Advice).where(Advice.champ_a == "Briar")).fetchall()
    assert len(after) == 3
    assert {r.id for r in after} == {r.id for r in before}


def _fake_generate_hallucinated(model, tokenizer, prompt, max_new_tokens, **kw):
    # No "Late:" label -> split_into_sections returns None -> fails the
    # check. Mirrors the real Briar/Viego run this session: a deterministic
    # grounding/split failure unrelated to markup.
    return "Early:\nfoo.\n\nMid:\nbar."


def test_force_regenerate_leaves_targets_own_row_untouched_on_failed_check(monkeypatch, db):
    # Real bug found and fixed this session: deleting the target row before
    # checking whether the new generation actually passes destroyed the
    # only copy of a pair's advice when regeneration failed. This proves
    # the fix: a failed check must never delete the pair's existing rows.
    monkeypatch.setattr(precompute, "generate", _fake_generate)
    monkeypatch.setattr(precompute, "load_model_and_tokenizer", lambda adapter_dir: ("fake-model", "fake-tok"))
    _seed_written(db, TARGET, PATCH, "target")

    monkeypatch.setattr(precompute, "generate", _fake_generate_hallucinated)
    result = force_regenerate_pairs(
        PATCH, targets=[("Caitlyn", "Samira", "bottom")], engine=db, pairs=[TARGET],
    )

    assert result["written_pairs"] == []
    assert result["skipped"][0]["reason"] == "could_not_split_sections"

    with db.connect() as conn:
        rows = conn.execute(
            select(Advice).where(Advice.champ_a == "Caitlyn", Advice.champ_b == "Samira", Advice.role == "bottom")
        ).fetchall()
    assert len(rows) == 3
    assert {r.text for r in rows} == {"play safe.", "regenerated content.", "close it out."}
