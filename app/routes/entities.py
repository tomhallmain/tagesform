from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import pytz
import csv
import io
from ..models import Entity, db
from ..utils.utils import Utils

# Define valid categories and common cuisines
VALID_CATEGORIES = {
    'restaurant', 'cafe', 'bar', 'park', 'store', 'service', 'gym', 'theater',
    'museum', 'library', 'school', 'hospital', 'pharmacy', 'bank', 'other'
}

COMMON_CUISINES = {
    'italian', 'chinese', 'japanese', 'mexican', 'indian', 'thai', 'french',
    'american', 'mediterranean', 'greek', 'spanish', 'vietnamese', 'korean',
    'middle eastern', 'turkish', 'brazilian', 'peruvian', 'fusion'
}

# Define valid ratings and their mappings
VALID_RATINGS = {
    # Great ratings
    'great': 'great',
    'best': 'great',
    'amazing': 'great',
    'awesome': 'great',
    'stupendous': 'great',
    'delicious': 'great',
    'excellent': 'great',
    'fantastic': 'great',
    'outstanding': 'great',
    'perfect': 'great',
    
    # Good ratings
    'good': 'good',
    'nice': 'good',
    'decent': 'good',
    'pleasant': 'good',
    'enjoyable': 'good',
    
    # OK ratings
    'ok': 'ok',
    'okay': 'ok',
    'so-so': 'ok',
    'mediocre': 'ok',
    'average': 'ok',
    'alright': 'ok',
    'fine': 'ok',
    
    # Bad ratings
    'bad': 'bad',
    'poor': 'bad',
    'disappointing': 'bad',
    'subpar': 'bad',
    'below average': 'bad',
    
    # Terrible ratings
    'terrible': 'terrible',
    'worst': 'terrible',
    'awful': 'terrible',
    'disgusting': 'terrible',
    'horrible': 'terrible',
    'atrocious': 'terrible',
    'dreadful': 'terrible'
}

# Create two separate blueprints
entities_bp = Blueprint('entities', __name__)  # For entity pages
entity_api_bp = Blueprint('entity_api', __name__, url_prefix='/api')  # For entity API endpoints

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
        return redirect(url_for('main.index'))

    return render_template('add_place.html')

@entities_bp.route('/import-places', methods=['GET', 'POST'])
@login_required
def import_places():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        if not file.filename.endswith('.csv'):
            flash('Only CSV files are allowed', 'error')
            return redirect(request.url)
        
        # Define expected column names
        EXPECTED_COLUMNS = {
            'name': ['name'],
            'category': ['category', 'type'],
            'cuisine': ['cuisine', 'food type'],
            'location': ['location', 'address', 'place'],
            'visited': ['visited', 'been there'],
            'rating': ['rating', 'good', 'like', 'liked'],
            'notes': ['notes', 'description', 'comments']
        }
        
        # Read CSV file
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = csv.reader(stream)
            
            # Read and normalize headers
            raw_headers = next(reader)
            headers = [h.strip().lower() for h in raw_headers]
            
            # Create a mapping of normalized headers to their original indices using fuzzy matching
            header_map = {}
            for idx, header in enumerate(headers):
                # Try to match this header with our expected columns
                for expected_col, alternatives in EXPECTED_COLUMNS.items():
                    if any(Utils.is_similar_strings(header, alt) for alt in alternatives):
                        header_map[expected_col] = idx
                        break
            
            # Validate required columns
            if 'name' not in header_map:
                similar_columns = [h for h in headers if any(Utils.is_similar_strings(h, alt) for alt in EXPECTED_COLUMNS['name'])]
                if similar_columns:
                    raise ValueError(f'Could not find "name" column. Did you mean: {", ".join(similar_columns)}?')
                else:
                    raise ValueError('CSV file must contain a "name" column')
            
            entities_added = 0
            skipped_rows = []
            invalid_categories = set()
            for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is headers
                # Helper function to safely get column value
                def get_col(name, default=''):
                    val = row[header_map.get(name, -1)].strip() if name in header_map else default
                    return val.lower() if name in ['category', 'cuisine', 'location'] else val
                
                # Helper function to parse boolean values
                def parse_bool(val, default=False):
                    if not val:
                        return default
                    val = str(val).lower()
                    if val in ['ok', 'okay']:
                        return True
                    return val in ['true', 't', 'yes', 'y', '1']
                
                # Helper function to parse rating values
                def parse_rating(val, default='bad'):
                    if not val:
                        return default
                    val = str(val).lower().strip()
                    
                    # Check for boolean values first
                    if val in ['true', 't', 'yes', 'y', '1']:
                        return 'good'
                    if val in ['false', 'f', 'no', 'n', '0']:
                        return 'bad'
                    
                    # Check for valid rating values
                    if val in VALID_RATINGS:
                        return VALID_RATINGS[val]
                    
                    # Try to find a similar rating
                    similar_ratings = [r for r in VALID_RATINGS.keys() if Utils.is_similar_strings(val, r)]
                    if similar_ratings:
                        return VALID_RATINGS[similar_ratings[0]]
                    
                    return default
                
                name = get_col('name')
                if not name:  # Skip rows with empty names
                    skipped_rows.append(f"Row {row_num}: Empty name")
                    continue
                
                # Validate and clean category
                category = get_col('category')
                if category and category not in VALID_CATEGORIES:
                    # Try to find a similar category
                    similar_categories = [c for c in VALID_CATEGORIES if Utils.is_similar_strings(category, c)]
                    if similar_categories:
                        category = similar_categories[0]
                    else:
                        invalid_categories.add(category)
                        category = 'other'
                
                # If no category, infer from cuisine
                if not category:
                    category = 'restaurant' if get_col('cuisine') else 'other'
                
                # Validate and clean cuisine
                cuisine = get_col('cuisine')
                if cuisine:
                    # Try to find a similar cuisine
                    similar_cuisines = [c for c in COMMON_CUISINES if Utils.is_similar_strings(cuisine, c)]
                    if similar_cuisines:
                        cuisine = similar_cuisines[0]
                
                # Create new entity
                entity = Entity(
                    name=name,
                    category=category,
                    location=get_col('location'),
                    description=get_col('notes'),
                    visited=parse_bool(get_col('visited')),
                    properties={
                        'cuisine': cuisine or None,
                        'rating': parse_rating(get_col('rating'))
                    },
                    user_id=current_user.id
                )
                
                db.session.add(entity)
                entities_added += 1
            
            if entities_added == 0:
                flash('No valid places found in the CSV file', 'error')
                return redirect(request.url)
            
            db.session.commit()
            
            # Show warnings about skipped rows and invalid categories
            if skipped_rows:
                flash(f'Skipped {len(skipped_rows)} rows: {"; ".join(skipped_rows)}', 'warning')
            if invalid_categories:
                flash(f'Found invalid categories that were set to "other": {", ".join(invalid_categories)}', 'warning')
            
            flash(f'Successfully imported {entities_added} places', 'success')
            return redirect(url_for('main.index'))
            
        except ValueError as ve:
            flash(str(ve), 'error')
            return redirect(request.url)
        except Exception as e:
            db.session.rollback()
            flash(f'Error importing CSV: {str(e)}', 'error')
            return redirect(request.url)
    
    return render_template('import_places.html')

@entity_api_bp.route('/entities/available')
@login_required
def get_available_entities():
    current_time = datetime.now(pytz.UTC)
    current_day = current_time.strftime('%A').lower()
    
    # Query entities that are currently open
    available_entities = Entity.query.all()  # TODO: Add filtering based on operating hours
    
    return jsonify([entity.to_dict() for entity in available_entities]) 