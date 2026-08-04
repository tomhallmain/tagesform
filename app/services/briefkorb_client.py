"""Thin client for BriefKorb's external messages API.

See docs/task-email-integration.md for the confirmed current API shape.
`GET /api/messages`, bearer-token auth against BriefKorb's own
email_server/config.yaml `external_api.tokens` list. Errors are raised, not
swallowed -- callers (background jobs) are responsible for catching,
logging, and rolling back, same convention as every other per-source job in
app/tasks/background_tasks.py.

Every call is one or more live Microsoft Graph/Gmail fetches on BriefKorb's
own end (per that endpoint's own docstring) -- not a cheap query. Callers
should poll on the order of hours (see config.BRIEFKORB_POLL_INTERVAL), not
per-request.
"""
from dateutil import parser as date_parser

import requests

from ..utils.config import config
from ..utils.logging_setup import get_logger

logger = get_logger('briefkorb_client')

REQUEST_TIMEOUT_SECONDS = 60  # live provider fetch on BriefKorb's end, not a local query


class BriefKorbClientError(Exception):
    """Raised on any BriefKorb API failure (network, auth, unexpected shape)."""
    pass


def _auth_headers():
    return {'Authorization': f'Bearer {config.BRIEFKORB_API_TOKEN}'}


def fetch_unread_messages():
    """Fetch every unread-mail sender bucket across every provider BriefKorb
    has an authenticated mailbox for.

    unread_only defaults true server-side; high_impact_only is deliberately
    left false here so 'unclassified' senders (no established pattern yet,
    but not necessarily unimportant) aren't dropped before Tagesform's own
    scoring gets a look -- see suggestion_queue_service._email_candidates.

    Returns a list of dicts: {sender_address, provider, sender_name,
    subject, last_received_at (datetime), count, impact, impact_score}.
    """
    if not config.BRIEFKORB_BASE_URL or not config.BRIEFKORB_API_TOKEN:
        raise BriefKorbClientError('BriefKorb base URL/token not configured')

    url = f"{config.BRIEFKORB_BASE_URL.rstrip('/')}/api/messages"
    params = {'unread_only': 'true', 'high_impact_only': 'false'}

    try:
        response = requests.get(
            url, headers=_auth_headers(), params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.exceptions.RequestException as e:
        raise BriefKorbClientError(f'Request to BriefKorb failed: {e}') from e

    if response.status_code == 401:
        raise BriefKorbClientError('BriefKorb rejected the configured API token (401)')
    if response.status_code in (502, 503):
        # Documented failure modes: 503 = config/provider-auth failure,
        # 502 = exception during the live Graph/Gmail fetch. Both are
        # BriefKorb-side/transient, not a Tagesform bug.
        body = response.json() if response.content else {}
        raise BriefKorbClientError(f"BriefKorb fetch failed ({response.status_code}): {body.get('error')}")
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise BriefKorbClientError(f'BriefKorb returned an error: {e}') from e

    payload = response.json()
    raw_buckets = payload.get('messages', [])

    buckets = []
    for raw in raw_buckets:
        try:
            buckets.append({
                'sender_address': raw['fromAddress'],
                'provider': raw.get('provider') or 'unknown',
                'sender_name': raw.get('fromName'),
                'subject': raw.get('subject'),
                'last_received_at': date_parser.isoparse(raw['lastReceivedDateTime']),
                'count': raw.get('count', 1),
                'impact': raw.get('impact'),
                'impact_score': raw.get('genericInferenceScore'),
            })
        except (KeyError, ValueError) as e:
            logger.error(f'Skipping malformed BriefKorb message bucket {raw!r}: {e}')
    return buckets
