from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from ..models import Activity, ScheduleRecord, db
from ..services.activity_service import infer_activity_importance

# Create two separate blueprints
activities_bp = Blueprint('activities', __name__)  # For activity pages
activity_api_bp = Blueprint('activity_api', __name__, url_prefix='/api')  # For activity API endpoints

@activities_bp.route('/add-activity', methods=['GET', 'POST'])
@login_required
def add_activity():
    if request.method == 'POST':
        # Get form data
        title = request.form.get('title')
        description = request.form.get('description')
        scheduled_date = request.form.get('scheduled_date')
        scheduled_time = request.form.get('scheduled_time')
        category = request.form.get('category')
        duration = request.form.get('duration')
        location = request.form.get('location')
        participants = request.form.get('participants', '').split(',') if request.form.get('participants') else []
        notes = request.form.get('notes')

        # Validate required fields
        if not title:
            flash('Title is required', 'error')
            return render_template('add_activity.html'), 400
            
        if not scheduled_date or not scheduled_time:
            flash('Date and time are required', 'error')
            return render_template('add_activity.html'), 400

        try:
            # Create datetime object from date and time
            scheduled_datetime = datetime.strptime(f"{scheduled_date} {scheduled_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            flash('Invalid date or time format', 'error')
            return render_template('add_activity.html'), 400

        # Create new activity
        activity = Activity(
            title=title,
            description=description,
            scheduled_time=scheduled_datetime,
            category=category,
            duration=int(duration) if duration else None,
            location=location,
            participants=participants,
            notes=notes,
            user_id=current_user.id
        )

        # Infer importance using LLM
        activity.importance = infer_activity_importance(activity)

        db.session.add(activity)
        db.session.commit()

        flash('Activity added successfully!', 'success')
        return redirect(url_for('main.index'))

    return render_template('add_activity.html')

@activity_api_bp.route('/activities', methods=['GET'])
@login_required
def get_activities():
    timeframe = request.args.get('timeframe', 'day')
    now = datetime.utcnow()
    
    # Get activities
    activities = Activity.query.filter_by(status='upcoming', user_id=current_user.id)
    
    # Calculate end time based on timeframe
    if timeframe == 'day':
        end_time = now + timedelta(days=1)
    elif timeframe == 'week':
        end_time = now + timedelta(weeks=1)
    elif timeframe == 'month':
        end_time = now + timedelta(days=30)
    elif timeframe == 'year':
        end_time = now + timedelta(days=365)
    else:
        end_time = now + timedelta(days=1)
    
    # Filter activities by timeframe
    activities = activities.filter(
        Activity.scheduled_time >= now,
        Activity.scheduled_time <= end_time
    ).order_by(Activity.scheduled_time, Activity.importance.desc()).all()
    
    # Convert activities to dict format
    result = [activity.to_dict() for activity in activities]
    
    return jsonify(result)

@activity_api_bp.route('/activities/analyze', methods=['POST'])
@login_required
def analyze_activity():
    """Endpoint to get LLM analysis of an activity without saving it"""
    data = request.json
    temp_activity = Activity(
        title=data.get('title'),
        description=data.get('description'),
        scheduled_time=datetime.fromisoformat(data.get('scheduled_time')),
        category=data.get('category'),
        duration=data.get('duration'),
        location=data.get('location'),
        participants=data.get('participants'),
        user_id=current_user.id
    )
    importance = infer_activity_importance(temp_activity)
    return jsonify({
        'importance': importance
    }) 