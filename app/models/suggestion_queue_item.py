from datetime import datetime
from .mixins import db

class SuggestionQueueItem(db.Model):
    """A ranked "you might want to do this" suggestion for one user,
    persisted so dismiss/snooze/complete actually stick across refreshes
    instead of the item just reappearing on the next dashboard load.

    (item_type, source_id) is a loose polymorphic reference, not a real
    foreign key, since it can point at several different tables depending on
    item_type: 'activity' -> Activity.id, 'entity' -> Entity.id, 'event' ->
    EventCache.id, 'task' -> MustermeisterTaskCache.id, 'email' ->
    BriefKorbMessageCache.id. 'plan' is the odd one out -- an LLM-synthesized
    suggestion with no single backing row, so its source_id is built from a
    fixed per-signal-type base constant plus that item's position among
    however many the LLM returned this cycle (see
    planning_agent_service.PLAN_SIGNAL_SOURCE_IDS/PLAN_ITEM_SOURCE_ID_STRIDE)
    rather than a real table id. item_type is deliberately a free-form string
    rather than an enum/CHECK constraint, so any future source only needs new
    candidate-gathering logic in suggestion_queue_service, not a migration or
    a change to this model.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_suggestion_queue_item_user'), nullable=False)
    item_type = db.Column(db.String(20), nullable=False)
    source_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    reason = db.Column(db.String(300))
    score = db.Column(db.Float, nullable=False, default=0.0)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending | dismissed | snoozed | done
    snoozed_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'item_type', 'source_id', name='uq_suggestion_queue_user_item'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'item_type': self.item_type,
            'source_id': self.source_id,
            'title': self.title,
            'reason': self.reason,
            'score': self.score,
            'status': self.status,
            'snoozed_until': self.snoozed_until.isoformat() if self.snoozed_until else None,
        }
