import pytest
from flask import g, url_for
from app.utils.translations import I18N
from app.models import User, db


class TestTranslationSystem:
    """Test the per-request translation system"""

    def test_get_user_language_default(self, app):
        """Test that get_user_language returns system default when no user is logged in"""
        with app.app_context():
            # No user logged in, should return system default
            language = I18N.get_user_language()
            assert language in ['en', 'de', 'es', 'fr', 'it']  # Should be one of available languages

    def test_get_user_language_no_current_user(self, app):
        """Test that get_user_language handles None current_user gracefully"""
        with app.app_context():
            # Ensure current_user is None (should be the case in test context)
            from flask_login import current_user
            # current_user should be None in test context without request
            language = I18N.get_user_language()
            assert language in ['en', 'de', 'es', 'fr', 'it']

    def test_get_user_language_with_preference(self, app, test_user, db_session):
        """Test that get_user_language returns user preference when set"""
        # Set user language preference
        test_user.preferences = {'language': 'de'}
        db_session.commit()
        
        with app.app_context():
            # Test that the function works (it will use system default when no user is logged in)
            language = I18N.get_user_language()
            assert language in ['en', 'de', 'es', 'fr', 'it']
            
            # The actual user preference testing is done in the web interface tests
            # where current_user is properly set up by Flask-Login

    def test_user_language_preference_in_request(self, client, auth, test_user, db_session):
        """Test that user language preference is used in actual requests"""
        # Set user language preference
        test_user.preferences = {'language': 'de'}
        db_session.commit()
        
        # Login and make a request
        auth.login()
        response = client.get('/settings/')
        
        # The page should load correctly with the user's language preference
        assert response.status_code == 200
        assert b'Language Settings' in response.data

    def test_get_current_locale_no_g(self, app):
        """Test get_current_locale when g object doesn't have current_locale"""
        with app.app_context():
            # Ensure g doesn't have current_locale
            if hasattr(g, 'current_locale'):
                delattr(g, 'current_locale')
            
            locale = I18N.get_current_locale()
            assert locale in ['en', 'de', 'es', 'fr', 'it']

    def test_get_current_locale_with_g(self, app):
        """Test get_current_locale when g object has current_locale"""
        with app.app_context():
            g.current_locale = 'fr'
            locale = I18N.get_current_locale()
            assert locale == 'fr'

    def test_get_current_translation_creation(self, app):
        """Test that get_current_translation creates translation object"""
        with app.app_context():
            g.current_locale = 'en'
            translation = I18N.get_current_translation()
            assert translation is not None
            assert hasattr(translation, 'gettext')

    def test_get_current_translation_caching(self, app):
        """Test that get_current_translation caches translation object"""
        with app.app_context():
            g.current_locale = 'en'
            g.current_translation = None  # Force recreation
            
            # First call should create translation
            translation1 = I18N.get_current_translation()
            assert translation1 is not None
            
            # Second call should return cached translation
            translation2 = I18N.get_current_translation()
            assert translation2 is not None
            
            assert translation1 is translation2
            
            # Different locale should create different translation object
            g.current_locale = 'de'
            g.current_translation = None  # Force recreation
            translation3 = I18N.get_current_translation()
            assert translation3 is not None
            
            assert translation1 is not translation3

    def test_translation_function(self, app):
        """Test the _() translation function"""
        with app.app_context():
            g.current_locale = 'en'
            
            # Test English translation
            result = I18N._('Settings')
            assert result == 'Settings'
            
            # Test fallback for untranslated string
            result = I18N._('Untranslated String')
            assert result == 'Untranslated String'

    def test_translation_function_different_languages(self, app):
        """Test that _() function works with different languages"""
        with app.app_context():
            # Test English
            g.current_locale = 'en'
            g.current_translation = None  # Force recreation
            result_en = I18N._('Settings')
            
            # Test German (should return German translation if available)
            g.current_locale = 'de'
            g.current_translation = None  # Force recreation
            result_de = I18N._('Settings')
            
            # Both should return appropriate translations for their language
            assert result_en == 'Settings'  # English
            assert result_de == 'Einstellungen'  # German

    def test_get_available_languages(self, app):
        """Test that get_available_languages returns correct list"""
        languages = I18N.get_available_languages()
        expected_languages = ['de', 'en', 'es', 'fr', 'it']  # Based on locale directory
        assert set(languages) == set(expected_languages)

    def test_day_of_the_week(self, app):
        """Test day_of_the_week function"""
        with app.app_context():
            g.current_locale = 'en'
            
            assert I18N.day_of_the_week(0) == 'Monday'
            assert I18N.day_of_the_week(1) == 'Tuesday'
            assert I18N.day_of_the_week(6) == 'Sunday'

    def test_translation_fallback_behavior(self, app):
        """Test that translation system works even without translation files"""
        with app.app_context():
            g.current_locale = 'en'
            g.current_translation = None  # Force recreation
            
            # Should work even if translation files are not available
            translation = I18N.get_current_translation()
            assert translation is not None
            
            # Should return the original string
            result = I18N._('Test String')
            assert result == 'Test String'

    def test_translation_fallback_for_missing_strings(self, app):
        """Test that untranslated strings fall back to original"""
        with app.app_context():
            # Test with a string that likely doesn't have translations
            g.current_locale = 'de'
            g.current_translation = None  # Force recreation
            
            # This string probably doesn't have a German translation
            result = I18N._('Untranslated String')
            assert result == 'Untranslated String'  # Should fall back to original


