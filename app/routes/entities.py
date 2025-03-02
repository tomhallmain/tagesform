from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from datetime import datetime
import pytz
from ..models import Entity, db

entities_bp = Blueprint('entities', __name__)

@entities_bp.route('/add-place', methods=['GET', 'POST'])
@login_required
def add_place():
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        category = request.form.get('category')
        location = request.form.get('location')
        contact_info = request.form.get('contact_info')
        description = request.form.get('description')
        tags = request.form.get('tags', '').split(',') if request.form.get('tags') else []
        visited = 'visited' in request.form

        # Initialize properties dictionary
        properties = {}
        
        # Add category-specific properties
        if category == 'restaurant':
            cuisine = request.form.get('cuisine')
            if cuisine:
                properties['cuisine'] = cuisine

        # Process operating hours
        operating_hours = {}
        days = request.form.getlist('days[]')
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            if day in days:
                operating_hours[day] = {
                    'open': request.form.get(f'{day}_open'),
                    'close': request.form.get(f'{day}_close')
                }

        # Create new entity
        entity = Entity(
            name=name,
            category=category,
            operating_hours=operating_hours,
            location=location,
            contact_info=contact_info,
            description=description,
            tags=tags,
            visited=visited,
            properties=properties
        )

        db.session.add(entity)
        db.session.commit()

        flash('Place added successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('add_place.html')

@entities_bp.route('/api/entities/available')
@login_required
def get_available_entities():
    current_time = datetime.now(pytz.UTC)
    current_day = current_time.strftime('%A').lower()
    
    # Query entities that are currently open
    available_entities = Entity.query.all()  # TODO: Add filtering based on operating hours
    
    return jsonify([entity.to_dict() for entity in available_entities]) 