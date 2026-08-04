import pytest
from unittest.mock import MagicMock, patch

from app.services import mustermeister_client
from app.services.mustermeister_client import MustermeisterClientError, fetch_open_tasks

pytestmark = pytest.mark.unit


def _configure(monkeypatch, base_url='https://mustermeister.example.com', token='test-token'):
    monkeypatch.setattr(mustermeister_client.config, 'MUSTERMEISTER_BASE_URL', base_url)
    monkeypatch.setattr(mustermeister_client.config, 'MUSTERMEISTER_API_TOKEN', token)
    monkeypatch.setattr(mustermeister_client.config, 'MUSTERMEISTER_TASK_LIMIT', 500)


def _fake_response(payload, status_code=200):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = payload
    if status_code >= 400:
        import requests
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError('error')
    else:
        mock_response.raise_for_status.return_value = None
    return mock_response


def test_fetch_open_tasks_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(mustermeister_client.config, 'MUSTERMEISTER_BASE_URL', '')
    monkeypatch.setattr(mustermeister_client.config, 'MUSTERMEISTER_API_TOKEN', '')

    with pytest.raises(MustermeisterClientError):
        fetch_open_tasks()


def test_fetch_open_tasks_sends_bearer_auth_header_and_timeout(monkeypatch):
    _configure(monkeypatch)
    empty_payload = {'priorities': {}, 'returned_count': 0, 'total_matching_count': 0, 'limit': 500}

    with patch.object(mustermeister_client.requests, 'get',
                       return_value=_fake_response(empty_payload)) as mock_get:
        fetch_open_tasks()

    assert mock_get.call_args.kwargs['headers']['Authorization'] == 'Bearer test-token'
    assert mock_get.call_args.kwargs.get('timeout') is not None


def test_fetch_open_tasks_requests_all_four_priorities_and_limit(monkeypatch):
    """open_tasks_by_priorities requires priorities[] -- passing all four
    values is how 'every open task' is expressed against this API (see
    docs/task-email-integration.md)."""
    _configure(monkeypatch)
    empty_payload = {'priorities': {}, 'returned_count': 0, 'total_matching_count': 0, 'limit': 500}

    with patch.object(mustermeister_client.requests, 'get',
                       return_value=_fake_response(empty_payload)) as mock_get:
        fetch_open_tasks()

    params = mock_get.call_args.kwargs['params']
    priority_values = [value for key, value in params if key == 'priorities[]']
    assert set(priority_values) == {'leisure', 'low', 'medium', 'high'}
    assert ('limit', 500) in params
    assert mock_get.call_args.args[0].endswith('/api/tools/open_tasks_by_priorities')


def test_fetch_open_tasks_flattens_nested_priorities_statuses_projects_shape(monkeypatch):
    _configure(monkeypatch)
    payload = {
        'priorities': {
            'high': {
                'statuses': {
                    'In Progress': {
                        'projects': {
                            'Website': [
                                {
                                    'id': 42, 'title': 'Fix bug', 'description': 'desc',
                                    'completed': False, 'priority': 'high', 'status': 'In Progress',
                                    'project': 'Website', 'updated_date': '2026-08-01',
                                    'due_date': '2026-08-05',
                                },
                            ]
                        }
                    }
                }
            },
            'low': {
                'statuses': {
                    'Todo': {
                        'projects': {
                            'Home': [
                                {
                                    'id': 7, 'title': 'Buy milk', 'description': None,
                                    'completed': False, 'priority': 'low', 'status': 'Todo',
                                    'project': 'Home', 'updated_date': '2026-07-30',
                                    # due_date key omitted entirely, matching the real API
                                },
                            ]
                        }
                    }
                }
            },
        },
        'returned_count': 2, 'total_matching_count': 2, 'limit': 500,
    }

    with patch.object(mustermeister_client.requests, 'get', return_value=_fake_response(payload)):
        tasks = fetch_open_tasks()

    by_external_id = {t['external_id']: t for t in tasks}
    assert by_external_id[42]['title'] == 'Fix bug'
    assert by_external_id[42]['due_date'].isoformat() == '2026-08-05'
    assert by_external_id[7]['title'] == 'Buy milk'
    assert by_external_id[7]['due_date'] is None


def test_fetch_open_tasks_raises_on_401(monkeypatch):
    _configure(monkeypatch)
    with patch.object(mustermeister_client.requests, 'get',
                       return_value=_fake_response({'error': 'Unauthorized'}, status_code=401)):
        with pytest.raises(MustermeisterClientError):
            fetch_open_tasks()
