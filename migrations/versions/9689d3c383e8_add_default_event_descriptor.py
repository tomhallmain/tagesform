"""Add default event descriptor catalog

Revision ID: 9689d3c383e8
Revises: a7c3e9f21b04
Create Date: 2026-08-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '9689d3c383e8'
down_revision = 'a7c3e9f21b04'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('default_event_descriptor',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=False),
    sa.Column('recurrence', sa.String(length=30), nullable=False),
    sa.Column('recurrence_params', sa.JSON(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('location', sa.String(length=200), nullable=True),
    sa.Column('source_url', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )

    # Seed exactly one well-established, high-confidence example to prove
    # the mechanism end-to-end. Most catalog candidates (e.g. America's Cup,
    # RoboGames, Lockn, Scamp) carry no fixed date rule and can't be
    # responsibly auto-seeded; broader catalog population is a follow-up,
    # not part of this migration. The Kentucky Derby's "first Saturday in
    # May" is long-established public fact.
    default_event_descriptor = sa.table('default_event_descriptor',
        sa.column('title', sa.String),
        sa.column('category', sa.String),
        sa.column('recurrence', sa.String),
        sa.column('recurrence_params', sa.JSON),
        sa.column('description', sa.Text),
        sa.column('location', sa.String),
        sa.column('source_url', sa.String),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    now = datetime.utcnow()
    op.bulk_insert(default_event_descriptor, [{
        'title': 'Kentucky Derby',
        'category': 'Sports Festival',
        'recurrence': 'nth_weekday',
        'recurrence_params': {'month': 5, 'weekday': 5, 'ordinal': 1},
        'description': None,
        'location': 'Churchill Downs, Louisville, Kentucky',
        'source_url': 'https://www.kentuckyderby.com/',
        'created_at': now,
        'updated_at': now,
    }])


def downgrade():
    op.drop_table('default_event_descriptor')
