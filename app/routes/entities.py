import csv
import io
import json
from functools import lru_cache
import pytz
import random
import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session, current_app, abort
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from ..models import Entity, db
from ..utils.utils import Utils

# Define valid categories and common cuisines
VALID_CATEGORIES = {
    'restaurant', 'cafe', 'bar', 'park', 'store', 'service', 'gym', 'theater',
    'museum', 'library', 'school', 'hospital', 'pharmacy', 'bank', 'other'
}

COMMON_CUISINES = {
    'british', 'german', 'italian', 'chinese', 'japanese', 'mexican', 'indian', 'thai',
    'french', 'american', 'mediterranean', 'greek', 'spanish', 'vietnamese', 'korean',
    'middle eastern', 'turkish', 'brazilian', 'peruvian', 'fusion', 'other'
}

# Define valid ratings and their mappings
VALID_RATINGS = {
    # Great ratings (4)
    'great': 4,
    'best': 4,
    'amazing': 4,
    'awesome': 4,
    'stupendous': 4,
    'delicious': 4,
    'excellent': 4,
    'fantastic': 4,
    'outstanding': 4,
    'perfect': 4,
    
    # Good ratings (3)
    'good': 3,
    'nice': 3,
    'decent': 3,
    'pleasant': 3,
    'enjoyable': 3,
    
    # OK ratings (2)
    'ok': 2,
    'okay': 2,
    'so-so': 2,
    'mediocre': 2,
    'average': 2,
    'alright': 2,
    'fine': 2,
    
    # Bad ratings (1)
    'bad': 1,
    'poor': 1,
    'disappointing': 1,
    'subpar': 1,
    'below average': 1,
    
    # Terrible ratings (0)
    'terrible': 0,
    'worst': 0,
    'awful': 0,
    'disgusting': 0,
    'horrible': 0,
    'atrocious': 0,
    'dreadful': 0
}

# Create two separate blueprints
entities_bp = Blueprint('entities', __name__)  # For entity pages
entity_api_bp = Blueprint('entity_api', __name__, url_prefix='/api')  # For entity API endpoints

class ImportData(db.Model):
    """Temporary table for storing import data"""
    id = db.Column(db.String(36), primary_key=True)  # UUID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    data = db.Column(db.Text, nullable=False)  # Store JSON as text
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    @property
    def json_data(self):
        """Get the data as a Python object"""
        if not self.data:
            return None
        return json.loads(self.data)

    @json_data.setter
    def json_data(self, value):
        """Set the data as JSON string"""
        if value is None:
            self.data = None
        else:
            self.data = json.dumps(value, default=str)  # Convert datetime to string

