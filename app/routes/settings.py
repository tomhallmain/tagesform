from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from ..models import Activity, ScheduleRecord, Entity, db

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/')
@login_required
def settings():
    return render_template('settings.html', preferences=current_user.preferences or {})

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
            'message': 'Notification settings updated!',
            'type': 'success'
        })
    
    flash('Notification settings updated!', 'success')
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
            'message': 'Display settings updated!',
            'type': 'success',
            'preferences': preferences
        })
    
    flash('Display settings updated!', 'success')
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
            'message': 'Weather settings updated!',
            'type': 'success'
        })
    
    flash('Weather settings updated!', 'success')
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
                'message': 'Account deleted successfully',
                'type': 'success',
                'redirect': url_for('main.index')
            })
        
        flash('Your account has been deleted successfully', 'success')
        return redirect(url_for('main.index'))
        
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'message': 'Failed to delete account',
                'type': 'error'
            }), 500
        
        flash('Failed to delete account', 'error')
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
    flash('All data cleared successfully', 'success')
    return redirect(url_for('settings.settings')) 