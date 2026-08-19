"""
Unit tests for app.llm.context.build_ask_context.

Real pgserver DB (same fixture pattern as test_forced_regeneration_scope.py)
and real Data Dragon kit-text fetches (same convention as
test_precompute_batch.py -- this project does not mock the Data Dragon
fetch, only the model call). Aatrox/Kayle (top lane) reused as the real
fixture pair already used throughout this project's docs/data.

build_ask_context now returns an AskContext (prompt, grounding_source,
win_rate_pct) instead of a plain string -- a deliberate, real contract
change made alongside the phase4-ask-quality-fix work (docs/decisions/
phase4-ask-quality-fix.md): the grounding_source and win_rate_pct are
needed by routers/ask.py's real fact_grounding_check call, the same check
precompute.py already gates writes on.

Expected values are hand-computed from the real format strings in
app.data_pipeline.precompute.build_pair_with_context and
app.llm.context.NO_DATA_NOTE, not copied from running the implementation.
"""
import shutil
import tempfile

import pytest

from app.db_migrate import migrate
from app.llm.context import NO_DATA_NOTE, NO_STAT_SENTINEL_PCT, build_ask_context
from app.models import Advice, MatchupStat

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


def _seed_advice(engine, champ_a, champ_b, role, rank, texts, is_abstention=0):
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        for phase, text in texts.items():
            session.add(Advice(
                champ_a=champ_a, champ_b=champ_b, role=role, rank_bracket=rank,
                phase=phase, text=text, fact_source_id=None, patch=PATCH,
                is_abstention=is_abstention, tier="eager",
            ))
        session.commit()


def test_build_ask_context_includes_real_stats_block_when_row_present(db):
    _seed_stat(db, "Aatrox", "Kayle", "top", "emerald", "early", 0.50, 4)

    from sqlalchemy.orm import Session
    with Session(db) as session:
        result = build_ask_context(
            session, "Aatrox", "Kayle", "top", "emerald",
            "How do I play the early trade?",
        )

    assert (
        "Context: 4 games observed this patch between Aatrox and Kayle in "
        "the top lane. Aatrox win rate: 50%." in result.prompt
    )
    assert "Aatrox kit:" in result.prompt
    assert "Kayle kit:" in result.prompt
    assert "Aatrox's real abilities:" in result.prompt
    assert "Question: How do I play the early trade?" in result.prompt
    assert NO_DATA_NOTE not in result.prompt
    assert result.win_rate_pct == 50.0


def test_build_ask_context_falls_back_to_no_data_note_when_no_row_at_any_rank(db):
    from sqlalchemy.orm import Session
    with Session(db) as session:
        result = build_ask_context(
            session, "Aatrox", "Kayle", "top", "emerald",
            "What do I do if there's no data?",
        )

    assert NO_DATA_NOTE in result.prompt
    assert "Context:" not in result.prompt  # no fabricated stats sentence
    assert "Aatrox kit:" in result.prompt
    assert "Kayle kit:" in result.prompt
    assert "Question: What do I do if there's no data?" in result.prompt
    assert result.win_rate_pct == NO_STAT_SENTINEL_PCT


def test_build_ask_context_widens_rank_bracket_when_exact_rank_missing(db):
    # Row exists at "emerald" only; request comes in for a different rank
    # string -- same wider-rank-bracket fallback routers/advice.py uses.
    _seed_stat(db, "Aatrox", "Kayle", "top", "emerald", "early", 0.33, 3)

    from sqlalchemy.orm import Session
    with Session(db) as session:
        result = build_ask_context(
            session, "Aatrox", "Kayle", "top", "diamond",
            "Is this matchup winnable?",
        )

    assert (
        "Context: 3 games observed this patch between Aatrox and Kayle in "
        "the top lane. Aatrox win rate: 33%." in result.prompt
    )
    assert NO_DATA_NOTE not in result.prompt


def test_build_ask_context_includes_real_precomputed_advice_as_grounding(db):
    # The real gap this test guards against: /ask previously never queried
    # Advice at all, so the already-generated, already-good precomputed
    # text never reached the model as context.
    _seed_advice(db, "Aatrox", "Kayle", "top", "emerald", {
        "early": "Aatrox should avoid early skirmishes.",
        "mid": "Kayle should look for picks with Radiant Blast.",
        "late": "Kayle should use Divine Judgment to secure a takedown, as Aatrox's reliance on crowd control makes him vulnerable.",
    })

    from sqlalchemy.orm import Session
    with Session(db) as session:
        result = build_ask_context(
            session, "Aatrox", "Kayle", "top", "emerald",
            "How do I win the late game?",
        )

    assert "Precomputed strategic notes" in result.prompt
    assert "Divine Judgment to secure a takedown" in result.prompt
    assert "Divine Judgment to secure a takedown" in result.grounding_source


def test_build_ask_context_omits_precomputed_notes_when_none_exist(db):
    from sqlalchemy.orm import Session
    with Session(db) as session:
        result = build_ask_context(
            session, "Aatrox", "Kayle", "top", "emerald",
            "How do I win the late game?",
        )

    assert "Precomputed strategic notes" not in result.prompt


def test_build_ask_context_omits_precomputed_notes_for_abstention_rows(db):
    # A real champion pair, not the ThinData/Opponent placeholders used
    # elsewhere in this project for DB-only tests: build_ask_context always
    # fetches real Data Dragon kit text regardless of Advice/abstention
    # status, so a fake champion name legitimately 403s here.
    _seed_advice(
        db, "Aatrox", "Kayle", "top", "iron",
        {"early": "", "mid": "", "late": ""},
        is_abstention=1,
    )

    from sqlalchemy.orm import Session
    with Session(db) as session:
        result = build_ask_context(
            session, "Aatrox", "Kayle", "top", "iron",
            "Is this matchup good?",
        )

    assert "Precomputed strategic notes" not in result.prompt


def test_build_ask_context_instruction_asks_for_win_condition_first(db):
    from sqlalchemy.orm import Session
    with Session(db) as session:
        result = build_ask_context(
            session, "Aatrox", "Kayle", "top", "emerald",
            "How do I win the late game?",
        )

    assert "win condition" in result.prompt.lower()
