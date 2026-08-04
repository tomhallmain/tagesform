"""Thin client for Mustermeister's external task-insights API.

See docs/task-email-integration.md for the confirmed current API shape.
`GET /api/tools/:tool_name`, bearer-token auth against `users.api_token`.
Errors are raised, not swallowed -- callers (background jobs) are
responsible for catching, logging, and rolling back, same convention as
every other per-source job in app/tasks/background_tasks.py.
"""
from datetime import datetime

import requests

from ..utils.config import config
from ..utils.logging_setup import get_logger

logger = get_logger('mustermeister_client')

REQUEST_TIMEOUT_SECONDS = 15

# The only tool that returns the full open-task set in one call -- the
# others are each scoped to a subset (overdue-only, high-priority-only,
# recent-only, keyword search). Passing all four priority values is how
# "give me everything open" is expressed against this API.
ALL_PRIORITIES = ['leisure', 'low', 'medium', 'high']


class MustermeisterClientError(Exception):
    """Raised on any Mustermeister API failure (network, auth, unexpected shape)."""
    pass


def _auth_headers():
    return {'Authorization': f'Bearer {config.MUSTERMEISTER_API_TOKEN}'}


def _parse_date(value):
    """Mustermeister's due_date/updated_date are date-only ISO strings
    (task.due_date&.to_date&.iso8601), never a full timestamp."""
    if not value:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def _flatten_open_tasks_by_priorities(payload):
    """Flatten the open_tasks_by_priorities response's nested
    priorities -> statuses -> projects -> [tasks] shape into a flat list of
    task dicts, with priority/status/project restored onto each one.

    Mustermeister's grouped_list_result strips those three keys from each
    individual task (`task.except(:priority, :status, :project)`) before
    nesting it, since they're already represented by the surrounding
    nesting keys -- the leaf task dicts in this response, unlike every
    other tool on this API, do not carry their own priority/status/project
    fields. They have to be read back off the nesting level they came
    from while flattening, or every task ends up with all three silently
    missing."""
    tasks = []
    priorities = payload.get('priorities') or {}
    for priority, priority_data in priorities.items():
        for status, status_data in (priority_data.get('statuses') or {}).items():
            for project, project_tasks in (status_data.get('projects') or {}).items():
                for task in project_tasks:
                    task = dict(task)
                    task['priority'] = priority
                    task['status'] = status
                    task['project'] = project
                    tasks.append(task)
    return tasks


def fetch_open_tasks():
    """Fetch every open (non-completed) task visible to the configured
    Mustermeister account, across all priorities.

    Returns a list of dicts: {external_id, title, description, due_date
    (date or None), completed, priority, status, project, updated_date
    (date or None)}.
    """
    if not config.MUSTERMEISTER_BASE_URL or not config.MUSTERMEISTER_API_TOKEN:
        raise MustermeisterClientError('Mustermeister base URL/token not configured')

    url = f"{config.MUSTERMEISTER_BASE_URL.rstrip('/')}/api/tools/open_tasks_by_priorities"
    params = [('priorities[]', p) for p in ALL_PRIORITIES]
    params.append(('limit', config.MUSTERMEISTER_TASK_LIMIT))

    try:
        response = requests.get(
            url, headers=_auth_headers(), params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.exceptions.RequestException as e:
        raise MustermeisterClientError(f'Request to Mustermeister failed: {e}') from e

    if response.status_code == 401:
        raise MustermeisterClientError('Mustermeister rejected the configured API token (401)')
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise MustermeisterClientError(f'Mustermeister returned an error: {e}') from e

    payload = response.json()
    raw_tasks = _flatten_open_tasks_by_priorities(payload)

    tasks = []
    for raw in raw_tasks:
        try:
            tasks.append({
                'external_id': raw['id'],
                'title': raw['title'],
                'description': raw.get('description'),
                'due_date': _parse_date(raw.get('due_date')),
                'completed': bool(raw.get('completed', False)),
                'priority': raw.get('priority'),
                'status': raw.get('status'),
                'project': raw.get('project'),
                'updated_date': _parse_date(raw.get('updated_date')),
            })
        except (KeyError, ValueError) as e:
            logger.error(f'Skipping malformed Mustermeister task {raw!r}: {e}')
    return tasks
