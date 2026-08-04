from datetime import datetime
from .mixins import db


class BriefKorbMessageCache(db.Model):
    """Local cache of unread-mail sender buckets pulled from the BriefKorb
    email integration (see docs/task-email-integration.md). Populated by
    refresh_briefkorb_messages -- the suggestion queue's _email_candidates
    reads only this table, never BriefKorb live; BriefKorb's own /api/messages
    docstring warns every call is a live Graph/Gmail fetch against its own
    quota, so this cache is what keeps a suggestion-queue refresh cheap.

    No is_read column: BriefKorb's endpoint is queried with unread_only=true,
    so a row's presence after a poll already means "unread as of that poll" --
    a row disappearing on the next poll (read or archived upstream) is
    handled by the same prune logic every other candidate source uses.

    Single-integration-owner: no user_id column, same as
    MustermeisterTaskCache -- see config.TASK_EMAIL_INTEGRATION_USER_ID.
    """
    id = db.Column(db.Integer, primary_key=True)
    sender_address = db.Column(db.String(320), nullable=False)  # bucket key
    provider = db.Column(db.String(20), nullable=False)          # "microsoft" | "gmail"
    sender_name = db.Column(db.String(200))
    subject = db.Column(db.String(500))
    last_received_at = db.Column(db.DateTime, nullable=False)
    count = db.Column(db.Integer, default=1)
    impact = db.Column(db.String(20))          # ImpactLevel: high-impact | low-impact | unclassified
    impact_score = db.Column(db.Float)         # genericInferenceScore -- secondary sort within a tier
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('sender_address', 'provider', name='uq_briefkorb_sender_provider'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'sender_address': self.sender_address,
            'provider': self.provider,
            'sender_name': self.sender_name,
            'subject': self.subject,
            'last_received_at': self.last_received_at.isoformat() if self.last_received_at else None,
            'count': self.count,
            'impact': self.impact,
            'impact_score': self.impact_score,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
        }
