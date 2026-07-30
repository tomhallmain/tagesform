"""Add entity calendar support

Revision ID: c4d8e6f2a913
Revises: b7e1f4a9c352
Create Date: 2026-07-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d8e6f2a913'
down_revision = 'b7e1f4a9c352'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('entity', schema=None) as batch_op:
        batch_op.add_column(sa.Column('calendar_entries', sa.JSON(), nullable=True))

    with op.batch_alter_table('event_cache', schema=None) as batch_op:
        batch_op.add_column(sa.Column('entity_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_event_cache_entity', 'entity', ['entity_id'], ['id'])


def downgrade():
    with op.batch_alter_table('event_cache', schema=None) as batch_op:
        batch_op.drop_constraint('fk_event_cache_entity', type_='foreignkey')
        batch_op.drop_column('entity_id')

    with op.batch_alter_table('entity', schema=None) as batch_op:
        batch_op.drop_column('calendar_entries')
