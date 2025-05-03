from flask import Blueprint, render_template, jsonify, redirect, url_for, request
from flask_login import current_user, login_required
from ..services.integration_service import integration_service
from ..models import Activity, ScheduleRecord, Entity
from datetime import datetime, timedelta

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        dashboard_data = integration_service.get_dashboard_data()
        return render_template('index.html', dashboard_data=dashboard_data)
    return redirect(url_for('auth.login'))

@main_bp.route('/api/stats')
@login_required
def get_stats():
    """Get statistics for the dashboard"""
    now = datetime.utcnow()
    return jsonify({
        'weekly_count': Activity.query.filter(
            Activity.user_id == current_user.id,
            Activity.scheduled_time >= now,
            Activity.scheduled_time <= now + timedelta(weeks=1)
        ).count(),
        'schedule_count': ScheduleRecord.query.filter_by(user_id=current_user.id).count(),
        'places_count': Entity.query.filter_by(user_id=current_user.id).count()
    })

@main_bp.route('/api/calendar/events')
@login_required
def get_calendar_events():
    """Get calendar events for a specified date range"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if end_date:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            
        events = integration_service.get_calendar_events(start_date, end_date)
        return jsonify(events)
    except Exception as e:
        return jsonify([])

@main_bp.route('/health')
def health_check():
    """Health check endpoint that also verifies Ollama connection"""
    import requests
    from sqlalchemy import text
    from ..services.ollama_service import ollama_service
    from ..models import db
    from ..utils.config import config

    try:
        ollama_status = "connected" if ollama_service.check_connection() else "error"
    except requests.exceptions.RequestException:
        ollama_status = "unavailable"

    # Check database connection using SQLAlchemy 2.0 API
    try:
        with db.engine.connect() as conn:
            result = conn.execute(text('SELECT 1')).scalar()
            db_status = 'connected' if result == 1 else 'error'
    except Exception:
        db_status = 'error'

    return jsonify({
        'status': 'healthy',
        'ollama_status': ollama_status,
        'database': db_status,
        'model': config.OLLAMA_MODEL
    }) 