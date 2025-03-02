from .mixins import db

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    recurrence = db.Column(db.String(50))  # daily, weekly, monthly, etc.
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50))
    location = db.Column(db.String(200))
    description = db.Column(db.Text)

    def to_dict(self):
        """Convert schedule to dictionary format"""
        return {
            'id': self.id,
            'title': self.title,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'recurrence': self.recurrence,
            'category': self.category,
            'location': self.location,
            'description': self.description
        } 