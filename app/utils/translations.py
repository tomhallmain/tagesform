import gettext
import os
from flask import g, request
from flask_login import current_user

from ..utils.logging_setup import get_logger
from ..utils.utils import Utils

logger = get_logger(__name__)

class I18N:
    localedir = os.path.join(os.path.dirname(os.path.abspath(os.path.dirname(os.path.dirname(__file__)))), 'locale')

    @staticmethod
    def get_user_language():
        """Get the user's preferred language, falling back to system default"""
        # First check if user is logged in and has a language preference
        if current_user and current_user.is_authenticated and current_user.preferences:
            user_lang = current_user.preferences.get('language')
            if user_lang:
                return user_lang
        
        # Fall back to system default
        return Utils.get_default_user_language()

    @staticmethod
    def get_current_locale():
        """Get the current locale for this request"""
        if hasattr(g, 'current_locale'):
            return g.current_locale
        return I18N.get_user_language()

    @staticmethod
    def get_current_translation():
        """Get the current translation object for this request"""
        if hasattr(g, 'current_translation') and g.current_translation is not None:
            return g.current_translation
        
        # Create translation for current request
        locale = I18N.get_current_locale()
        try:
            translation = gettext.translation('base', I18N.localedir, languages=[locale], fallback=True)
            # If translation is None, create a fallback translation
            if translation is None:
                translation = gettext.NullTranslations()
        except Exception as e:
            # If there's any error, use a null translation
            translation = gettext.NullTranslations()
        
        g.current_locale = locale
        g.current_translation = translation
        return translation

    @staticmethod
    def _(s):
        """Translate a string using the current request's language"""
        try:
            translation = I18N.get_current_translation()
            return translation.gettext(s)
        except Exception:
            return s

    @staticmethod
    def day_of_the_week(day_index=0):
        if day_index == 0:
            return I18N._('Monday')
        elif day_index == 1:
            return I18N._('Tuesday')
        elif day_index == 2:
            return I18N._('Wednesday')
        elif day_index == 3:
            return I18N._('Thursday')
        elif day_index == 4:
            return I18N._('Friday')
        elif day_index == 5:
            return I18N._('Saturday')
        else:
            return I18N._('Sunday')

    @staticmethod
    def get_available_languages():
        """Get list of available languages based on locale directory"""
        languages = []
        if os.path.exists(I18N.localedir):
            for item in os.listdir(I18N.localedir):
                item_path = os.path.join(I18N.localedir, item)
                if os.path.isdir(item_path) and item != '__pycache__':
                    # Check if it has LC_MESSAGES directory with base.mo file
                    mo_path = os.path.join(item_path, 'LC_MESSAGES', 'base.mo')
                    if os.path.exists(mo_path):
                        languages.append(item)
        return sorted(languages)

    '''
    TRANSLATION WORKFLOW:
    
    Option 1: Use the custom extraction script (recommended):
        ```python extract_translations.py```
    
    Option 2: Use Babel (if installed):
        ```bash
        pybabel extract -F babel.cfg -k _l -o locale/base.pot .
        ```
    
    Option 3: Use pygettext (requires temporary modification):
        - Temporarily change _() method to use gettext.gettext() directly
        - Run: ```python C:\Python310\Tools\i18n\pygettext.py -d base -o locale\base.pot .```
        - Revert the _() method back to normal
    
    After generating the POT file:
    1. Update PO files for each language in locale/[lang]/LC_MESSAGES/base.po
    2. Compile MO files: ```python C:\Python310\Tools\i18n\msgfmt.py -o locale/[lang]/LC_MESSAGES/base.mo locale/[lang]/LC_MESSAGES/base.po```
    
    The custom extraction script will detect:
    - I18N._('text') calls in Python files
    - {{ _('text') }} calls in Jinja2 templates
    '''
