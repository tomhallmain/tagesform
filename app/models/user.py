from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .mixins import db, JSONFieldMixin

class User(UserMixin, JSONFieldMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    activities = db.relationship('Activity', backref='owner', lazy=True)
    schedules = db.relationship('ScheduleRecord', backref='owner', lazy=True)
    entities = db.relationship('Entity', backref='owner', lazy=True)
    preferences = db.Column(db.JSON)  # Store user preferences for importance inference

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    def update_preferences(self, updates):
        """
        Update user preferences with type-specific transformations.
        """
        def transform_preferences(value):
            if isinstance(value, str) and value.lower() in ['true', 'false']:
                return value.lower() == 'true'
            return value
            
        return self.update_json_field('preferences', updates, transform_func=transform_preferences) 