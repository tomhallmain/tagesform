"""Add entity_comment table

Revision ID: a3f7c9d1e246
Revises: 6d2f7b8dce27
Create Date: 2026-07-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f7c9d1e246'
down_revision = '6d2f7b8dce27'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('entity_comment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['entity_id'], ['entity.id'], name='fk_entity_comment_entity'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='fk_entity_comment_user'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('entity_id', 'user_id', name='uq_entity_comment_entity_user')
    )


def downgrade():
    op.drop_table('entity_comment')
