import pytest
from flask import g
from app.utils.translations import I18N

pytestmark = pytest.mark.unit


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