@entities_bp.route('/add-place', methods=['GET', 'POST'])
@login_required
def add_place():
    if request.method == 'POST':
        # Check if this is an AJAX request for duplicate checking
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        name = request.form.get('name')
        category = request.form.get('category')
        location = request.form.get('location')
        contact_info = request.form.get('contact_info')
        description = request.form.get('description')
        tags = request.form.get('tags', '').split(',') if request.form.get('tags') else []
        visited = 'visited' in request.form
        rating_str = request.form.get('rating')

        # Validate rating
        rating = None
        if rating_str:
            try:
                rating = int(rating_str)
                if rating < 0 or rating > 4:
                    if is_ajax:
                        return jsonify({'error': 'Invalid rating value. Must be between 0 and 4.'}), 400
                    flash('Invalid rating value. Must be between 0 and 4.')
                    return render_template('add_place.html'), 400
            except ValueError:
                if is_ajax:
                    return jsonify({'error': 'Invalid rating value. Must be a number.'}), 400
                flash('Invalid rating value. Must be a number.')
                return render_template('add_place.html'), 400

        # If a valid rating is provided, automatically set visited to True
        if rating is not None:
            visited = True

        # Rest of validation and entity creation
        if not name:
            if is_ajax:
                return jsonify({'error': 'Name is required.'}), 400
            flash('Name is required.')
            return render_template('add_place.html'), 400

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

        # Check for duplicates before creating the entity
        entity_id = request.form.get('id')  # Get entity ID if this is an update
        potential_duplicates = Entity.find_duplicates(
            name=name,
            category=category,
            location=location,
            user_id=current_user.id
        )

        if potential_duplicates:
            # If this is an AJAX request (checking for duplicates), return the duplicates
            if is_ajax:
                return jsonify({
                    'has_duplicates': True,
                    'duplicates': potential_duplicates
                })
            
            # For regular form submission, show error
            flash('Potential duplicate found. Please review the details before saving.', 'warning')
            return render_template('add_place.html', 
                                name=name, 
                                category=category, 
                                location=location,
                                contact_info=contact_info,
                                description=description,
                                tags=','.join(tags),
                                visited=visited,
                                rating=rating,
                                cuisine=properties.get('cuisine'),
                                operating_hours=operating_hours)

        # If this is just an AJAX duplicate check, return success
        if is_ajax:
            return jsonify({'has_duplicates': False})

        try:
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
                rating=rating,
                properties=properties,
                user_id=current_user.id
            )

            db.session.add(entity)
            db.session.commit()

            flash('Place added successfully!', 'success')
            return redirect(url_for('entities.list_places', _anchor=f'entity-{entity.id}'))

        except Exception as e:
            db.session.rollback()
            # Check if it's a duplicate key error
            if 'UNIQUE constraint failed' in str(e):
                flash('This place already exists in your list.', 'error')
            else:
                flash(f'Error adding place: {str(e)}', 'error')
            return render_template('add_place.html', 
                                name=name, 
                                category=category, 
                                location=location,
                                contact_info=contact_info,
                                description=description,
                                tags=','.join(tags),
                                visited=visited,
                                rating=rating,
                                cuisine=properties.get('cuisine'),
                                operating_hours=operating_hours)

    return render_template('add_place.html')

@entities_bp.route('/delete-place/<int:entity_id>', methods=['POST'])
@login_required
def delete_place(entity_id):
    entity = Entity.query.get_or_404(entity_id)
    
    # Ensure user owns this entity
    if not entity.can_edit(current_user.id):
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
    # Get the import ID from session
    import_id = session.get('current_import_id')
    if not import_id:
        flash('No data to review. Please import a CSV file first.', 'error')
        return redirect(url_for('entities.import_places'))
    
    # Get the imported data from the database
    import_data = db.session.get(ImportData, import_id)
    if not import_data or import_data.user_id != current_user.id:
        flash('Import data not found or expired.', 'error')
        return redirect(url_for('entities.import_places'))
    
    data = import_data.json_data
    if not data:
        flash('No data to review.', 'error')
        return redirect(url_for('entities.import_places'))
    
    # Check if data is already processed (has duplicates and non_duplicates)
    if isinstance(data, dict) and 'duplicates' in data and 'non_duplicates' in data:
        duplicates = data['duplicates']
        non_duplicates = data['non_duplicates']
    else:
        # Process the data for the first time
        duplicates = []
        non_duplicates = []
        
        for idx, place in enumerate(data):
            potential_duplicates = Entity.find_duplicates(
                name=place['name'],
                category=place.get('category', 'other'),
                location=place.get('location'),
                user_id=current_user.id
            )
            
            if potential_duplicates:
                duplicates.append({
                    'index': idx,
                    'new': place,
                    'existing': potential_duplicates[0]
                })
            else:
                non_duplicates.append(place)
        
        # Store the segregated data in the database
        import_data.json_data = {
            'duplicates': duplicates,
            'non_duplicates': non_duplicates
        }
        db.session.commit()
    
    # If there are duplicates, show the duplicates review page
    if duplicates:
        return render_template('review_duplicates.html', duplicates=duplicates)
    
    # If no duplicates, proceed to normal review
    return render_template('review_import.html', places=non_duplicates)

