import ast
from pathlib import Path
from unittest.mock import patch

import pytest
from datetime import datetime
from freezegun import freeze_time

from app.models import DefaultEventDescriptor, EventCache, User
from app.services.integration_service import integration_service
from app.services.custom_calendar_service import expand_entries_for_year
from app.services.default_event_service import DEFAULT_EVENT_SOURCE
import app.tasks.background_tasks as background_tasks_module
from app.tasks.background_tasks import update_event_cache

pytestmark = pytest.mark.integration

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / 'migrations' / 'versions'
    / '9689d3c383e8_add_default_event_descriptor.py'
)


@pytest.fixture
def kentucky_derby(db_session):
    descriptor = DefaultEventDescriptor(
        title='Kentucky Derby', category='Sports Festival', recurrence='nth_weekday',
        recurrence_params={'month': 5, 'weekday': 5, 'ordinal': 1},
    )
    db_session.add(descriptor)
    db_session.commit()
    return descriptor


def test_update_default_events_saves_subscription_and_populates_cache(client, auth, test_user, kentucky_derby, db_session):
    auth.login()

    with freeze_time("2026-07-30"):
        response = client.post(
            '/settings/update-default-events',
            data={'subscribed_default_events': [str(kentucky_derby.id)]},
        )
        assert response.status_code == 302

    assert test_user.preferences.get('subscribed_default_events') == [kentucky_derby.id]

    cached = EventCache.query.filter_by(user_id=test_user.id, source=DEFAULT_EVENT_SOURCE).all()
    assert {c.year for c in cached} == {2026, 2027}


def test_update_default_events_drops_stale_id_without_erroring(client, auth, test_user, kentucky_derby, db_session):
    auth.login()
    stale_id = kentucky_derby.id + 999

    response = client.post(
        '/settings/update-default-events',
        data={'subscribed_default_events': [str(kentucky_derby.id), str(stale_id)]},
    )
    assert response.status_code == 302

    assert test_user.preferences.get('subscribed_default_events') == [kentucky_derby.id]


def test_update_default_events_empty_selection_clears_subscription_and_cache(client, auth, test_user, kentucky_derby, db_session):
    auth.login()
    client.post('/settings/update-default-events', data={'subscribed_default_events': [str(kentucky_derby.id)]})
    assert EventCache.query.filter_by(user_id=test_user.id, source=DEFAULT_EVENT_SOURCE).count() > 0

    response = client.post('/settings/update-default-events', data={})
    assert response.status_code == 302

    assert test_user.preferences.get('subscribed_default_events') == []
    assert EventCache.query.filter_by(user_id=test_user.id, source=DEFAULT_EVENT_SOURCE).count() == 0


def test_settings_page_lists_catalog_grouped_by_category(client, auth, kentucky_derby):
    auth.login()
    response = client.get('/settings/')
    assert response.status_code == 200
    assert b'Kentucky Derby' in response.data
    assert b'Sports Festival' in response.data


def test_background_job_rolls_subscribed_default_event_forward_into_next_year(app, test_user, kentucky_derby, db_session):
    test_user.update_preferences({'subscribed_default_events': [kentucky_derby.id]})
    db_session.commit()
    user_id = test_user.id

    with patch.object(integration_service, 'fetch_live_calendar_events', return_value=[]):
        with freeze_time("2027-01-01"):
            update_event_cache(app)

    cached_years = {
        c.year for c in EventCache.query.filter_by(user_id=user_id, source=DEFAULT_EVENT_SOURCE).all()
    }
    assert 2028 in cached_years  # rolled forward without the user re-saving anything


def test_background_job_skips_users_with_no_subscription(app, test_user, kentucky_derby, db_session):
    user_id = test_user.id  # test_user.preferences never touched -- no subscription

    with patch.object(integration_service, 'fetch_live_calendar_events', return_value=[]):
        update_event_cache(app)

    assert EventCache.query.filter_by(user_id=user_id, source=DEFAULT_EVENT_SOURCE).count() == 0


def test_background_job_one_users_failure_does_not_block_another(app, test_user, kentucky_derby, db_session):
    """Asserts on which users regenerate_event_cache_for_user_default_events
    got *called* for, rather than on EventCache rows actually persisting --
    the production code's except branch calls db.session.rollback() for the
    failing user, and this test's db_session fixture wraps the whole test
    in one savepoint-based transaction, where a mid-test rollback can undo
    earlier commits in that same transaction (the kentucky_derby fixture
    row, other_user, their preference writes) well beyond what a real
    ROLLBACK would affect in a genuinely running app. Checking call
    arguments instead of DB side effects tests the actual contract (the
    loop doesn't stop after one user's failure) without depending on data
    surviving a rollback this test fixture doesn't isolate the same way
    production does.
    """
    other_user = User(username='other_user', email='other@example.com')
    other_user.set_password('password')
    db_session.add(other_user)
    db_session.commit()

    test_user.update_preferences({'subscribed_default_events': [kentucky_derby.id]})
    other_user.update_preferences({'subscribed_default_events': [kentucky_derby.id]})
    db_session.commit()
    failing_user_id = test_user.id
    other_user_id = other_user.id

    processed_user_ids = []

    def flaky_regenerate(user_id, subscribed_ids, years):
        processed_user_ids.append(user_id)
        if user_id == failing_user_id:
            raise RuntimeError("boom")

    with patch.object(integration_service, 'fetch_live_calendar_events', return_value=[]):
        with patch.object(background_tasks_module, 'regenerate_event_cache_for_user_default_events', side_effect=flaky_regenerate):
            update_event_cache(app)

    assert failing_user_id in processed_user_ids
    assert other_user_id in processed_user_ids  # loop reached the next user despite the first one's failure


def _seeded_default_event_rows():
    """Statically extract the row dicts from the migration's
    op.bulk_insert(...) call -- same static-parsing approach as
    test_migration_table_names.py, since this sandbox can't run the
    migration. created_at/updated_at reference a `now` variable (not a
    literal), so those two keys are dropped per row rather than failing
    the whole parse."""
    tree = ast.parse(MIGRATION_PATH.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'bulk_insert':
            rows = []
            for dict_node in node.args[1].elts:
                row = {}
                for key_node, value_node in zip(dict_node.keys, dict_node.values):
                    key = ast.literal_eval(key_node)
                    try:
                        row[key] = ast.literal_eval(value_node)
                    except ValueError:
                        pass  # non-literal (e.g. `now`) -- not needed here
                rows.append(row)
            return rows
    raise AssertionError('Could not find an op.bulk_insert(...) call in the migration')


def test_seeded_kentucky_derby_row_expands_to_the_real_known_date():
    """Guards the migration's actual literal seed values, not a hand-copied
    duplicate of them -- a future edit to the seeded recurrence_params that
    breaks the real-world date would be caught here."""
    rows = _seeded_default_event_rows()
    derby = next(r for r in rows if r['title'] == 'Kentucky Derby')
    params = derby['recurrence_params']

    entry = {
        'title': derby['title'], 'recurrence': derby['recurrence'],
        'month': params.get('month'), 'day': params.get('day'),
        'weekday': params.get('weekday'), 'ordinal': params.get('ordinal'),
        'interval_years': params.get('interval_years'), 'anchor_year': params.get('anchor_year'),
        'year': None, 'description': derby.get('description'), 'location': derby.get('location'),
    }
    occurrence = expand_entries_for_year([entry], 2024)[0]
    assert occurrence['date'] == datetime(2024, 5, 4)  # the real 2024 Kentucky Derby date
