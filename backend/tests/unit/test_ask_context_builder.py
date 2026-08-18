"""
Unit tests for app.llm.context.build_ask_context, written before the
implementation per this task's instructions.

Real pgserver DB (same fixture pattern as test_forced_regeneration_scope.py)
and real Data Dragon kit-text fetches (same convention as
test_precompute_batch.py -- this project does not mock the Data Dragon
fetch, only the model call). Aatrox/Kayle (top lane) reused as the real
fixture pair already used throughout this project's docs/data.

Expected values are hand-computed from the real format strings in
app.data_pipeline.precompute.build_pair_with_context and
app.llm.context.NO_DATA_NOTE, not copied from running the implementation.
"""
import shutil
import tempfile

import pytest

from app.db_migrate import migrate
from app.llm.context import NO_DATA_NOTE, build_ask_context
from app.models import MatchupStat

PATCH = "16.15.1"


@pytest.fixture
def db():
    pgdata = tempfile.mkdtemp(prefix="ask_context_test_")
    server, engine = migrate(pgdata=pgdata)
    try:
        yield engine
    finally:
        engine.dispose()
        server.cleanup()
        shutil.rmtree(pgdata, ignore_errors=True)


def _seed_stat(engine, champ_a, champ_b, role, rank, phase, win_rate, sample_size):
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        session.add(MatchupStat(
            champ_a=champ_a, champ_b=champ_b, role=role, rank_bracket=rank,
            phase=phase, win_rate=win_rate, sample_size=sample_size, patch=PATCH,
        ))
        session.commit()


def test_build_ask_context_includes_real_stats_block_when_row_present(db):
    _seed_stat(db, "Aatrox", "Kayle", "top", "emerald", "early", 0.50, 4)

    from sqlalchemy.orm import Session
    with Session(db) as session:
        context = build_ask_context(
            session, "Aatrox", "Kayle", "top", "emerald",
            "How do I play the early trade?",
        )

    assert (
        "Context: 4 games observed this patch between Aatrox and Kayle in "
        "the top lane. Aatrox win rate: 50%." in context
    )
    assert "Aatrox kit:" in context
    assert "Kayle kit:" in context
    assert "Aatrox's real abilities:" in context
    assert "Question: How do I play the early trade?" in context
    assert NO_DATA_NOTE not in context


def test_build_ask_context_falls_back_to_no_data_note_when_no_row_at_any_rank(db):
    from sqlalchemy.orm import Session
    with Session(db) as session:
        context = build_ask_context(
            session, "Aatrox", "Kayle", "top", "emerald",
            "What do I do if there's no data?",
        )

    assert NO_DATA_NOTE in context
    assert "Context:" not in context  # no fabricated stats sentence
    assert "Aatrox kit:" in context
    assert "Kayle kit:" in context
    assert "Question: What do I do if there's no data?" in context


def test_build_ask_context_widens_rank_bracket_when_exact_rank_missing(db):
    # Row exists at "emerald" only; request comes in for a different rank
    # string -- same wider-rank-bracket fallback routers/advice.py uses.
    _seed_stat(db, "Aatrox", "Kayle", "top", "emerald", "early", 0.33, 3)

    from sqlalchemy.orm import Session
    with Session(db) as session:
        context = build_ask_context(
            session, "Aatrox", "Kayle", "top", "diamond",
            "Is this matchup winnable?",
        )

    assert (
        "Context: 3 games observed this patch between Aatrox and Kayle in "
        "the top lane. Aatrox win rate: 33%." in context
    )
    assert NO_DATA_NOTE not in context
