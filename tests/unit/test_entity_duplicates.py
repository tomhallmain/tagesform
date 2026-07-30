import pytest
from app.models import Entity, User

pytestmark = pytest.mark.unit


@pytest.fixture
def other_user(db_session):
    user = User(username='other_user', email='other@example.com')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()
    return user


def test_find_duplicates_default_scope_is_owner_only(app, test_user, other_user, db_session):
    """Without include_public, matches from other users (even public ones)
    must never be returned -- only the given user's own places."""
    with app.app_context():
        other_public = Entity(name='Cafe Central', category='cafe', location='1 Main St',
                               is_public=True, user_id=other_user.id)
        db_session.add(other_public)
        db_session.commit()

        matches = Entity.find_duplicates(
            name='Cafe Central', category='cafe', location='1 Main St', user_id=test_user.id
        )
        assert matches == []


def test_find_duplicates_include_public_finds_other_users_public_places(app, test_user, other_user, db_session):
    """With include_public=True, another user's public place with a matching
    name/category/location must be returned."""
    with app.app_context():
        other_public = Entity(name='Cafe Central', category='cafe', location='1 Main St',
                               is_public=True, user_id=other_user.id)
        db_session.add(other_public)
        db_session.commit()

        matches = Entity.find_duplicates(
            name='Cafe Central', category='cafe', location='1 Main St',
            user_id=test_user.id, include_public=True
        )
        assert len(matches) == 1
        assert matches[0]['name'] == 'Cafe Central'


def test_find_duplicates_include_public_ignores_other_users_private_places(app, test_user, other_user, db_session):
    """With include_public=True, another user's *private* place must still
    never match -- only that user's public places are in scope."""
    with app.app_context():
        other_private = Entity(name='Cafe Central', category='cafe', location='1 Main St',
                                is_public=False, user_id=other_user.id)
        db_session.add(other_private)
        db_session.commit()

        matches = Entity.find_duplicates(
            name='Cafe Central', category='cafe', location='1 Main St',
            user_id=test_user.id, include_public=True
        )
        assert matches == []


def test_find_duplicates_include_public_still_finds_owners_own_places(app, test_user, other_user, db_session):
    """include_public widens the scope, it doesn't narrow it -- the user's
    own (private) places must still match regardless."""
    with app.app_context():
        own_place = Entity(name='Cafe Central', category='cafe', location='1 Main St',
                            is_public=False, user_id=test_user.id)
        db_session.add(own_place)
        db_session.commit()

        matches = Entity.find_duplicates(
            name='Cafe Central', category='cafe', location='1 Main St',
            user_id=test_user.id, include_public=True
        )
        assert len(matches) == 1
        assert matches[0]['name'] == 'Cafe Central'


def test_find_duplicates_exclude_id_omits_the_given_entity(app, test_user, db_session):
    """exclude_id must omit that specific entity from the results -- needed
    when checking an entity being edited against everything *except itself*."""
    with app.app_context():
        place = Entity(name='Cafe Central', category='cafe', location='1 Main St',
                        is_public=False, user_id=test_user.id)
        db_session.add(place)
        db_session.commit()

        matches = Entity.find_duplicates(
            name='Cafe Central', category='cafe', location='1 Main St',
            user_id=test_user.id, exclude_id=place.id
        )
        assert matches == []

        # Sanity check: without exclude_id, the entity does match itself.
        matches = Entity.find_duplicates(
            name='Cafe Central', category='cafe', location='1 Main St',
            user_id=test_user.id
        )
        assert len(matches) == 1
