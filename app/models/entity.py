from .mixins import db, JSONFieldMixin

class Entity(db.Model, JSONFieldMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))  # restaurant, store, service, etc.
    operating_hours = db.Column(db.JSON)  # Store hours in JSON format
    location = db.Column(db.String(200))
    contact_info = db.Column(db.String(200))
    description = db.Column(db.Text)
    tags = db.Column(db.JSON)  # For better categorization and search
    visited = db.Column(db.Boolean, default=False)  # Keep this as a column since it applies to all entities
    properties = db.Column(db.JSON)  # Category-specific properties like cuisine, delivery_radius, etc.
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_entity_user'), nullable=False)

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
            'properties': self.properties or {},
            'user_id': self.user_id
        } 