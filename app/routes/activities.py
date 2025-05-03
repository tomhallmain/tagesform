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
    
    # Get schedules
    schedules = ScheduleRecord.query.filter_by(user_id=current_user.id, enabled=True).all()
    
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
    
    # Add schedules that match the timeframe
    for schedule_record in schedules:
        # For annual schedules, check if any dates fall within the timeframe
        if schedule_record.recurrence == 'annual' and schedule_record.annual_dates:
            for date in schedule_record.annual_dates:
                # Create a datetime for this year's occurrence
                schedule_date = datetime(now.year, date['month'], date['day'])
                if now <= schedule_date <= end_time:
                    result.append({
                        'id': f"schedule_{schedule_record.id}",
                        'title': schedule_record.title,
                        'description': f"Annual schedule for {date['month']}/{date['day']}",
                        'scheduled_time': schedule_date.isoformat(),
                        'importance': 0.5,  # Default importance for schedules
                        'status': 'upcoming',
                        'category': 'schedule',
                        'duration': None,
                        'location': None,
                        'participants': None,
                        'notes': None,
                        'is_schedule': True,
                        'schedule_details': {
                            'start_time': schedule_record.readable_time(schedule_record.start_time),
                            'end_time': schedule_record.readable_time(schedule_record.end_time)
                        }
                    })
        # For regular schedules, check if any weekdays fall within the timeframe
        else:
            current_date = now
            while current_date <= end_time:
                if current_date.weekday() in schedule_record.weekday_options:
                    result.append({
                        'id': f"schedule_{schedule_record.id}_{current_date.strftime('%Y%m%d')}",
                        'title': schedule_record.title,
                        'description': f"Regular schedule for {current_date.strftime('%A')}",
                        'scheduled_time': current_date.isoformat(),
                        'importance': 0.5,  # Default importance for schedules
                        'status': 'upcoming',
                        'category': 'schedule',
                        'duration': None,
                        'location': None,
                        'participants': None,
                        'notes': None,
                        'is_schedule': True,
                        'schedule_details': {
                            'start_time': schedule_record.readable_time(schedule_record.start_time),
                            'end_time': schedule_record.readable_time(schedule_record.end_time)
                        }
                    })
                current_date += timedelta(days=1)
    
    # Sort all items by scheduled_time
    result.sort(key=lambda x: x['scheduled_time'])
    
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