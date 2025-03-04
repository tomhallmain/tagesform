import pytest
from flask import url_for
from app.models import Entity, db
from app.routes.entities import ImportData
import json
from datetime import datetime, timedelta
from io import BytesIO

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
    import_data = ImportData.query.get(import_id)
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
    import_data = ImportData.query.get(import_id)
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
    import_data = ImportData.query.get(import_id)
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
    import_data = ImportData.query.get(import_id)
    assert len(import_data.json_data['duplicates']) == 0
    assert len(import_data.json_data['non_duplicates']) == 1 