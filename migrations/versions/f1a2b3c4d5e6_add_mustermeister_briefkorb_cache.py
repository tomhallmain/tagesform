"""Add mustermeister_task_cache and briefkorb_message_cache tables

Revision ID: f1a2b3c4d5e6
Revises: d5f9a2c7e841
Create Date: 2026-08-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'd5f9a2c7e841'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mustermeister_task_cache',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('external_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('completed', sa.Boolean(), nullable=True),
    sa.Column('priority', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=100), nullable=True),
    sa.Column('project', sa.String(length=200), nullable=True),
    sa.Column('updated_date', sa.Date(), nullable=True),
    sa.Column('fetched_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('external_id')
    )

    op.create_table('briefkorb_message_cache',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sender_address', sa.String(length=320), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('sender_name', sa.String(length=200), nullable=True),
    sa.Column('subject', sa.String(length=500), nullable=True),
    sa.Column('last_received_at', sa.DateTime(), nullable=False),
    sa.Column('count', sa.Integer(), nullable=True),
    sa.Column('impact', sa.String(length=20), nullable=True),
    sa.Column('impact_score', sa.Float(), nullable=True),
    sa.Column('fetched_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('sender_address', 'provider', name='uq_briefkorb_sender_provider')
    )


def downgrade():
    op.drop_table('briefkorb_message_cache')
    op.drop_table('mustermeister_task_cache')
