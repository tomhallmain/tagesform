import pytest
from datetime import date, datetime
from unittest.mock import patch

from app.models import BriefKorbMessageCache, MustermeisterTaskCache
from app.tasks import background_tasks

pytestmark = pytest.mark.integration


def _configure_mustermeister(monkeypatch):
    monkeypatch.setattr(background_tasks.config, 'MUSTERMEISTER_BASE_URL', 'https://mustermeister.example.com')
    monkeypatch.setattr(background_tasks.config, 'MUSTERMEISTER_API_TOKEN', 'test-token')


def _configure_briefkorb(monkeypatch):
    monkeypatch.setattr(background_tasks.config, 'BRIEFKORB_BASE_URL', 'https://briefkorb.example.com')
    monkeypatch.setattr(background_tasks.config, 'BRIEFKORB_API_TOKEN', 'test-token')


def _fake_task(external_id, title='Task', due_date=None, priority='medium'):
    return {
        'external_id': external_id, 'title': title, 'description': None, 'due_date': due_date,
        'completed': False, 'priority': priority, 'status': 'Todo', 'project': 'Website',
        'updated_date': date(2026, 8, 1),
    }


def _fake_bucket(sender_address, provider='microsoft', impact='high-impact'):
    return {
        'sender_address': sender_address, 'provider': provider, 'sender_name': 'Sender',
        'subject': 'Subject', 'last_received_at': datetime(2026, 8, 1, 12, 0, 0), 'count': 1,
        'impact': impact, 'impact_score': 0.7,
    }


def test_refresh_mustermeister_tasks_is_a_noop_when_unconfigured(app, db_session, monkeypatch):
    monkeypatch.setattr(background_tasks.config, 'MUSTERMEISTER_BASE_URL', '')
    monkeypatch.setattr(background_tasks.config, 'MUSTERMEISTER_API_TOKEN', '')

    with patch.object(background_tasks.mustermeister_client, 'fetch_open_tasks') as mock_fetch:
        background_tasks.refresh_mustermeister_tasks(app)

    mock_fetch.assert_not_called()


def test_refresh_mustermeister_tasks_inserts_new_tasks(app, db_session, monkeypatch):
    _configure_mustermeister(monkeypatch)
    with patch.object(background_tasks.mustermeister_client, 'fetch_open_tasks',
                       return_value=[_fake_task(1, title='Fix bug')]):
        background_tasks.refresh_mustermeister_tasks(app)

    cached = MustermeisterTaskCache.query.filter_by(external_id=1).first()
    assert cached is not None
    assert cached.title == 'Fix bug'


def test_refresh_mustermeister_tasks_upserts_existing_and_prunes_missing(app, db_session, monkeypatch):
    _configure_mustermeister(monkeypatch)
    with patch.object(background_tasks.mustermeister_client, 'fetch_open_tasks',
                       return_value=[_fake_task(1, title='Old title'), _fake_task(2, title='Stays')]):
        background_tasks.refresh_mustermeister_tasks(app)

    assert MustermeisterTaskCache.query.count() == 2

    # Next poll: task 1 retitled, task 2 no longer returned (completed upstream).
    with patch.object(background_tasks.mustermeister_client, 'fetch_open_tasks',
                       return_value=[_fake_task(1, title='New title')]):
        background_tasks.refresh_mustermeister_tasks(app)

    remaining = MustermeisterTaskCache.query.all()
    assert len(remaining) == 1
    assert remaining[0].external_id == 1
    assert remaining[0].title == 'New title'


def test_refresh_mustermeister_tasks_survives_client_failure(app, db_session, monkeypatch):
    """A fetch failure must not raise out of the job -- background jobs are
    called from an APScheduler interval trigger with no caller to catch it."""
    _configure_mustermeister(monkeypatch)
    with patch.object(background_tasks.mustermeister_client, 'fetch_open_tasks',
                       side_effect=Exception('boom')):
        background_tasks.refresh_mustermeister_tasks(app)  # must not raise


def test_refresh_briefkorb_messages_is_a_noop_when_unconfigured(app, db_session, monkeypatch):
    monkeypatch.setattr(background_tasks.config, 'BRIEFKORB_BASE_URL', '')
    monkeypatch.setattr(background_tasks.config, 'BRIEFKORB_API_TOKEN', '')

    with patch.object(background_tasks.briefkorb_client, 'fetch_unread_messages') as mock_fetch:
        background_tasks.refresh_briefkorb_messages(app)

    mock_fetch.assert_not_called()


def test_refresh_briefkorb_messages_upserts_by_sender_and_provider_and_prunes_missing(app, db_session, monkeypatch):
    _configure_briefkorb(monkeypatch)
    with patch.object(background_tasks.briefkorb_client, 'fetch_unread_messages',
                       return_value=[_fake_bucket('a@example.com'), _fake_bucket('b@example.com')]):
        background_tasks.refresh_briefkorb_messages(app)

    assert BriefKorbMessageCache.query.count() == 2

    # b@example.com read/archived upstream; a@example.com gets a new message count.
    with patch.object(background_tasks.briefkorb_client, 'fetch_unread_messages',
                       return_value=[dict(_fake_bucket('a@example.com'), count=2)]):
        background_tasks.refresh_briefkorb_messages(app)

    remaining = BriefKorbMessageCache.query.all()
    assert len(remaining) == 1
    assert remaining[0].sender_address == 'a@example.com'
    assert remaining[0].count == 2


def test_refresh_briefkorb_messages_treats_same_address_different_provider_as_distinct(app, db_session, monkeypatch):
    _configure_briefkorb(monkeypatch)
    with patch.object(background_tasks.briefkorb_client, 'fetch_unread_messages',
                       return_value=[
                           _fake_bucket('a@example.com', provider='microsoft'),
                           _fake_bucket('a@example.com', provider='gmail'),
                       ]):
        background_tasks.refresh_briefkorb_messages(app)

    assert BriefKorbMessageCache.query.filter_by(sender_address='a@example.com').count() == 2
