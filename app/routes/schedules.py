from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from ..models import Schedule, db
from ..services.integration_service import integration_service

schedules_bp = Blueprint('schedules', __name__)

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

        # Create new schedule
        schedule = Schedule(
            title=title,
            start_time=datetime.strptime(start_time, "%H:%M"),
            end_time=datetime.strptime(end_time, "%H:%M"),
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

@schedules_bp.route('/api/schedule/current')
@login_required
def get_current_schedule():
    """Get the currently active schedule"""
    schedule = integration_service.get_current_schedule()
    return jsonify(schedule) 