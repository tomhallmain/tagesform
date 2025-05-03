from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from ..models import ScheduleRecord, db
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
        
        # Get month and day pairs for annual dates
        months = request.form.getlist('month[]')
        days = request.form.getlist('day[]')
        annual_dates = []
        if recurrence == 'annual':
            annual_dates = [{'month': int(m), 'day': int(d)} for m, d in zip(months, days)]

        # Collect validation errors
        has_errors = False

        # Get weekday options for weekly schedules
        weekday_options = []
        if recurrence == 'weekly':
            weekday_options = [int(day) for day in request.form.getlist('weekday_options[]')]
            if not weekday_options:
                flash('Please select at least one day of the week for weekly schedules', 'error')
                has_errors = True

        if not title:
            flash('Title is required', 'error')
            has_errors = True

        if not start_time or not end_time:
            flash('Start time and end time are required', 'error')
            has_errors = True

        if not recurrence:
            flash('Recurrence is required', 'error')
            has_errors = True

        if recurrence == 'annual' and not annual_dates:
            flash('At least one annual date is required for annual schedules', 'error')
            has_errors = True

        # Validate month/day combinations
        if recurrence == 'annual':
            for date in annual_dates:
                month, day = date['month'], date['day']
                if month in [4, 6, 9, 11] and day > 30:
                    flash(f'Invalid date: {month}/{day} - this month only has 30 days', 'error')
                    has_errors = True
                elif month == 2 and day > 29:
                    flash(f'Invalid date: {month}/{day} - February only has 29 days', 'error')
                    has_errors = True
                elif day > 31:
                    flash(f'Invalid date: {month}/{day} - no month has more than 31 days', 'error')
                    has_errors = True

        if has_errors:
            return render_template('new_schedule.html'), 400

        # Validate time format
        try:
            start_minutes = ScheduleRecord.time_to_minutes(start_time)
            end_minutes = ScheduleRecord.time_to_minutes(end_time)
        except ValueError:
            flash('Invalid time format. Please use HH:MM format', 'error')
            return render_template('new_schedule.html'), 400

        # Create new schedule with times converted to minutes
        schedule = ScheduleRecord(
            title=title,
            start_time=start_minutes,
            end_time=end_minutes,
            recurrence=recurrence,
            category=category,
            location=location,
            description=description,
            user_id=current_user.id,
            annual_dates=annual_dates if recurrence == 'annual' else None,
            weekday_options=weekday_options if recurrence == 'weekly' else None
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
    schedules = ScheduleRecord.query.filter_by(user_id=current_user.id).all()
    return render_template('schedules.html', schedules=schedules)

@schedule_api_bp.route('/schedule/current')
@login_required
def get_current_schedule():
    """Get the currently active schedule"""
    schedule = integration_service.get_current_schedule()
    return jsonify(schedule)

@schedule_api_bp.route('/schedule/<int:schedule_id>/toggle', methods=['POST'])
@login_required
def toggle_schedule(schedule_id):
    """Toggle a schedule's enabled status"""
    schedule = ScheduleRecord.query.filter_by(id=schedule_id, user_id=current_user.id).first()
    if not schedule:
        return jsonify({'success': False, 'error': 'Schedule not found'}), 404
        
    data = request.get_json()
    if 'enabled' not in data:
        return jsonify({'success': False, 'error': 'Missing enabled parameter'}), 400
        
    schedule.enabled = data['enabled']
    db.session.commit()
    
    return jsonify({'success': True})

@schedules_bp.route('/schedule/<int:schedule_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_schedule(schedule_id):
    """Edit an existing schedule"""
    schedule = ScheduleRecord.query.filter_by(id=schedule_id, user_id=current_user.id).first()
    if not schedule:
        flash('Schedule not found', 'error')
        return redirect(url_for('schedules.list_schedules'))

    if request.method == 'POST':
        # Get form data
        title = request.form.get('title')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        recurrence = request.form.get('recurrence')
        category = request.form.get('category')
        location = request.form.get('location')
        description = request.form.get('description')
        enabled = request.form.get('enabled') == 'on'
        
        # Get month and day pairs for annual dates
        months = request.form.getlist('month[]')
        days = request.form.getlist('day[]')
        annual_dates = []
        if recurrence == 'annual':
            annual_dates = [{'month': int(m), 'day': int(d)} for m, d in zip(months, days)]

        # Collect validation errors
        has_errors = False

        # Get weekday options for weekly schedules
        weekday_options = []
        if recurrence == 'weekly':
            weekday_options = [int(day) for day in request.form.getlist('weekday_options[]')]
            if not weekday_options:
                flash('Please select at least one day of the week for weekly schedules', 'error')
                has_errors = True

        if not title:
            flash('Title is required', 'error')
            has_errors = True

        if not start_time or not end_time:
            flash('Start time and end time are required', 'error')
            has_errors = True

        if not recurrence:
            flash('Recurrence is required', 'error')
            has_errors = True

        if recurrence == 'annual' and not annual_dates:
            flash('At least one annual date is required for annual schedules', 'error')
            has_errors = True

        # Validate month/day combinations
        if recurrence == 'annual':
            for date in annual_dates:
                month, day = date['month'], date['day']
                if month in [4, 6, 9, 11] and day > 30:
                    flash(f'Invalid date: {month}/{day} - this month only has 30 days', 'error')
                    has_errors = True
                elif month == 2 and day > 29:
                    flash(f'Invalid date: {month}/{day} - February only has 29 days', 'error')
                    has_errors = True
                elif day > 31:
                    flash(f'Invalid date: {month}/{day} - no month has more than 31 days', 'error')
                    has_errors = True

        if has_errors:
            return render_template('edit_schedule.html', schedule=schedule), 400

        # Validate time format
        try:
            start_minutes = ScheduleRecord.time_to_minutes(start_time)
            end_minutes = ScheduleRecord.time_to_minutes(end_time)
        except ValueError:
            flash('Invalid time format. Please use HH:MM format', 'error')
            return render_template('edit_schedule.html', schedule=schedule), 400

        # Update schedule
        schedule.title = title
        schedule.start_time = start_minutes
        schedule.end_time = end_minutes
        schedule.recurrence = recurrence
        schedule.category = category
        schedule.location = location
        schedule.description = description
        schedule.enabled = enabled
        schedule.annual_dates = annual_dates if recurrence == 'annual' else None
        schedule.weekday_options = weekday_options if recurrence == 'weekly' else None

        db.session.commit()

        flash('Schedule updated successfully!', 'success')
        return redirect(url_for('schedules.list_schedules'))

    return render_template('edit_schedule.html', schedule=schedule) 