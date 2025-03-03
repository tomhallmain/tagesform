def title_case(text):
    """Convert text to title case, handling None values"""
    if text is None:
        return None
    return text.title() 