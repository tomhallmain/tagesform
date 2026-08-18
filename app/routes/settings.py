from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from ..models import Activity, ScheduleRecord, Entity, UserCalendarDescriptor, DefaultEventDescriptor, db
from ..services import geocoding_service
from ..services.custom_calendar_service import (
    parse_descriptor, regenerate_event_cache_for_user, delete_event_cache_for_user,
    DescriptorValidationError,
)
from ..services.default_event_service import regenerate_event_cache_for_user_default_events
from ..services.suggestion_queue_service import DEFAULT_NEARBY_DISTANCE_MILES
from ..utils.translations import I18N, _

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/')
@login_required
def settings():
    available_languages = I18N.get_available_languages()
    calendar_descriptor = UserCalendarDescriptor.query.filter_by(user_id=current_user.id).first()
    default_event_catalog = DefaultEventDescriptor.query.order_by(
        DefaultEventDescriptor.category, DefaultEventDescriptor.title
    ).all()
    subscribed_default_events = set((current_user.preferences or {}).get('subscribed_default_events') or [])
    return render_template(
        'settings.html',
        preferences=current_user.preferences or {},
        available_languages=available_languages,
        calendar_descriptor=calendar_descriptor,
        default_event_catalog=default_event_catalog,
        subscribed_default_events=subscribed_default_events,
        default_nearby_distance_miles=DEFAULT_NEARBY_DISTANCE_MILES,
    )

@settings_bp.route('/update-notifications', methods=['POST'])
@login_required
def update_notifications():
    # Create updates dictionary from form data
    updates = {
        'email_notifications': 'email_notifications' in request.form,
        'browser_notifications': 'browser_notifications' in request.form
    }
    
    # Update preferences using the new method
    preferences = current_user.update_preferences(updates)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'message': _('Notification settings updated!'),
            'type': 'success'
        })
    
    flash(_('Notification settings updated!'), 'success')
    return redirect(url_for('settings.settings'))

@settings_bp.route('/update-display', methods=['POST'])
@login_required
def update_display():
    # Create updates dictionary from form data
    updates = {
        'default_view': request.form.get('default_view'),
        'time_format': request.form.get('time_format'),
        'dark_mode': request.form.get('dark_mode') == 'true'
    }
    
    # Update preferences using the new method
    preferences = current_user.update_preferences(updates)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'message': _('Display settings updated!'),
            'type': 'success',
            'preferences': preferences
        })
    
    flash(_('Display settings updated!'), 'success')
    return redirect(url_for('settings.settings'))

@settings_bp.route('/update-location', methods=['POST'])
@login_required
def update_location():
    """Save the user's home-base location (freeform text, geocoded
    best-effort against the local gazetteer) and their nearby-distance
    preference, used together by the suggestion queue's entity proximity
    filtering.

    A location that fails to geocode is still saved as free text (so the
    user doesn't lose what they typed), just without coordinates -- the
    user can revise it, or find it later under the "needs location data"
    view now that it's an entity/location the same feature also surfaces
    for entities.
    """
    location = request.form.get('location', '').strip()
    current_user.location = location or None
    geocoding_service.apply_geocode(current_user, location)

    preference_updates = {}
    nearby_distance_miles = request.form.get('nearby_distance_miles', '').strip()
    if nearby_distance_miles:
        try:
            preference_updates['nearby_distance_miles'] = max(0.0, float(nearby_distance_miles))
        except ValueError:
            pass  # leave the existing preference untouched rather than erroring the whole save
    if preference_updates:
        current_user.update_preferences(preference_updates)

    db.session.commit()

    resolved = current_user.latitude is not None
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'message': _('Location settings updated!'),
            'type': 'success',
            'resolved': resolved,
        })

    if location and not resolved:
        flash(_('Location saved, but we could not match it to a known place -- '
                 'try being more specific (e.g. "City, State" or "City, Country").'), 'warning')
    else:
        flash(_('Location settings updated!'), 'success')
    return redirect(url_for('settings.settings'))

@settings_bp.route('/update-weather', methods=['POST'])
@login_required
def update_weather():
    updates = {
        'default_city': request.form.get('default_city'),
        'temperature_unit': request.form.get('temperature_unit')
    }
    
    # Update preferences using the new method
    preferences = current_user.update_preferences(updates)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'message': _('Weather settings updated!'),
            'type': 'success'
        })
    
    flash(_('Weather settings updated!'), 'success')
    return redirect(url_for('settings.settings'))

@settings_bp.route('/update-language', methods=['POST'])
@login_required
def update_language():
    updates = {
        'language': request.form.get('language')
    }
    
    # Update preferences using the new method
    preferences = current_user.update_preferences(updates)

    # The language just changed -- any _() call below (or in a template
    # rendered from this request going forward) must re-resolve against the
    # new preference rather than whatever locale was cached before this.
    I18N.reset_locale_cache()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'message': _('Language settings updated!'),
            'type': 'success'
        })

    flash(_('Language settings updated!'), 'success')
    return redirect(url_for('settings.settings'))

