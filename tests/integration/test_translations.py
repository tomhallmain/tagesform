import pytest
from app.utils.translations import I18N
from app.models import User

from helpers import assert_in_response, expected_text

pytestmark = pytest.mark.integration


class TestLanguageSettings:
    """Test the language settings functionality"""

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
        assert_in_response(expected_text('Language Settings', locale='de'), response)

    def test_settings_page_loads(self, client, auth):
        """Test that settings page loads with language options"""
        auth.login()
        response = client.get('/settings/')
        assert response.status_code == 200
        assert_in_response(expected_text('Language Settings'), response)
        assert_in_response(expected_text('Interface Language'), response)

    def test_update_language_success(self, client, auth, test_user, db_session):
        """Test successful language update"""
        auth.login()

        response = client.post('/settings/update-language', data={
            'language': 'de'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert_in_response('Language settings updated!', response)  # flash(), not translated

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
        assert data['message'] == 'Language settings updated!'  # not translated (see routes/settings.py)
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

        # Should show Spanish as selected (structural attribute, not translated)
        assert_in_response('value="es" selected', response)

    def test_language_settings_form_structure(self, client, auth):
        """Test that language settings form has correct structure"""
        auth.login()
        response = client.get('/settings/')

        # Structural HTML attributes -- not translated
        assert_in_response('action="/settings/update-language"', response)
        assert_in_response('method="POST"', response)
        assert_in_response('name="language"', response)
        assert_in_response('id="language"', response)

    def test_available_languages_in_template(self, client, auth):
        """Test that all available languages are shown in the template"""
        auth.login()
        response = client.get('/settings/')

        # Check that all available languages are present (structural attribute)
        available_languages = I18N.get_available_languages()
        for lang in available_languages:
            assert_in_response(f'value="{lang}"', response, note=f"language option {lang!r}")

    def test_language_names_display(self, client, auth):
        """Test that language names are displayed correctly"""
        auth.login()
        response = client.get('/settings/')

        # Check that language names are displayed
        for name in ('English', 'German', 'Spanish', 'French', 'Italian'):
            assert_in_response(expected_text(name), response, note=f"language name {name!r}")


class TestTranslationIntegration:
    """Test translation integration with the web application"""

    def test_template_translation(self, client, auth):
        """Test that templates use the translation function correctly"""
        auth.login()
        response = client.get('/settings/')

        # Check that translated strings are present
        assert_in_response(expected_text('Settings'), response)
        assert_in_response(expected_text('Language Settings'), response)
        assert_in_response(expected_text('Interface Language'), response)

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
        assert_in_response(expected_text('Settings'), response)  # Should always be present

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
