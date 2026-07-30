"""Add suggestion_queue_item table

Revision ID: d5f9a2c7e841
Revises: c4d8e6f2a913
Create Date: 2026-07-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5f9a2c7e841'
down_revision = 'c4d8e6f2a913'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('suggestion_queue_item',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('item_type', sa.String(length=20), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('reason', sa.String(length=300), nullable=True),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('snoozed_until', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='fk_suggestion_queue_item_user'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'item_type', 'source_id', name='uq_suggestion_queue_user_item')
    )


def downgrade():
    op.drop_table('suggestion_queue_item')
