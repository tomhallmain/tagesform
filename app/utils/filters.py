from app.utils.translations import I18N

_ = I18N._

def title_case(text):
    """Convert text to title case, handling None values"""
    if text is None:
        return None
    return text.title()

def format_rating(rating):
    """Convert integer rating to display text"""
    if rating is None:
        return None
    
    rating_map = {
        4: _('Great'),
        3: _('Good'),
        2: _('Okay'),
        1: _('Bad'),
        0: _('Terrible')
    }
    return rating_map.get(rating, '-') 