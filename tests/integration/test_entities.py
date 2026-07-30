import pytest
from flask import url_for
from app.models import Entity, db
from app.routes.entities import ImportData
import json
from datetime import datetime, timedelta
from io import BytesIO

from helpers import assert_in_response, expected_text

pytestmark = pytest.mark.integration

def test_add_place_duplicate_check(client, auth, db_session):
    """Test duplicate checking when adding a place"""
    # Login
    auth.login()
    
    # Create a test place
    test_place = Entity(
        name="Test Restaurant",
        category="restaurant",
        location="123 Test St",
        user_id=1
    )
    db_session.add(test_place)
    db_session.commit()
    
    # Make POST request to check for duplicates
    response = client.post('/add-place', 
                         data={
                             'name': 'Test Restaurant',
                             'category': 'restaurant',
                             'location': '123 Test St'
                         },
                         headers={'X-Requested-With': 'XMLHttpRequest'})
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['has_duplicates'] is True
    assert len(data['duplicates']) == 1
    assert data['duplicates'][0]['name'] == 'Test Restaurant'
    assert data['duplicates'][0]['category'] == 'restaurant'
    assert data['duplicates'][0]['location'] == '123 Test St'

def _create_other_user_with_public_place(db_session, name='Test Restaurant', category='restaurant',
                                          location='123 Test St', is_public=True):
    """Create a second user owning a place, for cross-user duplicate-check tests."""
    from app.models import User
    other_user = User(username='other_user', email='other@example.com')
    other_user.set_password('password')
    db_session.add(other_user)
    db_session.commit()

    other_place = Entity(
        name=name,
        category=category,
        location=location,
        is_public=is_public,
        user_id=other_user.id
    )
    db_session.add(other_place)
    db_session.commit()
    return other_user, other_place

def test_add_place_duplicate_check_includes_public_places_when_making_public(client, auth, db_session):
    """A new place being made public should be checked against other users' public places too."""
    auth.login()
    _create_other_user_with_public_place(db_session)

    response = client.post('/add-place',
                         data={
                             'name': 'Test Restaurant',
                             'category': 'restaurant',
                             'location': '123 Test St',
                             'is_public': 'on'
                         },
                         headers={'X-Requested-With': 'XMLHttpRequest'})

    assert response.status_code == 200
    data = response.get_json()
    assert data['has_duplicates'] is True
    assert len(data['duplicates']) == 1
    assert data['duplicates'][0]['name'] == 'Test Restaurant'

def test_add_place_duplicate_check_excludes_public_places_when_staying_private(client, auth, db_session):
    """A new place staying private should only be checked against the current user's own places."""
    auth.login()
    _create_other_user_with_public_place(db_session)

    response = client.post('/add-place',
                         data={
                             'name': 'Test Restaurant',
                             'category': 'restaurant',
                             'location': '123 Test St'
                             # is_public omitted -- staying private
                         },
                         headers={'X-Requested-With': 'XMLHttpRequest'})

    assert response.status_code == 200
    data = response.get_json()
    assert data['has_duplicates'] is False

def test_add_place_confirm_duplicate_bypasses_check(client, auth, test_user, db_session):
    """The 'Save as New Entry' resubmission (confirm_duplicate=1) must actually save,
    not hit the same duplicate check and get blocked again."""
    auth.login()
    _create_other_user_with_public_place(db_session)

    response = client.post('/add-place',
                         data={
                             'name': 'Test Restaurant',
                             'category': 'restaurant',
                             'location': '123 Test St',
                             'is_public': 'on',
                             'confirm_duplicate': '1'
                         },
                         follow_redirects=True)

    assert response.status_code == 200
    saved = Entity.query.filter_by(name='Test Restaurant', user_id=test_user.id).first()
    assert saved is not None
    assert saved.is_public is True

