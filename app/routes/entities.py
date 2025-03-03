from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
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
            properties=properties,
            user_id=current_user.id
        )

        db.session.add(entity)
        db.session.commit()

        flash('Place added successfully!', 'success')
        return redirect(url_for('entities.list_places'))

    return render_template('add_place.html')

@entities_bp.route('/delete-place/<int:entity_id>', methods=['POST'])
@login_required
def delete_place(entity_id):
    entity = Entity.query.get_or_404(entity_id)
    
    # Ensure user owns this entity
    if entity.user_id != current_user.id:
        flash('You do not have permission to delete this place.', 'error')
        return redirect(url_for('entities.list_places'))
    
    name = entity.name
    db.session.delete(entity)
    db.session.commit()
    
    flash(f'Successfully deleted "{name}"', 'success')
    return redirect(url_for('entities.list_places'))

@entities_bp.route('/review-import')
@login_required
def review_import():
    # Get the imported data from the session
    import_data = session.get('import_data', [])
    if not import_data:
        flash('No data to review. Please import a CSV file first.', 'error')
        return redirect(url_for('entities.import_places'))
    
    return render_template('review_import.html', places=import_data)

@entities_bp.route('/confirm-import', methods=['POST'])
@login_required
def confirm_import():
    # Get the reviewed/edited data
    import_data = session.get('import_data', [])
    if not import_data:
        flash('No data to import. Please import a CSV file first.', 'error')
        return redirect(url_for('entities.import_places'))
    
    try:
        entities_added = 0
        for place in import_data:
            if not place.get('name'):  # Skip entries with empty names
                continue
                
            # Ensure user_id is set for each imported entity
            place['user_id'] = current_user.id
            entity = Entity(**place)
            db.session.add(entity)
            entities_added += 1
        
        db.session.commit()
        session.pop('import_data', None)  # Clear the import data from session
        
        flash(f'Successfully imported {entities_added} places', 'success')
        return redirect(url_for('entities.list_places'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error importing places: {str(e)}', 'error')
        return redirect(url_for('entities.review_import'))

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
            'rating': ['rating', 'good', 'good?', 'like', 'liked'],
            'notes': ['notes', 'description', 'comments']
        }
        
        # Read CSV file
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = csv.reader(stream)
            
            # Read and normalize headers
            raw_headers = next(reader)
            print(f"Number of raw headers: {len(raw_headers)}")  # Debug log
            headers = [h.strip().lower() for h in raw_headers]
            print(f"Raw headers: {raw_headers}")  # Debug log
            print(f"Normalized headers: {headers}")  # Debug log
            
            # Create a mapping of normalized headers to their original indices using fuzzy matching
            header_map = {}
            for idx, header in enumerate(headers):
                matched = False
                print(f"Processing header: {header} at index {idx}")  # Debug log

                # First try exact matches
                for expected_col, alternatives in EXPECTED_COLUMNS.items():
                    if header == expected_col or header in alternatives:
                        header_map[expected_col] = idx
                        matched = True
                        print(f"Found exact match: {header} -> {expected_col} at index {idx}")  # Debug log
                        break
                
                # Only try fuzzy matching if no exact match was found
                if not matched:
                    for expected_col, alternatives in EXPECTED_COLUMNS.items():
                        if expected_col not in header_map and any(Utils.is_similar_strings(header, alt, do_print=True) for alt in alternatives):
                            header_map[expected_col] = idx
                            print(f"Found fuzzy match: {header} -> {expected_col} at index {idx}")  # Debug log
                            break
            
            print(f"Final header mapping: {header_map}")  # Debug log
            
            # Validate required columns
            if 'name' not in header_map:
                similar_columns = [h for h in headers if any(Utils.is_similar_strings(h, alt) for alt in EXPECTED_COLUMNS['name'])]
                print(f"Headers checked for name: {headers}")  # Debug log
                print(f"Similar columns found: {similar_columns}")  # Debug log
                if similar_columns:
                    raise ValueError(f'Could not find "name" column. Did you mean: {", ".join(similar_columns)}?')
                else:
                    raise ValueError('CSV file must contain a "name" column')
            
            parsed_entities = []
            skipped_rows = []
            invalid_categories = set()
            
            for row_num, row in enumerate(reader, start=2):
                print(f"\nProcessing row {row_num}: {row}")  # Debug log
                print(f"Row length: {len(row)}")  # Debug log
                
                # Skip empty rows
                if not row or all(cell.strip() == '' for cell in row):
                    print(f"Skipping empty row {row_num}")  # Debug log
                    continue
                
                # Validate row length matches headers
                if len(row) != len(headers):
                    print(f"Warning: Row {row_num} has {len(row)} columns but headers has {len(headers)} columns")  # Debug log
                
                # Helper function to safely get column value
                def get_col(name, default=''):
                    if name not in header_map:
                        print(f"Column {name} not found in header_map")  # Debug log
                        return default
                    idx = header_map[name]
                    if idx >= len(row):
                        print(f"Warning: Index {idx} for column {name} is out of range for row length {len(row)}")  # Debug log
                        return default
                    val = row[idx].strip()
                    print(f"Getting column {name} at index {idx}: {val}")  # Debug log
                    # Keep everything lowercase for storage
                    return val.lower() if name in ['category', 'cuisine', 'location'] else val
                
                # Helper function to parse boolean values
                def parse_bool(val, default=None):
                    if not val or not val.strip():
                        return default
                    val = str(val).lower().strip()
                    if val in ['ok', 'okay']:
                        return True
                    return val in ['true', 't', 'yes', 'y', '1']
                
                # Helper function to parse rating values
                def parse_rating(val):
                    if not val or not val.strip():
                        return None
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
                    
                    return None
                
                name = get_col('name')
                if not name:
                    skipped_rows.append(f"Row {row_num}: Empty name")
                    continue
                
                # Build entity parameters
                entity_params = {
                    'name': name,
                    'user_id': current_user.id
                }
                
                # Process all fields as before, but store in entity_params instead of creating Entity
                category = get_col('category')
                if category:
                    if category not in VALID_CATEGORIES:
                        # Try to find a similar category
                        similar_categories = [c for c in VALID_CATEGORIES if Utils.is_similar_strings(category, c)]
                        if similar_categories:
                            category = similar_categories[0]
                        else:
                            invalid_categories.add(category)
                            category = 'other'
                    entity_params['category'] = category
                else:
                    # Only set default category if cuisine exists
                    cuisine = get_col('cuisine')
                    if cuisine:
                        entity_params['category'] = 'restaurant'
                    else:
                        entity_params['category'] = 'other'

                # Process location
                location = get_col('location')
                if location:
                    entity_params['location'] = location

                # Process description/notes
                notes = get_col('notes')
                if notes:
                    entity_params['description'] = notes

                # Process cuisine and set in properties if exists
                cuisine = get_col('cuisine')
                if cuisine:
                    # Try to find a similar cuisine
                    similar_cuisines = [c for c in COMMON_CUISINES if Utils.is_similar_strings(cuisine, c)]
                    if similar_cuisines:
                        cuisine = similar_cuisines[0]
                    entity_params['properties'] = {'cuisine': cuisine}

                # Process visited field
                visited = parse_bool(get_col('visited'))
                if visited is not None:
                    entity_params['visited'] = visited

                # Process rating field
                rating = parse_rating(get_col('rating'))
                if rating is not None:
                    entity_params['rating'] = rating

                parsed_entities.append(entity_params)
            
            if not parsed_entities:
                flash('No valid places found in the CSV file', 'error')
                return redirect(request.url)
            
            # Store the parsed data in session for review
            session['import_data'] = parsed_entities
            
            # Show warnings about skipped rows and invalid categories
            if skipped_rows:
                flash(f'Skipped {len(skipped_rows)} rows: {"; ".join(skipped_rows)}', 'warning')
            if invalid_categories:
                flash(f'Found invalid categories that were set to "other": {", ".join(invalid_categories)}', 'warning')
            
            return redirect(url_for('entities.review_import'))
            
        except ValueError as ve:
            flash(str(ve), 'error')
            return redirect(request.url)
        except Exception as e:
            flash(f'Error processing CSV: {str(e)}', 'error')
            return redirect(request.url)
    
    return render_template('import_places.html')

@entities_bp.route('/places')
@login_required
def list_places():
    places = Entity.query.filter_by(user_id=current_user.id).all()
    return render_template('places.html', places=places)

@entity_api_bp.route('/entities/available')
@login_required
def get_available_entities():
    current_time = datetime.now(pytz.UTC)
    current_day = current_time.strftime('%A').lower()
    
    # Query entities that are currently open
    available_entities = Entity.query.all()  # TODO: Add filtering based on operating hours
    
    return jsonify([entity.to_dict() for entity in available_entities])

@entity_api_bp.route('/entities/remove-from-import/<int:index>', methods=['POST'])
@login_required
def remove_from_import(index):
    import_data = session.get('import_data', [])
    
    try:
        if 0 <= index < len(import_data):
            import_data.pop(index)
            session['import_data'] = import_data
            return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': False, 'error': 'Invalid index'}) 