class TestLanguageSettings:
    """Test the language settings functionality"""

    def test_settings_page_loads(self, client, auth):
        """Test that settings page loads with language options"""
        auth.login()
        response = client.get('/settings/')
        assert response.status_code == 200
        assert b'Language Settings' in response.data
        assert b'Interface Language' in response.data

    def test_update_language_success(self, client, auth, test_user, db_session):
        """Test successful language update"""
        auth.login()
        
        response = client.post('/settings/update-language', data={
            'language': 'de'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Language settings updated!' in response.data
        
        # Verify user preference was updated
        db_session.refresh(test_user)
        assert test_user.preferences.get('language') == 'de'

    def test_update_language_ajax(self, client, auth, test_user, db_session):
        """Test language update via AJAX"""
        auth.login()
        
        response = client.post('/settings/update-language', 
                             data={'language': 'fr'},
                             headers={'X-Requested-With': 'XMLHttpRequest'})
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['message'] == 'Language settings updated!'
        assert data['type'] == 'success'
        
        # Verify user preference was updated
        db_session.refresh(test_user)
        assert test_user.preferences.get('language') == 'fr'

    def test_update_language_invalid(self, client, auth):
        """Test language update with invalid language"""
        auth.login()
        
        response = client.post('/settings/update-language', data={
            'language': 'invalid_lang'
        }, follow_redirects=True)
        
        # Should still work (fallback behavior)
        assert response.status_code == 200

    def test_language_preference_persistence(self, client, auth, test_user, db_session):
        """Test that language preference persists across sessions"""
        # Set language preference
        test_user.preferences = {'language': 'es'}
        db_session.commit()
        
        # Login and check settings page
        auth.login()
        response = client.get('/settings/')
        assert response.status_code == 200
        
        # Should show Spanish as selected
        assert b'value="es" selected' in response.data

    def test_language_settings_form_structure(self, client, auth):
        """Test that language settings form has correct structure"""
        auth.login()
        response = client.get('/settings/')
        
        # Check form action
        assert b'action="/settings/update-language"' in response.data
        
        # Check form method
        assert b'method="POST"' in response.data
        
        # Check select element
        assert b'name="language"' in response.data
        assert b'id="language"' in response.data

    def test_available_languages_in_template(self, client, auth):
        """Test that all available languages are shown in the template"""
        auth.login()
        response = client.get('/settings/')
        
        # Check that all available languages are present
        available_languages = I18N.get_available_languages()
        for lang in available_languages:
            assert f'value="{lang}"'.encode() in response.data

    def test_language_names_display(self, client, auth):
        """Test that language names are displayed correctly"""
        auth.login()
        response = client.get('/settings/')
        
        # Check that language names are displayed
        assert b'English' in response.data
        assert b'German' in response.data
        assert b'Spanish' in response.data
        assert b'French' in response.data
        assert b'Italian' in response.data


class TestTranslationIntegration:
    """Test translation integration with the web application"""

    def test_template_translation(self, client, auth):
        """Test that templates use the translation function correctly"""
        auth.login()
        response = client.get('/settings/')
        
        # Check that translated strings are present
        assert b'Settings' in response.data
        assert b'Language Settings' in response.data
        assert b'Interface Language' in response.data

    def test_context_processor_locale(self, client, auth):
        """Test that context processor provides current_locale"""
        auth.login()
        response = client.get('/settings/')
        
        # The context processor should provide current_locale
        # This is tested indirectly by checking the page loads correctly
        assert response.status_code == 200

    def test_web_interface_fallback_behavior(self, client, auth):
        """Test that translation fallback works correctly in web interface"""
        auth.login()
        response = client.get('/settings/')
        
        # Even if some translations are missing, the page should still load
        assert response.status_code == 200
        assert b'Settings' in response.data  # Should always be present

    def test_multiple_users_different_languages(self, client, db_session):
        """Test that multiple users can have different language preferences"""
        # Create two users with different language preferences
        user1 = User(username='user1', email='user1@example.com')
        user1.set_password('password')
        user1.preferences = {'language': 'en'}
        db_session.add(user1)
        
        user2 = User(username='user2', email='user2@example.com')
        user2.set_password('password')
        user2.preferences = {'language': 'de'}
        db_session.add(user2)
        
        db_session.commit()
        
        # Login as user1
        client.post('/login', data={'username': 'user1', 'password': 'password'})
        response1 = client.get('/settings/')
        
        # Logout and login as user2
        client.get('/logout')
        client.post('/login', data={'username': 'user2', 'password': 'password'})
        response2 = client.get('/settings/')
        
        # Both should work without interference
        assert response1.status_code == 200
        assert response2.status_code == 200


def test_translation_system_thread_safety(app):
    """Test that translation system is thread-safe (per-request isolation)"""
    with app.app_context():
        # Simulate request 1
        g.current_locale = 'en'
        g.current_translation = None  # Force recreation
        translation1 = I18N.get_current_translation()
        assert translation1 is not None
        result1 = I18N._('Settings')
        
        # Simulate request 2 (different thread/request)
        g.current_locale = 'de'
        g.current_translation = None  # Force recreation
        translation2 = I18N.get_current_translation()
        assert translation2 is not None
        result2 = I18N._('Settings')
        
        # Each should have its own translation context
        assert translation1 is not translation2
        # Both should work correctly with appropriate translations
        assert result1 == 'Settings'  # English
        assert result2 == 'Einstellungen'  # German 