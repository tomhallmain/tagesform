from datetime import datetime
from .mixins import db

class EntityComment(db.Model):
    """A private note a user keeps on an entity, invisible to everyone else --
    including the entity's owner -- regardless of the entity's is_public/
    shared_with state. One row per (entity, user): saving overwrites the
    user's existing note rather than appending a new one."""
    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey('entity.id', name='fk_entity_comment_entity'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_entity_comment_user'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('entity_id', 'user_id', name='uq_entity_comment_entity_user'),
    )

    def to_dict(self):
        return {
            'entity_id': self.entity_id,
            'body': self.body,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
