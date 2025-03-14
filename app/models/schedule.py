from .mixins import db

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start_time = db.Column(db.Integer, nullable=False)  # Minutes since midnight (0-1440)
    end_time = db.Column(db.Integer, nullable=False)    # Minutes since midnight (0-1440)
    recurrence = db.Column(db.String(50))  # daily, weekly, monthly, etc.
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50))
    location = db.Column(db.String(200))
    description = db.Column(db.Text)

    @staticmethod
    def time_to_minutes(time_str):
        """Convert HH:MM time string to minutes since midnight"""
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes

    @staticmethod
    def minutes_to_time(minutes):
        """Convert minutes since midnight to HH:MM time string"""
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}"

    def to_dict(self):
        """Convert schedule to dictionary format"""
        return {
            'id': self.id,
            'title': self.title,
            'start_time': self.minutes_to_time(self.start_time),
            'end_time': self.minutes_to_time(self.end_time),
            'recurrence': self.recurrence,
            'category': self.category,
            'location': self.location,
            'description': self.description
        } 