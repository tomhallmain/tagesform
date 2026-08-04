from datetime import datetime
from .mixins import db


class MustermeisterTaskCache(db.Model):
    """Local cache of open tasks pulled from the Mustermeister task-manager
    integration (see docs/task-email-integration.md). Populated by
    refresh_mustermeister_tasks -- the suggestion queue's _task_candidates
    reads only this table, never Mustermeister live, so a slow/down
    Mustermeister instance can't block a suggestion-queue refresh.

    Single-integration-owner: no user_id column. Visibility into the
    suggestion queue is gated by config.TASK_EMAIL_INTEGRATION_USER_ID in
    suggestion_queue_service, not by row ownership.
    """
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.Integer, nullable=False, unique=True)  # Mustermeister's task.id
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)          # already truncated to 500 chars server-side
    due_date = db.Column(db.Date)              # date-only; API omits the key entirely when unset
    completed = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(20))        # leisure | low | medium | high
    status = db.Column(db.String(100))         # Mustermeister's status name (no status_id available)
    project = db.Column(db.String(200))        # Mustermeister's project title (no project_id available)
    updated_date = db.Column(db.Date)          # Mustermeister's own updated_at, date-only
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'external_id': self.external_id,
            'title': self.title,
            'description': self.description,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'completed': self.completed,
            'priority': self.priority,
            'status': self.status,
            'project': self.project,
            'updated_date': self.updated_date.isoformat() if self.updated_date else None,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
        }
