from datetime import datetime
from .mixins import db

class EventCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(200))
    source = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    year = db.Column(db.Integer, nullable=False)  # For efficient querying
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_event_cache_user'), nullable=True)
    # NULL for global/public events (holidays, etc. from the background job);
    # set to the owning user's id for personal entries from that user's
    # custom calendar descriptor (see UserCalendarDescriptor).
    entity_id = db.Column(db.Integer, db.ForeignKey('entity.id', name='fk_event_cache_entity'), nullable=True)
    # NULL except for entries from a specific Entity's calendar_entries (see
    # entity_calendar_service.py). Deliberately independent of user_id above --
    # visibility for these rows is governed by the entity's own sharing rules
    # (Entity.can_view-style), not by "which user does this row belong to."
    
    @staticmethod
    def from_event_dict(event_dict):
        """Create an EventCache instance from an event dictionary"""
        return EventCache(
            title=event_dict['title'],
            date=datetime.strptime(event_dict['start_time'], '%Y-%m-%d %H:%M'),
            description=event_dict.get('description'),
            location=event_dict.get('location'),
            source=event_dict['sources'][0] if event_dict.get('sources') else None,
            year=datetime.strptime(event_dict['start_time'], '%Y-%m-%d %H:%M').year
        )
    
    def to_dict(self):
        """Convert to dictionary format matching the API response"""
        return {
            'id': self.id,
            'title': self.title,
            'start_time': self.date.strftime('%Y-%m-%d %H:%M'),
            'description': self.description,
            'location': self.location,
            'sources': [self.source] if self.source else []
        } 