import pytest
from app.models import Entity, db

pytestmark = pytest.mark.unit


def test_entity_defaults_to_public_when_not_specified(app, test_user, db_session):
    """Entity.is_public should default to True when not explicitly set --
    relied on by paths that construct an Entity without a visibility field,
    e.g. CSV import (Entity(**place) in app/routes/entities.py)."""
    with app.app_context():
        entity = Entity(name='Imported Place', category='restaurant', user_id=test_user.id)
        db_session.add(entity)
        db_session.commit()

        db_session.refresh(entity)
        assert entity.is_public is True
