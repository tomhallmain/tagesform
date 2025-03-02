from flask_sqlalchemy import SQLAlchemy
from flask import current_app

db = SQLAlchemy()

class JSONFieldMixin:
    def update_json_field(self, field_name, updates, transform_func=None, validate_func=None):
        """
        Generic method to update any JSON field while handling SQLAlchemy change detection.
        
        Args:
            field_name (str): Name of the JSON field to update
            updates (dict): Dictionary of updates to apply
            transform_func (callable, optional): Function to transform values before storing
            validate_func (callable, optional): Function to validate updates before applying
            
        Returns:
            dict: The updated JSON field value
            
        Raises:
            ValueError: If validation fails
            AttributeError: If field doesn't exist
        """
        try:
            # Get current value, defaulting to empty dict
            current = getattr(self, field_name) or {}
            
            # Create new value by copying current and updating
            new_value = current.copy()
            
            # Transform updates if transform function provided
            if transform_func:
                updates = {k: transform_func(v) for k, v in updates.items()}
            
            # Validate updates if validate function provided
            if validate_func and not validate_func(updates):
                raise ValueError(f"Validation failed for {field_name} updates")
            
            # Update the dictionary
            new_value.update(updates)
            
            # Force SQLAlchemy to detect the change
            setattr(self, field_name, None)
            db.session.commit()
            
            setattr(self, field_name, new_value)
            db.session.commit()
            
            # Refresh the instance to ensure we have the latest data
            db.session.refresh(self)
            return getattr(self, field_name)
            
        except AttributeError:
            raise AttributeError(f"Model has no JSON field named {field_name}")
        except Exception as e:
            db.session.rollback()
            raise e

    def get_json_value(self, field_name, key, default=None):
        """
        Safely get a value from a JSON field.
        
        Args:
            field_name (str): Name of the JSON field
            key (str): Key to retrieve
            default: Value to return if key doesn't exist
            
        Returns:
            The value if found, else default
        """
        try:
            field_data = getattr(self, field_name) or {}
            return field_data.get(key, default)
        except AttributeError:
            return default

    def set_json_value(self, field_name, key, value, transform_func=None, validate_func=None):
        """
        Safely set a single value in a JSON field.
        
        Args:
            field_name (str): Name of the JSON field
            key (str): Key to set
            value: Value to set
            transform_func (callable, optional): Function to transform value before storing
            validate_func (callable, optional): Function to validate value before storing
            
        Returns:
            dict: The updated JSON field value
        """
        return self.update_json_field(
            field_name,
            {key: value},
            transform_func=transform_func,
            validate_func=validate_func
        ) 