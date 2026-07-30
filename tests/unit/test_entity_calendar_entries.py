import pytest
from app.models import Entity, db

pytestmark = pytest.mark.unit


@pytest.fixture
def entity(app, test_user, db_session):
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()
    return place


def test_get_calendar_entries_defaults_to_empty_list(app, entity):
    with app.app_context():
        assert entity.get_calendar_entries() == []


def test_add_calendar_entry_appends_and_persists(app, entity, db_session):
    with app.app_context():
        entry = {'id': 'abc123', 'title': 'Closed for holidays', 'recurrence': 'once', 'date': '2026-12-25'}
        entity.add_calendar_entry(entry)

        db_session.refresh(entity)
        assert entity.get_calendar_entries() == [entry]


def test_add_calendar_entry_does_not_clobber_existing_entries(app, entity, db_session):
    with app.app_context():
        first = {'id': 'a', 'title': 'First', 'recurrence': 'once', 'date': '2026-01-01'}
        second = {'id': 'b', 'title': 'Second', 'recurrence': 'once', 'date': '2026-02-01'}
        entity.add_calendar_entry(first)
        entity.add_calendar_entry(second)

        db_session.refresh(entity)
        assert entity.get_calendar_entries() == [first, second]


def test_update_calendar_entry_replaces_matching_entry(app, entity, db_session):
    with app.app_context():
        original = {'id': 'a', 'title': 'Original', 'recurrence': 'once', 'date': '2026-01-01'}
        entity.add_calendar_entry(original)

        updated = {'id': 'a', 'title': 'Updated', 'recurrence': 'once', 'date': '2026-01-02'}
        result = entity.update_calendar_entry('a', updated)

        db_session.refresh(entity)
        assert result == updated
        assert entity.get_calendar_entries() == [updated]


def test_update_calendar_entry_returns_none_for_unknown_id(app, entity):
    with app.app_context():
        assert entity.update_calendar_entry('does-not-exist', {'id': 'does-not-exist'}) is None


def test_remove_calendar_entry_removes_matching_entry_only(app, entity, db_session):
    with app.app_context():
        keep = {'id': 'keep', 'title': 'Keep', 'recurrence': 'once', 'date': '2026-01-01'}
        remove = {'id': 'remove', 'title': 'Remove', 'recurrence': 'once', 'date': '2026-02-01'}
        entity.add_calendar_entry(keep)
        entity.add_calendar_entry(remove)

        removed = entity.remove_calendar_entry('remove')

        db_session.refresh(entity)
        assert removed is True
        assert entity.get_calendar_entries() == [keep]


def test_remove_calendar_entry_returns_false_for_unknown_id(app, entity):
    with app.app_context():
        assert entity.remove_calendar_entry('does-not-exist') is False
