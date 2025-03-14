from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from ..models import Schedule, db
from ..services.integration_service import integration_service

# Create two separate blueprints
schedules_bp = Blueprint('schedules', __name__)  # For schedule pages
schedule_api_bp = Blueprint('schedule_api', __name__, url_prefix='/api')  # For schedule API endpoints

@schedules_bp.route('/new-schedule', methods=['GET', 'POST'])
@login_required
def new_schedule():
    if request.method == 'POST':
        # Get form data
        title = request.form.get('title')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        recurrence = request.form.get('recurrence')
        category = request.form.get('category')
        location = request.form.get('location')
        description = request.form.get('description')

        # Collect validation errors
        has_errors = False
        if not title:
            flash('Title is required', 'error')
            has_errors = True

        if not start_time or not end_time:
            flash('Start time and end time are required', 'error')
            has_errors = True

        if has_errors:
            return render_template('new_schedule.html'), 400

        # Validate time format
        try:
            start_minutes = Schedule.time_to_minutes(start_time)
            end_minutes = Schedule.time_to_minutes(end_time)
        except ValueError:
            flash('Invalid time format. Please use HH:MM format', 'error')
            return render_template('new_schedule.html'), 400

        # Create new schedule with times converted to minutes
        schedule = Schedule(
            title=title,
            start_time=start_minutes,
            end_time=end_minutes,
            recurrence=recurrence,
            category=category,
            location=location,
            description=description,
            user_id=current_user.id
        )

        db.session.add(schedule)
        db.session.commit()

        flash('Schedule created successfully!', 'success')
        return redirect(url_for('main.index'))

    return render_template('new_schedule.html')

@schedules_bp.route('/schedules')
@login_required
def list_schedules():
    """List all schedules for the current user"""
    schedules = Schedule.query.filter_by(user_id=current_user.id).all()
    return render_template('schedules.html', schedules=schedules)

@schedule_api_bp.route('/schedule/current')
@login_required
def get_current_schedule():
    """Get the currently active schedule"""
    schedule = integration_service.get_current_schedule()
    return jsonify(schedule) 