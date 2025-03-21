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
    is_public = db.Column(db.Boolean, default=False)  # Whether the entity is shared with other users
    shared_with = db.Column(db.JSON)  # List of user IDs this entity is shared with

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

    @classmethod
    def find_duplicates(cls, name, category, location, user_id):
        """Find potential duplicates based on name similarity and exact category/location match"""
        # Log input parameters
        print(f"Finding duplicates for: name='{name}', category='{category}', location='{location}', user_id={user_id}")

        # Debug: Show all entities with similar names regardless of location
        debug_query = cls.query.filter(
            cls.user_id == user_id,
            cls.category == category
        )
        print("\nDEBUG - All existing records with matching category:")
        for record in debug_query.all():
            print(f"Found record: id={record.id}, name='{record.name}', category='{record.category}', location='{record.location}'")

        # Normalize location value
        location = location if location else None
        print(f"\nNormalized location value: {location}")

        # First check for exact matches
        exact_match_query = cls.query.filter(
            cls.user_id == user_id,
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
        print(f"Exact match query: {exact_match_query}")
        
        exact_matches = exact_match_query.all()
        print(f"Found {len(exact_matches)} exact matches")
        for match in exact_matches:
            print(f"Exact match found: id={match.id}, name='{match.name}', category='{match.category}', location='{match.location}'")
        
        if exact_matches:
            return [match.to_dict() for match in exact_matches]

        # If no exact matches, look for similar names with matching category and similar location handling
        similar_match_query = cls.query.filter(
            cls.user_id == user_id,
            cls.category == category,
            db.or_(
                # Both locations match (including both being None/empty)
                cls.location == location,
                # Match records with NULL or empty location regardless of input location
                cls.location.is_(None),
                cls.location == ''
            )
        )
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