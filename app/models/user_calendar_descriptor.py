from datetime import datetime
from .mixins import db

class UserCalendarDescriptor(db.Model):
    """A user's personal calendar descriptor -- a YAML file describing their
    own one-off/annual calendar entries (birthdays, anniversaries, etc.).
    One row per user; re-saving replaces the whole file rather than merging
    with whatever was there before."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_user_calendar_descriptor_user'),
                         nullable=False, unique=True)
    raw_yaml = db.Column(db.Text, nullable=False)
    last_parse_error = db.Column(db.Text)  # set on the most recent failed parse, else NULL
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
