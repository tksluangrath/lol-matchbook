"""
Integration test: app.db_migrate.migrate() creates every table/column from
app.models.Base against a real pgserver instance (docs/decisions/
phase0-pgserver-spike.md's validated start/stop method), not a mock.

EXPECTED_COLUMNS below is transcribed by hand from backend/app/models.py
(AGENT-7's finalized schema, read directly, not derived by running
db_migrate and copying its own output back in as "expected").
"""
import shutil
import tempfile

import pytest
from sqlalchemy import inspect

from app.db_migrate import migrate
from app.models import Base

EXPECTED_COLUMNS = {
    "matchup_stats": {
        "id",
        "champ_a",
        "champ_b",
        "role",
        "rank_bracket",
        "phase",
        "win_rate",
        "sample_size",
        "patch",
    },
    "advice": {
        "id",
        "champ_a",
        "champ_b",
        "role",
        "rank_bracket",
        "phase",
        "text",
        "fact_source_id",
        "patch",
        "is_abstention",
        "tier",
        "generated_at",
    },
    "backfill_queue": {
        "id",
        "champ_a",
        "champ_b",
        "rank_bracket",
        "phase",
        "requested_at",
        "status",
    },
    "reports": {
        "id",
        "category",
        "message",
        "champ_a",
        "champ_b",
        "role",
        "rank_bracket",
        "created_at",
    },
}


@pytest.fixture(scope="module")
def migrated_db():
    pgdata = tempfile.mkdtemp(prefix="db_migrate_test_")
    server, engine = migrate(pgdata=pgdata)
    try:
        yield engine
    finally:
        engine.dispose()
        server.cleanup()
        shutil.rmtree(pgdata, ignore_errors=True)


def test_all_expected_tables_exist(migrated_db):
    inspector = inspect(migrated_db)
    tables = set(inspector.get_table_names())
    assert set(EXPECTED_COLUMNS.keys()) <= tables


@pytest.mark.parametrize("table_name", sorted(EXPECTED_COLUMNS.keys()))
def test_table_has_expected_columns(migrated_db, table_name):
    inspector = inspect(migrated_db)
    actual = {c["name"] for c in inspector.get_columns(table_name)}
    assert EXPECTED_COLUMNS[table_name] <= actual


def test_advice_tier_check_constraint_rejects_invalid_value(migrated_db):
    # models.py declares CheckConstraint("tier IN ('eager','lazy')") on
    # advice -- confirm the real DB actually enforces it, not just that
    # SQLAlchemy's Python-side model declares it.
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with migrated_db.connect() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO advice "
                    "(champ_a, champ_b, role, rank_bracket, phase, text, "
                    "patch, tier) VALUES "
                    "('Ashe', 'Zed', 'BOTTOM', 'GOLD', 'early', 'x', "
                    "'16.15.1', 'not_a_real_tier')"
                )
            )
            conn.commit()


def test_migrate_is_idempotent_rerun(migrated_db):
    # Re-running create_all against a DB that already has the tables must
    # not error (create_all only adds missing tables/skips existing ones).
    Base.metadata.create_all(migrated_db)
    inspector = inspect(migrated_db)
    assert "advice" in inspector.get_table_names()
