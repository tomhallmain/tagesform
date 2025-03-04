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
        4: 'Great',
        3: 'Good',
        2: 'Okay',
        1: 'Bad',
        0: 'Terrible'
    }
    return rating_map.get(rating, '-') 