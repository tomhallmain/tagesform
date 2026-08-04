"""Regression guard for a real production bug: BriefKorbMessageCache had no
__tablename__, so SQLAlchemy derived 'brief_korb_message_cache' (splitting
the compound name "BriefKorb" into two words, since there's no way for it
to know that's one name), while the migration that actually created the
table (f1a2b3c4d5e6_add_mustermeister_briefkorb_cache.py) used the literal
string 'briefkorb_message_cache'. Every query against that model failed at
runtime with "no such table: brief_korb_message_cache" -- the table
SQLAlchemy looked for was never the one that got created.

Every other fixture in this suite (`app`, `db_session`) builds its schema
via db.create_all() straight from model metadata, which is self-consistent
by construction and can never catch this class of bug -- it doesn't touch
the migration files at all. This test does, statically (parsing
op.create_table(...) calls rather than actually running `flask db
upgrade`, since this sandbox can't execute the app -- see CLAUDE.md).
"""
import re
from pathlib import Path

import pytest

from app.models import db

pytestmark = pytest.mark.unit

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / 'migrations' / 'versions'


def _tables_created_by_migrations():
    created = set()
    for path in MIGRATIONS_DIR.glob('*.py'):
        text = path.read_text(encoding='utf-8')
        created.update(re.findall(r"op\.create_table\(\s*'([^']+)'", text))
    return created


def test_every_model_tablename_matches_a_table_a_migration_actually_creates(app):
    """`app` is pulled in only to force create_app() to run at least once --
    that's what imports every blueprint (and, with it, models defined
    outside app/models/, e.g. ImportData in app/routes/entities.py) so
    db.metadata is fully populated before this test inspects it."""
    migrated_tables = _tables_created_by_migrations()
    model_tables = set(db.metadata.tables.keys())

    missing = model_tables - migrated_tables
    assert not missing, (
        f"Model(s) declare a table with no matching migrations/versions/*.py "
        f"op.create_table(...) call: {missing}. Likely a missing __tablename__ "
        f"override, or a migration using a different literal table name than "
        f"SQLAlchemy's default derivation for that model's class name."
    )