@entities_bp.route('/confirm-import', methods=['POST'])
@login_required
def confirm_import():
    # Get the import ID from session
    import_id = session.get('current_import_id')
    if not import_id:
        flash('No data to import. Please import a CSV file first.', 'error')
        return redirect(url_for('entities.import_places'))
    
    # Get the import data from database
    import_data = db.session.get(ImportData, import_id)
    if not import_data or import_data.user_id != current_user.id:
        flash('Import data not found or expired.', 'error')
        return redirect(url_for('entities.import_places'))
    
    data = import_data.json_data
    if not data:
        flash('No data to import.', 'error')
        return redirect(url_for('entities.import_places'))
    
    try:
        entities_added = 0
        # Get the non-duplicates from the data
        places_to_import = data.get('non_duplicates', [])
        
        for place in places_to_import:
            if not place.get('name'):  # Skip entries with empty names
                continue
                
            # Ensure user_id is set for each imported entity
            place['user_id'] = current_user.id
            entity = Entity(**place)
            db.session.add(entity)
            entities_added += 1
        
        db.session.commit()
        
        # Clean up the import data
        db.session.delete(import_data)
        db.session.commit()
        
        # Clear the import ID from session
        session.pop('current_import_id', None)
        
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
                        return 3  # Good rating for positive boolean
                    if val in ['false', 'f', 'no', 'n', '0']:
                        return 1  # Bad rating for negative boolean
                    
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
            
            # Create a new import record in the database
            import_id = str(uuid.uuid4())
            expires_at = datetime.utcnow() + timedelta(hours=1)  # Data expires in 1 hour
            
            import_data = ImportData(
                id=import_id,
                user_id=current_user.id,
                json_data=parsed_entities,  # Use json_data property instead of data
                expires_at=expires_at
            )
            db.session.add(import_data)
            db.session.commit()
            
            # Store only the import ID in the session
            session['current_import_id'] = import_id
            
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
    # Get all places the user owns, has shared with them, or are public
    places = Entity.query.filter(
        db.or_(
            Entity.user_id == current_user.id,
            Entity.is_public == True,
            Entity.shared_with.contains([current_user.id])
        )
    ).order_by(
        Entity.visited.asc(),  # First sort by visited (True first)
        Entity.updated_at.desc(),  # Then by most recently updated
        Entity.rating.desc().nullsfirst(),  # Then by rating (highest first, nulls before non-nulls)
        Entity.category,  # Then by category alphabetically
        Entity.name  # Finally by name alphabetically
    ).all()
    return render_template('places.html', places=places)

def get_open_entities(current_time, current_day, current_hour, debug=False):
    """
    Get all entities that are currently open based on operating hours.
    
    Args:
        current_time: datetime object representing the current time
        current_day: lowercase string of current day (e.g., 'monday')
        current_hour: integer representing current hour (0-23)
        debug: boolean to enable debug logging
    
    Returns:
        list of Entity objects that are currently open
    """
    # Query all entities that might be available
    available_entities = Entity.query.filter(
        db.or_(
            Entity.user_id == current_user.id,
            Entity.is_public == True,
            Entity.shared_with.contains([current_user.id])
        )
    ).all()

    # Debug print all operating hours
    if debug:
        current_app.logger.debug("Available entities:")
        for entity in available_entities:
            current_app.logger.debug(f"Entity: {entity.name} - Operating hours: {entity.operating_hours}")
    
    # Filter for entities that are currently open based on operating hours
    open_entities = []
    for entity in available_entities:
        is_open = False
        if entity.operating_hours and current_day in entity.operating_hours:
            hours = entity.operating_hours[current_day]
            if hours and 'open' in hours and 'close' in hours:
                try:
                    open_hour = int(hours['open'].split(':')[0])
                    close_hour = int(hours['close'].split(':')[0])
                    # Handle cases where closing time is past midnight
                    if close_hour < open_hour:
                        close_hour += 24
                    if open_hour <= current_hour < close_hour:
                        is_open = True
                    elif debug:
                        current_app.logger.debug(f"Not open: {entity.name} - {open_hour} <= {current_hour} < {close_hour}")
                except (ValueError, IndexError):
                    # If hours are invalid, assume it's open
                    if debug:
                        current_app.logger.debug(f"Invalid hours for {entity.name}: {hours}")
                    is_open = True
            else:
                # If hours are missing open/close times, assume it's open
                if debug:
                    current_app.logger.debug(f"Missing hours for {entity.name}")
                is_open = True
        else:
            # If no operating hours specified, assume it's open
            if debug:
                current_app.logger.debug(f"No hours specified for {entity.name}")
            is_open = True
        
        if is_open:
            open_entities.append(entity)

    if debug:
        current_app.logger.debug("Open entities:")
        for entity in open_entities:
            current_app.logger.debug(f"Entity: {entity.name} - Operating hours: {entity.operating_hours}")

    return open_entities

