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
    def reset_locale_cache():
        """Clear the per-request locale/translation cache on `g`.

        get_current_locale()/get_current_translation() cache onto `g` so a
        request doesn't re-resolve the locale on every _() call. That cache
        needs clearing whenever the active user's language preference
        changes within the same request (e.g. right after saving a new
        preference) -- otherwise a _() call later in that same request keeps
        returning the *previous* language instead of the one just selected.
        """
        if hasattr(g, 'current_locale'):
            del g.current_locale
        if hasattr(g, 'current_translation'):
            del g.current_translation

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


# Module-level alias so other modules can do `from ..utils.translations import _`
# instead of importing I18N and aliasing it themselves.
_ = I18N._

'''
NOTE when gathering the translation strings, set _() == to gettext.gettext() instead of the above, and run:

    ```python C:\Python310\Tools\i18n\pygettext.py -d base -o locale\base.pot .```

in the base directory. The POT output file can be used as source for the PO files in each locale.
Run personal script C:\Scripts\i18n_manager.py to generate new PO files and look for invalid translations.

Bonus command:
    ```git diff Tagesform\locale\de\LC_MESSAGES\base.po Tagesform\locale\de\LC_MESSAGES\base1.po | rg -v "^.*#" | rg -C 3 "^(-|\+)"```

Then for each locale once the PO files are set up as desired, run below in the deepest locale directory to produce the MO file from the PO file:
    ```python C:\Python310\Tools\i18n\msgfmt.py -o base.mo base```
'''
