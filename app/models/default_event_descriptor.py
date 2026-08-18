from datetime import datetime
from .mixins import db

class DefaultEventDescriptor(db.Model):
    """One row per app-wide catalog event a user can opt into (e.g. Kentucky
    Derby, music/art festivals) -- DB-seeded/admin-curated, not user-editable.
    Distinct from UserCalendarDescriptor (personal YAML) and
    Entity.calendar_entries (per-entity JSON): this is global content shared
    across users, who opt in individually via
    User.preferences['subscribed_default_events'] (see default_event_service.py).

    recurrence uses the same vocabulary as custom_calendar_service.VALID_RECURRENCES.
    recurrence_params holds whichever of month/day/weekday/ordinal/
    interval_years/anchor_year that recurrence kind needs -- one JSON column
    rather than several mostly-NULL columns, matching how UserCalendarDescriptor/
    Entity.calendar_entries already store this same kind of data.
    """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=False)  # e.g. 'Sports Festival' -- the settings UI groups by this
    recurrence = db.Column(db.String(30), nullable=False)
    recurrence_params = db.Column(db.JSON)
    description = db.Column(db.Text)
    location = db.Column(db.String(200))
    source_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