@entity_api_bp.route('/entities/available')
@login_required
def api_available_entities():
    """API endpoint for available entities with smart sorting"""
    # Get hour key for caching
    hour_key = get_hour_key(current_user.id)
    
    # Get sorted entities using hour-based caching
    sorted_entities = get_sorted_available_entities(hour_key, current_user.id)
    
    # Get dashboard suggestions
    dashboard_suggestions = get_dashboard_suggestions(sorted_entities)
    
    # Convert to dictionary format
    result = {
        'owned': [e.to_dict() for e in sorted_entities['owned']],
        'shared': [e.to_dict() for e in sorted_entities['shared']],
        'public': [e.to_dict() for e in sorted_entities['public']],
        'dashboard_suggestions': [e.to_dict() for e in dashboard_suggestions],
        'hour_key': hour_key
    }
    
    return jsonify(result)

@entities_bp.route('/available')
@login_required
def list_available():
    """Show expanded view of all available places"""
    # Get hour key for caching
    hour_key = get_hour_key(current_user.id)
    
    # Get sorted entities using hour-based caching
    sorted_entities = get_sorted_available_entities(hour_key, current_user.id)
    
    return render_template(
        'entities/available.html',
        entities=sorted_entities,
        hour_key=hour_key  # For displaying last update time
    )

@entity_api_bp.route('/entities/remove-from-import/<int:index>', methods=['POST'])
@login_required
def remove_from_import(index):
    # Get the import ID from session
    import_id = session.get('current_import_id')
    if not import_id:
        return jsonify({'success': False, 'error': 'No active import found'})
    
    # Get the import data from database
    import_data = db.session.get(ImportData, import_id)
    if not import_data or import_data.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Import data not found or expired'})
    
    data = import_data.json_data
    non_duplicates = data.get('non_duplicates', [])
    
    try:
        if 0 <= index < len(non_duplicates):
            non_duplicates.pop(index)
            import_data.json_data = {'non_duplicates': non_duplicates}
            db.session.commit()
            return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': False, 'error': 'Invalid index'})

