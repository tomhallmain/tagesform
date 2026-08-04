"""Add gazetteer_place table and location/coordinate columns on user/entity

Revision ID: a7c3e9f21b04
Revises: f1a2b3c4d5e6
Create Date: 2026-08-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c3e9f21b04'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('gazetteer_place',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('external_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('normalized_name', sa.String(length=200), nullable=False),
    sa.Column('admin_region', sa.String(length=100), nullable=True),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('feature_type', sa.String(length=20), nullable=True),
    sa.Column('population', sa.Integer(), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('external_id')
    )
    op.create_index('ix_gazetteer_place_normalized_name', 'gazetteer_place', ['normalized_name'], unique=False)

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('latitude', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('longitude', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('location_matched_place_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_user_location_matched_place', 'gazetteer_place', ['location_matched_place_id'], ['id']
        )

    with op.batch_alter_table('entity', schema=None) as batch_op:
        batch_op.add_column(sa.Column('latitude', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('longitude', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('location_matched_place_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_entity_location_matched_place', 'gazetteer_place', ['location_matched_place_id'], ['id']
        )


def downgrade():
    with op.batch_alter_table('entity', schema=None) as batch_op:
        batch_op.drop_constraint('fk_entity_location_matched_place', type_='foreignkey')
        batch_op.drop_column('location_matched_place_id')
        batch_op.drop_column('longitude')
        batch_op.drop_column('latitude')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_location_matched_place', type_='foreignkey')
        batch_op.drop_column('location_matched_place_id')
        batch_op.drop_column('longitude')
        batch_op.drop_column('latitude')
        batch_op.drop_column('location')

    op.drop_index('ix_gazetteer_place_normalized_name', table_name='gazetteer_place')
    op.drop_table('gazetteer_place')
