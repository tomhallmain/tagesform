from datetime import datetime
from .mixins import db

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    importance = db.Column(db.Float)  # 0.0 to 1.0: LLM-inferred importance
    status = db.Column(db.String(20), default='upcoming')  # upcoming, in_progress, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50))  # social, health, work, leisure, etc.
    duration = db.Column(db.Integer)  # estimated duration in minutes
    location = db.Column(db.String(200))
    participants = db.Column(db.JSON)  # List of people involved
    notes = db.Column(db.Text)

    def to_dict(self):
        """Convert activity to dictionary format"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'scheduled_time': self.scheduled_time.isoformat(),
            'importance': self.importance,
            'status': self.status,
            'category': self.category,
            'duration': self.duration,
            'location': self.location,
            'participants': self.participants,
            'notes': self.notes
        } 