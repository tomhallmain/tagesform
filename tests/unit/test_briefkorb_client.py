import pytest
from unittest.mock import MagicMock, patch

from app.services import briefkorb_client
from app.services.briefkorb_client import BriefKorbClientError, fetch_unread_messages

pytestmark = pytest.mark.unit


def _configure(monkeypatch, base_url='https://briefkorb.example.com', token='test-token'):
    monkeypatch.setattr(briefkorb_client.config, 'BRIEFKORB_BASE_URL', base_url)
    monkeypatch.setattr(briefkorb_client.config, 'BRIEFKORB_API_TOKEN', token)


def _fake_response(payload, status_code=200):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.content = b'{}'
    mock_response.json.return_value = payload
    if status_code >= 400 and status_code not in (502, 503):
        import requests
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError('error')
    else:
        mock_response.raise_for_status.return_value = None
    return mock_response


def test_fetch_unread_messages_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(briefkorb_client.config, 'BRIEFKORB_BASE_URL', '')
    monkeypatch.setattr(briefkorb_client.config, 'BRIEFKORB_API_TOKEN', '')

    with pytest.raises(BriefKorbClientError):
        fetch_unread_messages()


def test_fetch_unread_messages_sends_bearer_auth_header_and_timeout(monkeypatch):
    _configure(monkeypatch)

    with patch.object(briefkorb_client.requests, 'get',
                       return_value=_fake_response({'messages': []})) as mock_get:
        fetch_unread_messages()

    assert mock_get.call_args.kwargs['headers']['Authorization'] == 'Bearer test-token'
    assert mock_get.call_args.kwargs.get('timeout') is not None


def test_fetch_unread_messages_requests_unread_only_and_leaves_high_impact_only_false(monkeypatch):
    """high_impact_only is deliberately left false server-side -- filtering
    server-side would also drop 'unclassified' senders, which
    suggestion_queue_service._email_candidates wants to keep. See
    docs/task-email-integration.md."""
    _configure(monkeypatch)

    with patch.object(briefkorb_client.requests, 'get',
                       return_value=_fake_response({'messages': []})) as mock_get:
        fetch_unread_messages()

    params = mock_get.call_args.kwargs['params']
    assert params['unread_only'] == 'true'
    assert params['high_impact_only'] == 'false'
    assert mock_get.call_args.args[0].endswith('/api/messages')


def test_fetch_unread_messages_parses_sender_bucket_shape(monkeypatch):
    _configure(monkeypatch)
    payload = {
        'messages': [
            {
                'fromName': 'Jane Doe', 'fromAddress': 'jane@example.com', 'subject': 'Re: Invoice',
                'lastReceivedDateTime': '2026-08-03T14:30:00Z', 'count': 3, 'provider': 'microsoft',
                'impact': 'high-impact', 'genericInferenceScore': 0.9,
                'messages': [{'id': '1', 'subject': 'Re: Invoice', 'lastReceivedDateTime': '2026-08-03T14:30:00Z', 'isRead': False}],
            },
        ],
    }

    with patch.object(briefkorb_client.requests, 'get', return_value=_fake_response(payload)):
        buckets = fetch_unread_messages()

    assert len(buckets) == 1
    bucket = buckets[0]
    assert bucket['sender_address'] == 'jane@example.com'
    assert bucket['sender_name'] == 'Jane Doe'
    assert bucket['provider'] == 'microsoft'
    assert bucket['count'] == 3
    assert bucket['impact'] == 'high-impact'
    assert bucket['impact_score'] == 0.9
    assert bucket['last_received_at'].year == 2026


def test_fetch_unread_messages_raises_on_503(monkeypatch):
    """503 is BriefKorb's documented config/provider-auth failure shape."""
    _configure(monkeypatch)
    with patch.object(briefkorb_client.requests, 'get',
                       return_value=_fake_response({'error': 'not configured'}, status_code=503)):
        with pytest.raises(BriefKorbClientError):
            fetch_unread_messages()


def test_fetch_unread_messages_raises_on_401(monkeypatch):
    _configure(monkeypatch)
    with patch.object(briefkorb_client.requests, 'get',
                       return_value=_fake_response({'error': 'Unauthorized'}, status_code=401)):
        with pytest.raises(BriefKorbClientError):
            fetch_unread_messages()