@entity_api_bp.route('/entities/handle-duplicate/<int:index>', methods=['POST'])
@login_required
def handle_duplicate(index):
    print("\nDebug - Starting handle_duplicate function")
    
    # Get the import ID from session
    import_id = session.get('current_import_id')
    print(f"Debug - Import ID from session: {import_id}")
    if not import_id:
        return jsonify({'success': False, 'error': 'No active import found'})
    
    # Get the import data from database
    import_data = db.session.get(ImportData, import_id)
    print(f"Debug - Found import data: {import_data is not None}")
    if not import_data or import_data.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Import data not found or expired'})
    
    data = import_data.json_data
    duplicates = data.get('duplicates', [])
    non_duplicates = data.get('non_duplicates', [])
    
    print(f"Debug - Current data state:")
    print(f"  - Number of duplicates: {len(duplicates)}")
    print(f"  - Number of non-duplicates: {len(non_duplicates)}")
    print(f"  - Duplicates content: {duplicates}")
    
    # Validate index
    if not duplicates:
        print("Debug - No duplicates to process")
        return jsonify({'success': False, 'error': 'No duplicates to process'})
    
    if index < 0 or index >= len(duplicates):
        print(f"Debug - Invalid index {index} for duplicates length {len(duplicates)}")
        return jsonify({'success': False, 'error': 'Invalid duplicate index'})
    
    duplicate = duplicates[index]
    action = request.json.get('action')
    print(f"Debug - Processing action: {action}")
    print(f"Debug - Duplicate being processed: {duplicate}")
    
    try:
        if action == 'skip':
            print("Debug - Executing skip action")
            print(f"Debug - Before skip: {len(duplicates)} duplicates")
            # Simply remove from duplicates list
            duplicates.pop(index)
            print(f"Debug - After skip: {len(duplicates)} duplicates")
            
        elif action == 'update':
            # Update existing entity with new data
            existing_id = duplicate['existing'].get('id')
            if not existing_id:
                return jsonify({'success': False, 'error': 'Invalid existing entity'})
                
            existing_entity = Entity.query.get(existing_id)
            if existing_entity and existing_entity.user_id == current_user.id:
                new_data = duplicate['new']
                for key, value in new_data.items():
                    if key not in ['id', 'user_id', 'created_at', 'updated_at'] and value is not None:
                        setattr(existing_entity, key, value)
                db.session.commit()
            
            # Remove from duplicates list
            duplicates.pop(index)
            
        elif action == 'import':
            # Move to non-duplicates list
            non_duplicates.append(duplicate['new'])
            # Remove from duplicates list
            duplicates.pop(index)
            
        else:
            print(f"Debug - Invalid action: {action}")
            return jsonify({'success': False, 'error': 'Invalid action'})
        
        # Update the data in the database
        print("Debug - Updating database with new data state")
        import_data.json_data = {
            'duplicates': duplicates,
            'non_duplicates': non_duplicates
        }
        db.session.commit()
        print("Debug - Database update complete")
        
        # If no more duplicates, prepare for redirect
        if not duplicates:
            return jsonify({'success': True, 'redirect': url_for('entities.review_import')})
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Debug - Error occurred: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@entities_bp.route('/review-non-duplicates')
@login_required
def review_non_duplicates():
    """Review only non-duplicate entries"""
    # Get the import ID from session
    import_id = session.get('current_import_id')
    if not import_id:
        flash('No data to review. Please import a CSV file first.', 'error')
        return redirect(url_for('entities.import_places'))
    
    # Get the import data from database
    import_data = db.session.get(ImportData, import_id)
    if not import_data or import_data.user_id != current_user.id:
        flash('Import data not found or expired.', 'error')
        return redirect(url_for('entities.import_places'))
    
    data = import_data.json_data
    non_duplicates = data.get('non_duplicates', [])
    
    if not non_duplicates:
        flash('No non-duplicate entries to review.', 'warning')
        return redirect(url_for('entities.import_places'))
    
    # Update the data to only include non-duplicates
    import_data.json_data = {'non_duplicates': non_duplicates}
    db.session.commit()
    
    return render_template('review_import.html', places=non_duplicates)

@entities_bp.route('/review-all')
@login_required
def review_all():
    """Review all remaining entries (non-duplicates and unhandled duplicates)"""
    # Get the import ID from session
    import_id = session.get('current_import_id')
    if not import_id:
        flash('No data to review. Please import a CSV file first.', 'error')
        return redirect(url_for('entities.import_places'))
    
    # Get the import data from database
    import_data = db.session.get(ImportData, import_id)
    if not import_data or import_data.user_id != current_user.id:
        flash('Import data not found or expired.', 'error')
        return redirect(url_for('entities.import_places'))
    
    data = import_data.json_data
    duplicates = data.get('duplicates', [])
    non_duplicates = data.get('non_duplicates', [])
    
    # Combine all entries for review
    all_entries = non_duplicates + [d['new'] for d in duplicates]
    
    if not all_entries:
        flash('No entries to review.', 'warning')
        return redirect(url_for('entities.import_places'))
    
    # Update the data to include all entries
    import_data.json_data = {'non_duplicates': all_entries}
    db.session.commit()
    
    return render_template('review_import.html', places=all_entries)

