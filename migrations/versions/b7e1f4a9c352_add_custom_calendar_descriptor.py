"""Add custom calendar descriptor support

Revision ID: b7e1f4a9c352
Revises: a3f7c9d1e246
Create Date: 2026-07-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7e1f4a9c352'
down_revision = 'a3f7c9d1e246'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('event_cache', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_event_cache_user', 'user', ['user_id'], ['id'])

    op.create_table('user_calendar_descriptor',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('raw_yaml', sa.Text(), nullable=False),
    sa.Column('last_parse_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='fk_user_calendar_descriptor_user'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', name='uq_user_calendar_descriptor_user')
    )


def downgrade():
    op.drop_table('user_calendar_descriptor')

    with op.batch_alter_table('event_cache', schema=None) as batch_op:
        batch_op.drop_constraint('fk_event_cache_user', type_='foreignkey')
        batch_op.drop_column('user_id')
