"""
Tests for backend/app/models.py against a REAL pgserver instance (embedded
Postgres), per docs/decisions/phase0-pgserver-spike.md's validated approach:
each test process gets its own pgdata dir and calls pgserver.get_server()
directly (single-process here is fine -- the spike's "fresh subprocess"
requirement was specifically for testing pgserver's own crash-recovery
behavior across process boundaries, which this file isn't re-testing; it's
using pgserver as a plain fixture, matching the spike's Scenario 1/2 shape).

Requires the Python <=3.12 environment noted in the spike doc (pgserver has
no 3.9-3.12... no 3.13 wheel). Run with:
    backend/.venv312/bin/python -m pytest backend/tests/unit/test_models.py -v
"""
import shutil
import tempfile

import pgserver
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import Advice, Base, BackfillQueue, MatchupStat


@pytest.fixture(scope="module")
def db_session():
    pgdata = tempfile.mkdtemp(prefix="test_models_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="stop")
    try:
        # psycopg (v3) driver, per requirements.txt; pgserver's URI is a bare
        # postgresql:// DSN so swap the dialect prefix for SQLAlchemy.
        uri = srv.get_uri().replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_engine(uri)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    finally:
        srv.cleanup()
        shutil.rmtree(pgdata, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_tables(db_session):
    """Each test starts with empty tables -- avoids cross-test interference
    within the module-scoped server/session."""
    yield
    db_session.rollback()
    for model in (MatchupStat, Advice, BackfillQueue):
        db_session.query(model).delete()
    db_session.commit()


def test_matchup_stat_duplicate_key_raises(db_session):
    """Duplicate insert on the (champ_a, champ_b, role, rank_bracket, phase,
    patch) identity key must be rejected by the DB, per phase0-role-scoping.md
    section 5's recommendation that this be the matchup identity."""
    row_kwargs = dict(
        champ_a="Darius",
        champ_b="Garen",
        role="TOP",
        rank_bracket="GOLD",
        phase="early",
        win_rate=0.52,
        sample_size=100,
        patch="16.15.1",
    )
    db_session.add(MatchupStat(**row_kwargs))
    db_session.commit()

    db_session.add(MatchupStat(**row_kwargs))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_matchup_stat_same_pair_different_role_is_not_a_duplicate(db_session):
    """Role is part of the identity key, not a fixed champion attribute --
    the same champ_a/champ_b pair must be insertable twice under different
    roles (e.g. a flex pick), per phase0-role-scoping.md section 2's
    Ashe (Bottom + Support) example."""
    common = dict(
        champ_a="Yone",
        champ_b="Zed",
        rank_bracket="DIAMOND",
        phase="mid",
        win_rate=0.5,
        sample_size=50,
        patch="16.15.1",
    )
    db_session.add(MatchupStat(role="TOP", **common))
    db_session.add(MatchupStat(role="MIDDLE", **common))
    db_session.commit()  # must not raise

    rows = (
        db_session.query(MatchupStat)
        .filter_by(champ_a="Yone", champ_b="Zed")
        .all()
    )
    assert {r.role for r in rows} == {"TOP", "MIDDLE"}


def test_advice_tier_rejects_value_outside_eager_lazy(db_session):
    advice = Advice(
        champ_a="Ashe",
        champ_b="Vayne",
        role="BOTTOM",
        rank_bracket="PLATINUM",
        phase="late",
        text="placeholder",
        patch="16.15.1",
        tier="mediumrare",  # invalid -- only eager|lazy allowed
    )
    db_session.add(advice)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize("valid_tier", ["eager", "lazy"])
def test_advice_tier_accepts_eager_and_lazy(db_session, valid_tier):
    advice = Advice(
        champ_a="Ashe",
        champ_b="Vayne",
        role="BOTTOM",
        rank_bracket="PLATINUM",
        phase="late",
        text="placeholder",
        patch="16.15.1",
        tier=valid_tier,
    )
    db_session.add(advice)
    db_session.commit()  # must not raise

    saved = db_session.query(Advice).filter_by(tier=valid_tier).one()
    assert saved.tier == valid_tier
    assert saved.generated_at is not None


def test_backfill_queue_round_trips_a_row(db_session):
    """Per tiered-fallback-design.md's backfill queue table shape:
    champ_a, champ_b, rank, phase, requested_at, status."""
    row = BackfillQueue(
        champ_a="Kayle",
        champ_b="Fiora",
        rank_bracket="IRON",
        phase="early",
        status="pending",
    )
    db_session.add(row)
    db_session.commit()

    saved = (
        db_session.query(BackfillQueue)
        .filter_by(champ_a="Kayle", champ_b="Fiora")
        .one()
    )
    assert saved.champ_a == "Kayle"
    assert saved.champ_b == "Fiora"
    assert saved.rank_bracket == "IRON"
    assert saved.phase == "early"
    assert saved.status == "pending"
    assert saved.requested_at is not None
    assert saved.id is not None