@entities_bp.route('/edit-place/<int:entity_id>', methods=['GET', 'POST'])
@login_required
def edit_place(entity_id):
    entity = Entity.query.get_or_404(entity_id)
    
    # Check if user can edit this entity
    if not entity.can_edit(current_user.id):
        flash('You do not have permission to edit this place.', 'error')
        return redirect(url_for('entities.list_places'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category')
        location = request.form.get('location')
        contact_info = request.form.get('contact_info')
        description = request.form.get('description')
        tags = request.form.get('tags', '').split(',') if request.form.get('tags') else []
        visited = 'visited' in request.form
        rating_str = request.form.get('rating')

        # Validate rating
        rating = None
        if rating_str:
            try:
                rating = int(rating_str)
                if rating < 0 or rating > 4:
                    flash('Invalid rating value. Must be between 0 and 4.')
                    return render_template('edit_place.html', place=entity), 400
            except ValueError:
                flash('Invalid rating value. Must be a number.')
                return render_template('edit_place.html', place=entity), 400

        # If a valid rating is provided, automatically set visited to True
        if rating is not None:
            visited = True

        # Rest of validation and entity update
        if not name:
            flash('Name is required.')
            return render_template('edit_place.html', place=entity), 400

        # Initialize properties dictionary
        properties = entity.properties or {}
        
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

        # Add visibility handling
        is_public = 'is_public' in request.form
        
        try:
            # Update entity
            entity.name = name
            entity.category = category
            entity.operating_hours = operating_hours
            entity.location = location
            entity.contact_info = contact_info
            entity.description = description
            entity.tags = tags
            entity.visited = visited
            entity.rating = rating
            entity.properties = properties
            entity.is_public = is_public

            db.session.commit()
            flash('Place updated successfully!', 'success')
            return redirect(url_for('entities.list_places'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating place: {str(e)}', 'error')
            return render_template('edit_place.html', place=entity)

    return render_template('edit_place.html', place=entity)

@entities_bp.route('/<int:entity_id>/share', methods=['POST'])
@login_required
def share_place(entity_id):
    current_app.logger.debug(f"Share place route called for entity_id: {entity_id}")
    current_app.logger.debug(f"Request form data: {request.form}")
    
    entity = Entity.query.get_or_404(entity_id)
    current_app.logger.debug(f"Found entity: {entity.name} (owned by user_id: {entity.user_id})")
    current_app.logger.debug(f"Current user_id: {current_user.id}")
    
    if entity.user_id != current_user.id:
        current_app.logger.warning(f"User {current_user.id} attempted to modify sharing settings for entity {entity_id} owned by user {entity.user_id}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'You do not have permission to share this place.'}), 403
        abort(403)
    
    action = request.form.get('share_action')
    current_app.logger.debug(f"Action requested: {action}")
    
    if action == 'make_public':
        entity.is_public = True
        message = 'Place is now public and can be viewed by all users.'
        current_app.logger.debug("Making entity public")
    elif action == 'make_private':
        entity.is_public = False
        message = 'Place is now private.'
        current_app.logger.debug("Making entity private")
    else:
        current_app.logger.error(f"Invalid action received: {action}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Invalid action.'}), 400
        abort(400)
    
    db.session.commit()
    current_app.logger.debug("Changes committed to database")
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'message': message,
            'is_public': entity.is_public
        })
    
    flash(message, 'success')
    return redirect(url_for('entities.list_places'))

@entities_bp.route('/share-with/<int:entity_id>', methods=['POST'])
@login_required
def share_with_user(entity_id):
    entity = Entity.query.get_or_404(entity_id)
    
    # Ensure user owns this entity
    if entity.user_id != current_user.id:
        flash('You do not have permission to share this place.', 'error')
        return redirect(url_for('entities.list_places'))
    
    username = request.form.get('username')
    if not username:
        flash('Username is required.', 'error')
        return redirect(url_for('entities.list_places'))
    
    # Find the user to share with
    from ..models import User
    user_to_share = User.query.filter_by(username=username).first()
    if not user_to_share:
        flash(f'User "{username}" not found.', 'error')
        return redirect(url_for('entities.list_places'))
    
    if user_to_share.id == current_user.id:
        flash('You cannot share with yourself.', 'error')
        return redirect(url_for('entities.list_places'))
    
    if entity.share_with(user_to_share.id):
        flash(f'Place shared with {username}.', 'success')
    else:
        flash(f'Place is already shared with {username}.', 'info')
    
    db.session.commit()
    return redirect(url_for('entities.list_places'))

@entities_bp.route('/unshare-with/<int:entity_id>', methods=['POST'])
@login_required
def unshare_with_user(entity_id):
    entity = Entity.query.get_or_404(entity_id)
    
    # Ensure user owns this entity
    if entity.user_id != current_user.id:
        flash('You do not have permission to modify sharing settings.', 'error')
        return redirect(url_for('entities.list_places'))
    
    user_id = request.form.get('user_id')
    if not user_id:
        flash('User ID is required.', 'error')
        return redirect(url_for('entities.list_places'))
    
    try:
        user_id = int(user_id)
    except ValueError:
        flash('Invalid user ID.', 'error')
        return redirect(url_for('entities.list_places'))
    
    if entity.unshare_with(user_id):
        flash('User removed from sharing list.', 'success')
    else:
        flash('User was not in the sharing list.', 'info')
    
    db.session.commit()
    return redirect(url_for('entities.list_places'))

# Cache results for 1 hour
@lru_cache(maxsize=128)
def get_hour_key(user_id):
    """Generate a cache key based on the current hour and user ID"""
    now = datetime.now()
    return f"{now.strftime('%Y%m%d%H')}_{user_id}"

@lru_cache(maxsize=128)
def get_sorted_available_entities(hour_key, user_id):
    """Get all available entities and sort them based on relevance, status, and ratings"""
    # Get current time info for filtering
    current_time = datetime.now(Utils.get_user_timezone())
    current_day = current_time.strftime('%A').lower()
    current_hour = current_time.hour
    
    # Get open entities
    entities = get_open_entities(current_time, current_day, current_hour)
    
    # Filter out poorly rated places (ratings 0-1)
    entities = [e for e in entities if e.rating is None or e.rating > 1]
    
    # Group entities by ownership/sharing status
    owned = [e for e in entities if e.user_id == user_id]
    shared = [e for e in entities if e.user_id != user_id and not e.is_public]
    public = [e for e in entities if e.user_id != user_id and e.is_public]
    
    # Calculate weights for each entity based on rating
    def get_weight(entity):
        base_weight = {
            'owned': 0.5,
            'shared': 0.3,
            'public': 0.2
        }
        
        # Determine ownership type
        if entity.user_id == user_id:
            ownership_weight = base_weight['owned']
        elif not entity.is_public:
            ownership_weight = base_weight['shared']
        else:
            ownership_weight = base_weight['public']
        
        # Rating weight with ranges that overlap
        rating_weight = 0.0
        if not entity.visited or entity.rating is None:
            # Unvisited places get a high weight (0.3-0.5)
            rating_weight = 0.3 + (random.random() * 0.2)
        elif entity.rating is not None:
            # Define rating ranges that overlap
            rating_ranges = {
                4: (0.3, 0.5),  # Excellent: 0.3-0.5
                3: (0.2, 0.4),  # Good: 0.2-0.4
                2: (0.1, 0.4)   # OK: 0.1-0.4
            }
            min_weight, max_weight = rating_ranges.get(entity.rating, (0.0, 0.2))
            rating_weight = min_weight + (random.random() * (max_weight - min_weight))
        
        # Add larger random factor (0.0 to 0.4) for more variety
        random_weight = random.random() * 0.4
        
        # Combine weights
        return ownership_weight + rating_weight + random_weight
    
    # Add weights and randomize each list
    def weighted_shuffle(items):
        weighted_items = [(item, get_weight(item)) for item in items]
        # Sort by weight but with randomization influence
        weighted_items.sort(key=lambda x: (-x[1], random.random()))
        return [item for item, _ in weighted_items]
    
    # Apply weighted shuffle to each list
    owned = weighted_shuffle(owned)
    shared = weighted_shuffle(shared)
    public = weighted_shuffle(public)
    
    # Group by category with randomization
    category_groups = {}
    for entity in entities:
        if entity.category not in category_groups:
            category_groups[entity.category] = {
                'owned': [],
                'shared': [],
                'public': []
            }
        
        # Store entity in appropriate category group
        if entity.user_id == user_id:
            category_groups[entity.category]['owned'].append(entity)
        elif not entity.is_public:
            category_groups[entity.category]['shared'].append(entity)
        else:
            category_groups[entity.category]['public'].append(entity)
    
    # Apply weighted shuffle to each category group
    for category in category_groups.values():
        category['owned'] = weighted_shuffle(category['owned'])
        category['shared'] = weighted_shuffle(category['shared'])
        category['public'] = weighted_shuffle(category['public'])
    
    return {
        'owned': owned,
        'shared': shared,
        'public': public,
        'by_category': category_groups,
        'categories': sorted(category_groups.keys())
    }

def get_dashboard_suggestions(sorted_entities, max_items=5):
    """Get a curated list of suggestions for the dashboard widget"""
    import random
    
    # Helper function to get a random item from a list
    def get_random_item(items):
        return random.choice(items) if items else None
    
    # Helper function to get a random item with minimum rating
    def get_random_item_with_min_rating(items, min_rating):
        eligible = [item for item in items if item.rating and item.rating >= min_rating]
        return random.choice(eligible) if eligible else None
    
    suggestions = []
    
    # Always try to include at least one owned place
    if sorted_entities['owned']:
        suggestions.append(get_random_item(sorted_entities['owned']))
    
    # Try to include at least one good or excellent place
    all_places = sorted_entities['owned'] + sorted_entities['shared'] + sorted_entities['public']
    good_place = get_random_item_with_min_rating(all_places, 3)
    if good_place and good_place not in suggestions:
        suggestions.append(good_place)
    
    # Fill remaining slots with a mix of places
    remaining_slots = max_items - len(suggestions)
    if remaining_slots > 0:
        # Create a pool of remaining places
        remaining_pool = []
        for place in all_places:
            if place not in suggestions:
                remaining_pool.append(place)
        
        # Randomly select from remaining pool
        random.shuffle(remaining_pool)
        suggestions.extend(remaining_pool[:remaining_slots])
    
    return suggestions[:max_items]

@entity_api_bp.route('/import/<import_id>/check-duplicates', methods=['GET'])
@login_required
def check_duplicates(import_id):
    """Check for duplicates in the import data"""
    import_data = db.session.get(ImportData, import_id)
    if not import_data or import_data.user_id != current_user.id:
        return jsonify({'error': 'Import not found'}), 404

    # ... rest of the function ...

@entity_api_bp.route('/import/<import_id>/handle-duplicates', methods=['POST'])
@login_required
def handle_duplicates(import_id):
    """Handle duplicate actions"""
    import_data = db.session.get(ImportData, import_id)
    if not import_data or import_data.user_id != current_user.id:
        return jsonify({'error': 'Import not found'}), 404

    # ... rest of the function ... 