@settings_bp.route('/update-calendar-descriptor', methods=['POST'])
@login_required
def update_calendar_descriptor():
    """Save the user's custom calendar YAML descriptor.

    On success, immediately regenerates that user's Custom Calendar
    EventCache rows for this year and next, so they show up on the
    dashboard right away rather than waiting for the next background
    refresh. On failure, nothing is saved -- the previously-stored,
    still-valid descriptor (if any) and its already-cached events are left
    untouched.
    """
    raw_yaml = request.form.get('raw_yaml', '')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    try:
        entries = parse_descriptor(raw_yaml)
    except DescriptorValidationError as e:
        error_message = str(e)
        if is_ajax:
            return jsonify({'error': error_message}), 400
        flash(error_message, 'error')
        return redirect(url_for('settings.settings'))

    descriptor = UserCalendarDescriptor.query.filter_by(user_id=current_user.id).first()
    if descriptor:
        descriptor.raw_yaml = raw_yaml
        descriptor.last_parse_error = None
    else:
        descriptor = UserCalendarDescriptor(user_id=current_user.id, raw_yaml=raw_yaml)
        db.session.add(descriptor)
    db.session.commit()

    current_year = datetime.utcnow().year
    regenerate_event_cache_for_user(current_user.id, entries, years=[current_year, current_year + 1])

    if is_ajax:
        return jsonify({'message': _('Custom calendar saved!'), 'type': 'success'})

    flash(_('Custom calendar saved!'), 'success')
    return redirect(url_for('settings.settings'))

@settings_bp.route('/delete-calendar-descriptor', methods=['POST'])
@login_required
def delete_calendar_descriptor():
    """Remove the user's custom calendar descriptor and its cached events."""
    descriptor = UserCalendarDescriptor.query.filter_by(user_id=current_user.id).first()
    if descriptor:
        db.session.delete(descriptor)
        db.session.commit()
    delete_event_cache_for_user(current_user.id)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'message': _('Custom calendar removed.'), 'type': 'success'})

    flash(_('Custom calendar removed.'), 'success')
    return redirect(url_for('settings.settings'))

@settings_bp.route('/update-default-events', methods=['POST'])
@login_required
def update_default_events():
    """Save which app-wide catalog events (see DefaultEventDescriptor) the
    user is opted into, and immediately regenerate their Default Event
    EventCache rows for this year and next -- same synchronous-refresh-on-
    save pattern as update_calendar_descriptor.

    Submitted ids that no longer exist in the catalog are silently dropped
    rather than erroring the whole save -- the checkboxes are rendered from
    the live catalog, so a stale id only happens if the catalog changed
    between page load and submit.
    """
    raw_ids = request.form.getlist('subscribed_default_events')
    submitted_ids = {int(raw_id) for raw_id in raw_ids if raw_id.isdigit()}
    valid_ids = [
        row.id for row in DefaultEventDescriptor.query.filter(
            DefaultEventDescriptor.id.in_(submitted_ids)
        ).all()
    ] if submitted_ids else []

    current_user.update_preferences({'subscribed_default_events': valid_ids})

    current_year = datetime.utcnow().year
    regenerate_event_cache_for_user_default_events(
        current_user.id, valid_ids, years=[current_year, current_year + 1]
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'message': _('Default events updated!'), 'type': 'success'})

    flash(_('Default events updated!'), 'success')
    return redirect(url_for('settings.settings'))

@settings_bp.route('/export-data')
@login_required
def export_data():
    # Get all user data
    activities = Activity.query.filter_by(user_id=current_user.id).all()
    schedules = ScheduleRecord.query.filter_by(user_id=current_user.id).all()
    
    data = {
        'user': {
            'username': current_user.username,
            'email': current_user.email,
            'preferences': current_user.preferences
        },
        'activities': [activity.to_dict() for activity in activities],
        'schedules': [schedule.to_dict() for schedule in schedules]
    }
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(data)
    
    response = jsonify(data)
    response.headers['Content-Disposition'] = 'attachment; filename=user_data.json'
    response.headers['Content-Type'] = 'application/json'
    return response

@settings_bp.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    """Delete the user's account and all associated data"""
    from flask_login import logout_user
    
    try:
        # Delete all user's data
        Activity.query.filter_by(user_id=current_user.id).delete()
        ScheduleRecord.query.filter_by(user_id=current_user.id).delete()
        Entity.query.filter_by(user_id=current_user.id).delete()
        
        # Delete the user
        db.session.delete(current_user)
        db.session.commit()
        
        # Log the user out
        logout_user()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'message': _('Account deleted successfully'),
                'type': 'success',
                'redirect': url_for('main.index')
            })
        
        flash(_('Your account has been deleted successfully'), 'success')
        return redirect(url_for('main.index'))
        
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'message': _('Failed to delete account'),
                'type': 'error'
            }), 500
        
        flash(_('Failed to delete account'), 'error')
        return redirect(url_for('settings.settings'))

@settings_bp.route('/settings/clear-data', methods=['POST'])
@login_required
def clear_data():
    """Clear all user data"""
    # Delete all activities
    Activity.query.filter_by(user_id=current_user.id).delete()
    
    # Delete all schedules
    ScheduleRecord.query.filter_by(user_id=current_user.id).delete()
    
    # Delete all entities
    Entity.query.filter_by(user_id=current_user.id).delete()
    
    db.session.commit()
    flash(_('All data cleared successfully'), 'success')
    return redirect(url_for('settings.settings')) 