def test_import_places_duplicate_check(client, auth, test_user, db_session):
    """Test duplicate checking during CSV import"""
    # Login
    auth.login()
    
    # Create a test place
    test_place = Entity(
        name="Test Restaurant",
        category="restaurant",
        location="123 test st",
        user_id=test_user.id
    )
    db_session.add(test_place)
    db_session.commit()
    
    # Create test CSV data
    csv_data = [
        ['name', 'category', 'location'],
        ['Test Restaurant', 'restaurant', '123 Test St'],
        ['Different Restaurant', 'restaurant', '456 Different St'],
    ]
    
    # Convert to CSV string
    csv_string = '\n'.join(','.join(row) for row in csv_data)
    
    # Create a BytesIO object for the file
    file_data = BytesIO(csv_string.encode('utf-8'))
    
    # Test import
    response = client.post(
        url_for('entities.import_places'),
        data={
            'file': (file_data, 'test.csv')
        },
        content_type='multipart/form-data'
    )
    
    assert response.status_code == 302  # Redirect to review page
    
    # Verify the session was updated
    with client.session_transaction() as sess:
        assert 'current_import_id' in sess
        import_id = sess.get('current_import_id')
    
    # Check the import data in the database
    import_data = db_session.get(ImportData, import_id)
    assert import_data is not None
    assert import_data.user_id == test_user.id
    
    # The data should be a list of parsed entities at this point
    data = import_data.json_data
    assert isinstance(data, list)
    assert len(data) == 2
    
    # Now visit the review page to process duplicates
    response = client.get(url_for('entities.review_import'))
    assert response.status_code == 200
    
    # After review, the data should be processed into duplicates and non_duplicates
    import_data = db_session.get(ImportData, import_id)
    data = import_data.json_data
    print(data)
    assert isinstance(data, dict)
    assert 'duplicates' in data
    assert 'non_duplicates' in data
    assert len(data['duplicates']) == 1
    assert len(data['non_duplicates']) == 1
    
    # Verify duplicate data
    duplicate = data['duplicates'][0]
    assert duplicate['new']['name'] == 'Test Restaurant'
    assert duplicate['existing']['name'] == 'Test Restaurant'
    
    # Verify non-duplicate data
    non_duplicate = data['non_duplicates'][0]
    assert non_duplicate['name'] == 'Different Restaurant'

