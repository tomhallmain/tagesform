from .mixins import db, JSONFieldMixin
from datetime import datetime

class Entity(db.Model, JSONFieldMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))  # restaurant, store, service, etc.
    operating_hours = db.Column(db.JSON)  # Store hours in JSON format
    location = db.Column(db.String(200))
    contact_info = db.Column(db.String(200))
    description = db.Column(db.Text)
    tags = db.Column(db.JSON)  # For better categorization and search
    visited = db.Column(db.Boolean, default=False)  # Keep this as a column since it applies to all entities
    rating = db.Column(db.Integer)  # 0=terrible, 1=bad, 2=ok, 3=good, 4=great
    properties = db.Column(db.JSON)  # Category-specific properties like cuisine, delivery_radius, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_entity_user'), nullable=False)
    is_public = db.Column(db.Boolean, default=True)  # Whether the entity is shared with other users
    shared_with = db.Column(db.JSON)  # List of user IDs this entity is shared with
    calendar_entries = db.Column(db.JSON)  # List of dated entries (closures, special hours, events) -- see entity_calendar_service.py

    __table_args__ = (
        db.UniqueConstraint('name', 'category', 'location', 'user_id', name='uq_entity_name_category_location_user'),
    )

    def get_property(self, key, default=None):
        """Safely get a property value"""
        return self.get_json_value('properties', key, default)

    def set_property(self, key, value):
        """Safely set a property value"""
        return self.set_json_value('properties', key, value)

    @property
    def cuisine(self):
        """Get cuisine for restaurants"""
        return self.get_property('cuisine') if self.category == 'restaurant' else None

    def to_dict(self):
        """Convert entity to dictionary format"""
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'location': self.location,
            'description': self.description,
            'contact_info': self.contact_info,
            'operating_hours': self.operating_hours,
            'tags': self.tags,
            'visited': self.visited,
            'rating': self.rating,
            'properties': self.properties or {},
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'user_id': self.user_id,
            'is_public': self.is_public,
            'shared_with': self.shared_with or []
        }

    def to_json_dict(self):
        """Convert entity to JSON-serializable dictionary format"""
        data = self.to_dict()
        # Convert datetime objects to ISO format strings
        if data['created_at']:
            data['created_at'] = data['created_at'].isoformat()
        if data['updated_at']:
            data['updated_at'] = data['updated_at'].isoformat()
        return data

    @classmethod
    def from_json_dict(cls, data):
        """Create an Entity instance from a JSON-serialized dictionary"""
        # Convert ISO format strings back to datetime objects
        if data.get('created_at'):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if data.get('updated_at'):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return cls(**data)

    def can_view(self, user_id):
        """Check if a user can view this entity"""
        if self.is_public:
            return True
        if user_id == self.user_id:
            return True
        if self.shared_with and user_id in self.shared_with:
            return True
        return False

    def can_edit(self, user_id):
        """Check if a user can edit this entity"""
        return user_id == self.user_id

    def share_with(self, user_id):
        """Share this entity with another user"""
        if not self.shared_with:
            self.shared_with = []
        if user_id not in self.shared_with:
            self.shared_with.append(user_id)
            return True
        return False

    def unshare_with(self, user_id):
        """Remove sharing with a user"""
        if self.shared_with and user_id in self.shared_with:
            self.shared_with.remove(user_id)
            return True
        return False

    def get_calendar_entries(self):
        """Return this entity's calendar entries (closures, special hours,
        events), or an empty list if none exist."""
        return self.calendar_entries or []

    def add_calendar_entry(self, entry):
        """Append a new (already-validated, already-id-assigned) calendar
        entry."""
        entries = self.get_calendar_entries() + [entry]
        self._set_calendar_entries(entries)
        return entry

    def update_calendar_entry(self, entry_id, entry):
        """Replace the entry with the given id. Returns the updated entry,
        or None if no entry with that id exists."""
        found = False
        new_entries = []
        for existing in self.get_calendar_entries():
            if existing['id'] == entry_id:
                found = True
                new_entries.append(entry)
            else:
                new_entries.append(existing)
        if not found:
            return None
        self._set_calendar_entries(new_entries)
        return entry

    def remove_calendar_entry(self, entry_id):
        """Remove the entry with the given id. Returns True if an entry was
        removed, False if no entry with that id existed."""
        entries = self.get_calendar_entries()
        new_entries = [e for e in entries if e['id'] != entry_id]
        if len(new_entries) == len(entries):
            return False
        self._set_calendar_entries(new_entries)
        return True

    def _set_calendar_entries(self, entries):
        """Replace the whole calendar_entries list.

        Follows the same reset-then-set pattern as JSONFieldMixin.update_json_field:
        SQLAlchemy's JSON column type does not detect in-place mutation of the
        same list reference, so without the intermediate None write the second
        setattr can be a no-op against the ORM's change tracking.
        """
        self.calendar_entries = None
        db.session.commit()
        self.calendar_entries = entries
        db.session.commit()
        db.session.refresh(self)

    @classmethod
    def find_duplicates(cls, name, category, location, user_id, include_public=False, exclude_id=None):
        """Find potential duplicates based on name similarity and exact category/location match.

        By default this only searches the given user's own places. Pass
        include_public=True to widen the search to also cover other users'
        public places -- intended for the case where the place being
        created/edited is itself being made public, since a private place
        only ever needs to be checked against the owner's own list.
        exclude_id excludes a specific entity (the one being edited) from
        matching against itself.
        """
        # Log input parameters
        print(f"Finding duplicates for: name='{name}', category='{category}', location='{location}', user_id={user_id}, include_public={include_public}")

        owner_filter = cls.user_id == user_id
        scope_filter = db.or_(owner_filter, cls.is_public == True) if include_public else owner_filter

        # Normalize location value
        location = location if location else None
        print(f"\nNormalized location value: {location}")

        # First check for exact matches
        exact_match_query = cls.query.filter(
            scope_filter,
            cls.name.ilike(name),
            cls.category == category,
            db.or_(
                # Both locations match (including both being None/empty)
                cls.location == location,
                # Match records with NULL or empty location regardless of input location
                cls.location.is_(None),
                cls.location == ''
            )
        )
        if exclude_id is not None:
            exact_match_query = exact_match_query.filter(cls.id != exclude_id)
        print(f"Exact match query: {exact_match_query}")

        exact_matches = exact_match_query.all()
        print(f"Found {len(exact_matches)} exact matches")
        for match in exact_matches:
            print(f"Exact match found: id={match.id}, name='{match.name}', category='{match.category}', location='{match.location}'")

        if exact_matches:
            return [match.to_dict() for match in exact_matches]

        # If no exact matches, look for similar names with matching category and similar location handling
        similar_match_query = cls.query.filter(
            scope_filter,
            cls.category == category,
            db.or_(
                # Both locations match (including both being None/empty)
                cls.location == location,
                # Match records with NULL or empty location regardless of input location
                cls.location.is_(None),
                cls.location == ''
            )
        )
        if exclude_id is not None:
            similar_match_query = similar_match_query.filter(cls.id != exclude_id)
        print(f"Similar match query: {similar_match_query}")

        similar_matches = similar_match_query.all()
        print(f"Found {len(similar_matches)} category/location matches before name similarity check")

        # Filter for similar names using Utils.is_similar_strings
        from ..utils.utils import Utils
        final_matches = [entity for entity in similar_matches if Utils.is_similar_strings(entity.name.lower(), name.lower())]
        print(f"Found {len(final_matches)} matches after name similarity check")
        for match in final_matches:
            print(f"Similar match found: id={match.id}, name='{match.name}', category='{match.category}', location='{match.location}'")

        return [match.to_dict() for match in final_matches]