def test_handle_duplicate_actions(client, auth, test_user, db_session):
    """Test handling duplicate actions during import"""
    # Login
    auth.login()
    
    # Create a test place
    test_place = Entity(
        name="Test Restaurant",
        category="restaurant",
        location="123 test st",
        user_id=test_user.id
    )
    db_session.add(test_place)
    db_session.commit()
    
    # Create import data
    import_id = "test-import-id"
    import_data = ImportData(
        id=import_id,
        user_id=test_user.id,
        json_data={
            'duplicates': [{
                'index': 0,
                'new': {
                    'name': 'Test Restaurant',
                    'category': 'restaurant',
                    'location': '123 test st'
                },
                'existing': {
                    'id': test_place.id,
                    'name': 'Test Restaurant',
                    'category': 'restaurant',
                    'location': '123 test st'
                }
            }],
            'non_duplicates': []
        },
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    db_session.add(import_data)
    db_session.commit()
    
    # Set up the session with the import ID
    with client.session_transaction() as sess:
        sess['current_import_id'] = import_id
    
    # Test skip action
    response = client.post(
        url_for('entity_api.handle_duplicate', index=0),
        json={'action': 'skip'},
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    
    # Verify the duplicate was removed
    import_data = db_session.get(ImportData, import_id)
    assert len(import_data.json_data['duplicates']) == 0
    
    # Test import action
    import_data.json_data = {
        'duplicates': [{
            'index': 0,
            'new': {
                'name': 'Test Restaurant',
                'category': 'restaurant',
                'location': '123 test st'
            },
            'existing': {
                'id': test_place.id,
                'name': 'Test Restaurant',
                'category': 'restaurant',
                'location': '123 test st'
            }
        }],
        'non_duplicates': []
    }
    db_session.commit()
    
    response = client.post(
        url_for('entity_api.handle_duplicate', index=0),
        json={'action': 'import'},
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    
    # Verify the duplicate was moved to non_duplicates
    import_data = db_session.get(ImportData, import_id)
    assert len(import_data.json_data['duplicates']) == 0
    assert len(import_data.json_data['non_duplicates']) == 1

def test_add_place_with_rating(client, auth, db_session):
    """Test adding a place with different rating scenarios"""
    auth.login()

    # Test case 1: Add place with rating - should automatically set visited to true
    response = client.post('/add-place', data={
        'name': 'Excellent Restaurant',  # More distinct name
        'category': 'restaurant',
        'rating': '4',  # Great rating
        'visited': ''  # Even if visited is unchecked, it should be set to true when rating is provided
    })
    assert response.status_code == 302  # Successful redirect
    
    place1 = Entity.query.filter_by(name='Excellent Restaurant').first()
    assert place1 is not None
    assert place1.rating == 4
    assert place1.visited is True  # Should be True because a rating was provided

    # Test case 2: Add place with no rating but marked as visited
    response = client.post('/add-place', data={
        'name': 'Neighborhood Cafe',  # Completely different name
        'category': 'cafe',  # Different category too
        'rating': '',  # No rating
        'visited': 'on'  # Visited (checkbox checked)
    })
    assert response.status_code == 302

    place2 = Entity.query.filter_by(name='Neighborhood Cafe').first()
    assert place2 is not None
    assert place2.rating is None
    assert place2.visited is True

    # Test case 3: Add place with rating and visited explicitly set
    response = client.post('/add-place', data={
        'name': 'Downtown Bar',  # Another distinct name
        'category': 'bar',  # Different category
        'rating': '2',  # OK rating
        'visited': 'on'  # Visited explicitly set
    })
    assert response.status_code == 302

    place3 = Entity.query.filter_by(name='Downtown Bar').first()
    assert place3 is not None
    assert place3.rating == 2
    assert place3.visited is True

def test_edit_place_rating_and_visited(client, auth, test_user, db_session):
    """Test editing a place's rating and visited status"""
    auth.login()

    # Create a test place
    place = Entity(
        name="Test Place",
        category="restaurant",
        rating=None,
        visited=False,
        user_id=test_user.id
    )
    db_session.add(place)
    db_session.commit()

    # Test case 1: Update to add rating - should automatically set visited to true
    response = client.post(f'/edit-place/{place.id}', data={
        'name': 'Test Place',
        'category': 'restaurant',
        'rating': '4',
        'visited': ''  # Even if visited is unchecked, it should be set to true when rating is provided
    })
    assert response.status_code == 302

    place = db_session.get(Entity, place.id)
    assert place.rating == 4
    assert place.visited is True  # Should be True because a rating was provided

    # Test case 2: Update to remove rating but keep visited
    response = client.post(f'/edit-place/{place.id}', data={
        'name': 'Test Place',
        'category': 'restaurant',
        'rating': '',
        'visited': 'on'
    })
    assert response.status_code == 302

    place = db_session.get(Entity, place.id)
    assert place.rating is None
    assert place.visited is True

    # Test case 3: Update to add rating with visited explicitly set
    response = client.post(f'/edit-place/{place.id}', data={
        'name': 'Test Place',
        'category': 'restaurant',
        'rating': '2',
        'visited': 'on'
    })
    assert response.status_code == 302

    place = db_session.get(Entity, place.id)
    assert place.rating == 2
    assert place.visited is True

def test_edit_place_becoming_public_succeeds_without_duplicate(client, auth, test_user, db_session):
    """Making a place public should still save normally when the (now
    widened) duplicate check finds nothing."""
    auth.login()

    place = Entity(name='My Place', category='restaurant', location='1 Main St',
                    is_public=False, user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.post(f'/edit-place/{place.id}', data={
        'name': 'My Place',
        'category': 'restaurant',
        'location': '1 Main St',
        'is_public': 'on'
    })
    assert response.status_code == 302

    place = db_session.get(Entity, place.id)
    assert place.is_public is True

def test_edit_place_no_duplicate_check_when_staying_private(client, auth, test_user, db_session):
    """Editing a place that stays private must not trigger a duplicate check,
    even if a matching public place exists elsewhere."""
    auth.login()
    _create_other_user_with_public_place(db_session, name='My Place', location='1 Main St')

    place = Entity(name='My Place', category='restaurant', location='1 Main St',
                    is_public=False, user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.post(f'/edit-place/{place.id}', data={
        'name': 'My Place',
        'category': 'restaurant',
        'location': '1 Main St',
        'description': 'updated description'
        # is_public omitted -- staying private
    })
    assert response.status_code == 302

    place = db_session.get(Entity, place.id)
    assert place.description == 'updated description'
    assert place.is_public is False

def test_edit_place_no_duplicate_check_when_already_public(client, auth, test_user, db_session):
    """Editing a place that was already public (and stays public) must not
    trigger a duplicate check -- it's not a transition to public."""
    auth.login()
    _create_other_user_with_public_place(db_session, name='My Place', location='1 Main St')

    place = Entity(name='My Place', category='restaurant', location='1 Main St',
                    is_public=True, user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.post(f'/edit-place/{place.id}', data={
        'name': 'My Place',
        'category': 'restaurant',
        'location': '1 Main St',
        'is_public': 'on',
        'description': 'updated description'
    })
    assert response.status_code == 302

    place = db_session.get(Entity, place.id)
    assert place.description == 'updated description'
    assert place.is_public is True

def test_edit_place_duplicate_check_when_becoming_public(client, auth, test_user, db_session):
    """Editing a private place to make it public must be checked against
    other users' public places, and blocked if a match is found."""
    auth.login()
    _create_other_user_with_public_place(db_session, name='My Place', location='1 Main St')

    place = Entity(name='My Place', category='restaurant', location='1 Main St',
                    is_public=False, user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.post(f'/edit-place/{place.id}', data={
        'name': 'My Place',
        'category': 'restaurant',
        'location': '1 Main St',
        'is_public': 'on'
    })
    assert response.status_code == 400

    place = db_session.get(Entity, place.id)
    assert place.is_public is False  # Blocked -- change was not saved

def test_edit_place_duplicate_check_ajax_when_becoming_public(client, auth, test_user, db_session):
    """The AJAX duplicate pre-check (used by the edit form's JS) should
    report the match without saving anything."""
    auth.login()
    _create_other_user_with_public_place(db_session, name='My Place', location='1 Main St')

    place = Entity(name='My Place', category='restaurant', location='1 Main St',
                    is_public=False, user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.post(f'/edit-place/{place.id}', data={
        'name': 'My Place',
        'category': 'restaurant',
        'location': '1 Main St',
        'is_public': 'on'
    }, headers={'X-Requested-With': 'XMLHttpRequest'})

    assert response.status_code == 200
    data = response.get_json()
    assert data['has_duplicates'] is True
    assert len(data['duplicates']) == 1
    assert data['duplicates'][0]['name'] == 'My Place'

    place = db_session.get(Entity, place.id)
    assert place.is_public is False  # AJAX pre-check must not have saved anything

def test_edit_place_confirm_duplicate_bypasses_check(client, auth, test_user, db_session):
    """The 'Save Anyway' resubmission (confirm_duplicate=1) must actually
    save the change, not hit the same duplicate check and get blocked again."""
    auth.login()
    _create_other_user_with_public_place(db_session, name='My Place', location='1 Main St')

    place = Entity(name='My Place', category='restaurant', location='1 Main St',
                    is_public=False, user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.post(f'/edit-place/{place.id}', data={
        'name': 'My Place',
        'category': 'restaurant',
        'location': '1 Main St',
        'is_public': 'on',
        'confirm_duplicate': '1'
    })
    assert response.status_code == 302

    place = db_session.get(Entity, place.id)
    assert place.is_public is True

def test_rating_validation(client, auth):
    """Test validation of rating values"""
    auth.login()

    # Test invalid rating value
    response = client.post('/add-place', data={
        'name': 'Test Place',
        'category': 'restaurant',
        'rating': '5'  # Invalid rating (should be 0-4)
    })
    assert response.status_code == 400
    assert_in_response(expected_text('Invalid rating value. Must be between 0 and 4.'), response)

    # Test non-numeric rating
    response = client.post('/add-place', data={
        'name': 'Test Place',
        'category': 'restaurant',
        'rating': 'invalid'
    })
    assert response.status_code == 400
    assert_in_response(expected_text('Invalid rating value. Must be a number.'), response)

def test_add_place_visibility(client, auth, db_session):
    """Test adding a place with different visibility settings"""
    auth.login()

    # Test case 1: Add place as public
    response = client.post('/add-place', data={
        'name': 'Public Restaurant',
        'category': 'restaurant',
        'is_public': 'on'  # Checkbox checked
    })
    assert response.status_code == 302  # Successful redirect
    
    place1 = Entity.query.filter_by(name='Public Restaurant').first()
    assert place1 is not None
    assert place1.is_public is True

    # Test case 2: Add place as private (default)
    response = client.post('/add-place', data={
        'name': 'Private Restaurant',
        'category': 'restaurant'
        # is_public not included in form data
    })
    assert response.status_code == 302

    place2 = Entity.query.filter_by(name='Private Restaurant').first()
    assert place2 is not None
    assert place2.is_public is False 