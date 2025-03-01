from flask import Flask, jsonify, request, render_template, redirect, url_for, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_required, current_user, login_user, logout_user
from flask_migrate import Migrate
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import json
import pytz
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from services.integration_service import integration_service
from utils.config import config

# Set up logging based on debug mode
logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app with explicit template folder
app = Flask(__name__, 
            template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates')),
            static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'static')))

# Only log paths in debug mode
if config.debug:
    logger.debug(f"Template folder: {app.template_folder}")
    logger.debug(f"Static folder: {app.static_folder}")
    logger.debug(f"Templates available: {os.listdir(app.template_folder)}")
    logger.debug(f"Static files available: {os.listdir(app.static_folder)}")

app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = config.DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS
app.config['DEBUG'] = config.debug

# Ensure static files are handled correctly
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0 if config.debug else None  # Only disable caching in debug mode
app.static_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))

# Ollama Configuration
OLLAMA_BASE_URL = config.OLLAMA_BASE_URL
OLLAMA_MODEL = config.OLLAMA_MODEL
TASK_UPDATE_INTERVAL = config.TASK_UPDATE_INTERVAL

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
scheduler = BackgroundScheduler()

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    activities = db.relationship('Activity', backref='owner', lazy=True)
    schedules = db.relationship('Schedule', backref='owner', lazy=True)
    preferences = db.Column(db.JSON)  # Store user preferences for importance inference

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    importance = db.Column(db.Float)  # 0.0 to 1.0: LLM-inferred importance
    status = db.Column(db.String(20), default='upcoming')  # upcoming, in_progress, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50))  # social, health, work, leisure, etc.
    duration = db.Column(db.Integer)  # estimated duration in minutes
    location = db.Column(db.String(200))
    participants = db.Column(db.JSON)  # List of people involved
    notes = db.Column(db.Text)

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    recurrence = db.Column(db.String(50))  # daily, weekly, monthly, etc.
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50))
    location = db.Column(db.String(200))
    description = db.Column(db.Text)

class Entity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))  # restaurant, store, service, etc.
    operating_hours = db.Column(db.JSON)  # Store hours in JSON format
    location = db.Column(db.String(200))
    contact_info = db.Column(db.String(200))
    description = db.Column(db.Text)
    tags = db.Column(db.JSON)  # For better categorization and search

def query_ollama(prompt, model=None):
    """Send a query to Ollama's API and return the response"""
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model or OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            }
        )
        response.raise_for_status()
        return response.json()['response']
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error querying Ollama: {e}")
        return None

def generate_importance_prompt(activity, user):
    """Generate a prompt for importance inference based on activity and user context"""
    user_activities = Activity.query.filter_by(user_id=user.id, status='upcoming').all()
    
    context = {
        "current_activity": {
            "title": activity.title,
            "description": activity.description,
            "scheduled_time": activity.scheduled_time.isoformat(),
            "category": activity.category,
            "duration": activity.duration,
            "location": activity.location,
            "participants": activity.participants
        },
        "user_context": {
            "upcoming_count": len(user_activities),
            "preferences": user.preferences,
            "upcoming_events": [
                {
                    "title": a.title,
                    "scheduled_time": a.scheduled_time.isoformat(),
                    "category": a.category
                } for a in user_activities if a.scheduled_time <= (datetime.utcnow() + timedelta(days=7))
            ]
        }
    }
    
    prompt = f"""As a personal schedule assistant, analyze this activity and context to determine its importance (0.0 to 1.0).
Consider:
1. Time sensitivity
2. Personal value (based on category and preferences)
3. Social aspects (participants involved)
4. Location and travel requirements
5. Impact on other activities

Activity and Context:
{json.dumps(context, indent=2)}

Provide only a number between 0.0 and 1.0 as the importance score, where 1.0 is highest importance."""
    
    return prompt

def infer_activity_importance(activity):
    """Use Ollama to infer activity importance"""
    try:
        user = User.query.get(activity.user_id)
        prompt = generate_importance_prompt(activity, user)
        response = query_ollama(prompt)
        
        if response:
            try:
                importance = float(response.strip())
                return max(0.0, min(1.0, importance))
            except ValueError:
                app.logger.error(f"Could not parse importance score from response: {response}")
                return 0.5
        return 0.5
    except Exception as e:
        app.logger.error(f"Error inferring activity importance: {e}")
        return 0.5

def update_activity_importance():
    """Background job to update activity importance using LLM inference"""
    with app.app_context():
        activities = Activity.query.filter_by(status='upcoming').all()
        for activity in activities:
            importance = infer_activity_importance(activity)
            activity.importance = importance
        db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize scheduler with interval from environment
scheduler.add_job(update_activity_importance, 'interval', hours=TASK_UPDATE_INTERVAL)
scheduler.start()

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        dashboard_data = integration_service.get_dashboard_data()
        return render_template('index.html', dashboard_data=dashboard_data)
    return render_template('index.html')

@app.route('/api/activities', methods=['GET'])
def get_activities():
    timeframe = request.args.get('timeframe', 'day')
    activities = Activity.query.filter_by(status='upcoming')
    
    now = datetime.utcnow()
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
    
    activities = activities.filter(
        Activity.scheduled_time >= now,
        Activity.scheduled_time <= end_time
    ).order_by(Activity.scheduled_time, Activity.importance.desc()).all()
    
    return jsonify([{
        'id': activity.id,
        'title': activity.title,
        'scheduled_time': activity.scheduled_time.isoformat(),
        'category': activity.category,
        'importance': activity.importance,
        'location': activity.location,
        'duration': activity.duration,
        'participants': activity.participants
    } for activity in activities])

@app.route('/api/activities/analyze', methods=['POST'])
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
        user_id=1  # TODO: Get actual user ID from session
    )
    importance = infer_activity_importance(temp_activity)
    return jsonify({
        'importance': importance
    })

@app.route('/api/entities/available', methods=['GET'])
def get_available_entities():
    current_time = datetime.now(pytz.UTC)
    current_day = current_time.strftime('%A').lower()
    
    # Query entities that are currently open
    available_entities = Entity.query.all()  # TODO: Add filtering based on operating hours
    
    return jsonify([{
        'id': entity.id,
        'name': entity.name,
        'category': entity.category,
        'location': entity.location,
        'description': entity.description,
        'tags': entity.tags
    } for entity in available_entities])

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics for the dashboard"""
    now = datetime.utcnow()
    return jsonify({
        'weekly_count': Activity.query.filter(
            Activity.scheduled_time >= now,
            Activity.scheduled_time <= now + timedelta(weeks=1)
        ).count(),
        'schedule_count': Schedule.query.count(),
        'places_count': Entity.query.count()
    })

# Add health check endpoint
@app.route('/health')
def health_check():
    """Health check endpoint that also verifies Ollama connection"""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags")
        if response.status_code == 200:
            ollama_status = "connected"
        else:
            ollama_status = "error"
    except requests.exceptions.RequestException:
        ollama_status = "unavailable"

    return jsonify({
        'status': 'healthy',
        'ollama_status': ollama_status,
        'database': 'connected' if db.engine.execute('SELECT 1').scalar() else 'error',
        'model': OLLAMA_MODEL
    })

@app.route('/api/dashboard', methods=['GET'])
@login_required
def get_dashboard_data():
    """Get combined dashboard data including weather, schedule, and calendar events"""
    city = request.args.get('city')
    dashboard_data = integration_service.get_dashboard_data(city)
    return jsonify(dashboard_data)

@app.route('/api/weather', methods=['GET'])
@login_required
def get_weather():
    """Get weather data for a specific city"""
    city = request.args.get('city')
    weather_data = integration_service.get_current_weather(city)
    return jsonify(weather_data)

@app.route('/api/schedule/current', methods=['GET'])
@login_required
def get_current_schedule():
    """Get the currently active schedule"""
    schedule = integration_service.get_current_schedule()
    return jsonify(schedule)

@app.route('/api/calendar/events', methods=['GET'])
@login_required
def get_calendar_events():
    """Get calendar events for a specific date range"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date:
        start_date = datetime.fromisoformat(start_date)
    if end_date:
        end_date = datetime.fromisoformat(end_date)
        
    events = integration_service.get_calendar_events(start_date, end_date)
    return jsonify(events)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user is None or not user.check_password(password):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        
        login_user(user)
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('index')
        return redirect(next_page)
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/add-activity', methods=['GET', 'POST'])
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

        # Create datetime object from date and time
        scheduled_datetime = datetime.strptime(f"{scheduled_date} {scheduled_time}", "%Y-%m-%d %H:%M")

        # Create new activity
        activity = Activity(
            title=title,
            description=description,
            scheduled_time=scheduled_datetime,
            category=category,
            duration=duration,
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
        return redirect(url_for('index'))

    return render_template('add_activity.html')

@app.route('/new-schedule', methods=['GET', 'POST'])
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
        return redirect(url_for('index'))

    return render_template('new_schedule.html')

@app.route('/add-place', methods=['GET', 'POST'])
@login_required
def add_place():
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        category = request.form.get('category')
        location = request.form.get('location')
        contact_info = request.form.get('contact_info')
        description = request.form.get('description')
        tags = request.form.get('tags', '').split(',') if request.form.get('tags') else []

        # Process operating hours
        operating_hours = {}
        days = request.form.getlist('days[]')
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            if day in days:
                operating_hours[day] = {
                    'open': request.form.get(f'{day}_open'),
                    'close': request.form.get(f'{day}_close')
                }

        # Create new entity
        entity = Entity(
            name=name,
            category=category,
            operating_hours=operating_hours,
            location=location,
            contact_info=contact_info,
            description=description,
            tags=tags
        )

        db.session.add(entity)
        db.session.commit()

        flash('Place added successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('add_place.html')

@app.route('/profile')
@login_required
def profile():
    # Get user statistics
    stats = {
        'total_activities': Activity.query.filter_by(user_id=current_user.id).count(),
        'active_schedules': Schedule.query.filter_by(user_id=current_user.id).count(),
        'places_tracked': Entity.query.count()
    }
    return render_template('profile.html', stats=stats)

@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    username = request.form.get('username')
    email = request.form.get('email')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if new_password:
        if new_password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect(url_for('profile'))
        current_user.set_password(new_password)

    # Check if username or email already exists
    if username != current_user.username and User.query.filter_by(username=username).first():
        flash('Username already taken!', 'error')
        return redirect(url_for('profile'))

    if email != current_user.email and User.query.filter_by(email=email).first():
        flash('Email already registered!', 'error')
        return redirect(url_for('profile'))

    current_user.username = username
    current_user.email = email
    db.session.commit()

    flash('Profile updated successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/settings')
@login_required
def settings():
    logger.debug("Rendering settings page")
    logger.debug(f"Current user preferences: {current_user.preferences}")
    return render_template('settings.html', preferences=current_user.preferences or {})

@app.route('/update-notifications', methods=['POST'])
@login_required
def update_notifications():
    preferences = current_user.preferences or {}
    preferences['email_notifications'] = 'email_notifications' in request.form
    preferences['browser_notifications'] = 'browser_notifications' in request.form
    current_user.preferences = preferences
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'message': 'Notification settings updated!',
            'type': 'success'
        })
    
    flash('Notification settings updated!', 'success')
    return redirect(url_for('settings'))

@app.route('/update-display', methods=['POST'])
@login_required
def update_display():
    preferences = current_user.preferences or {}
    preferences['default_view'] = request.form.get('default_view')
    preferences['time_format'] = request.form.get('time_format')
    current_user.preferences = preferences
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'message': 'Display settings updated!',
            'type': 'success'
        })
    
    flash('Display settings updated!', 'success')
    return redirect(url_for('settings'))

@app.route('/update-weather', methods=['POST'])
@login_required
def update_weather():
    preferences = current_user.preferences or {}
    preferences['default_city'] = request.form.get('default_city')
    preferences['temperature_unit'] = request.form.get('temperature_unit')
    current_user.preferences = preferences
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'message': 'Weather settings updated!',
            'type': 'success'
        })
    
    flash('Weather settings updated!', 'success')
    return redirect(url_for('settings'))

@app.route('/export-data')
@login_required
def export_data():
    # Get all user data
    activities = Activity.query.filter_by(user_id=current_user.id).all()
    schedules = Schedule.query.filter_by(user_id=current_user.id).all()
    
    data = {
        'user': {
            'username': current_user.username,
            'email': current_user.email,
            'preferences': current_user.preferences
        },
        'activities': [{
            'title': a.title,
            'description': a.description,
            'scheduled_time': a.scheduled_time.isoformat(),
            'category': a.category,
            'importance': a.importance,
            'status': a.status,
            'location': a.location,
            'participants': a.participants,
            'notes': a.notes
        } for a in activities],
        'schedules': [{
            'title': s.title,
            'start_time': s.start_time.isoformat(),
            'end_time': s.end_time.isoformat(),
            'recurrence': s.recurrence,
            'category': s.category,
            'location': s.location,
            'description': s.description
        } for s in schedules]
    }
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(data)
    
    response = make_response(jsonify(data))
    response.headers['Content-Disposition'] = 'attachment; filename=user_data.json'
    response.headers['Content-Type'] = 'application/json'
    return response

@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    # Delete all user data
    Activity.query.filter_by(user_id=current_user.id).delete()
    Schedule.query.filter_by(user_id=current_user.id).delete()
    db.session.delete(current_user)
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'message': 'Your account has been deleted.',
            'type': 'success',
            'redirect': url_for('index')
        })
    
    logout_user()
    flash('Your account has been deleted.', 'success')
    return redirect(url_for('index'))

@app.before_request
def log_request_info():
    """Log request information when in debug mode"""
    if not config.debug:
        return
        
    logger.debug('Headers: %s', request.headers)
    logger.debug('Path: %s', request.path)
    if request.path.startswith('/static/'):
        logger.debug('Static file requested: %s', request.path)

if __name__ == '__main__':
    with app.app_context():
        if config.debug:
            logger.info(f"Using Ollama at: {OLLAMA_BASE_URL}")
            logger.info(f"Using model: {OLLAMA_MODEL}")
            logger.info(f"Activity update interval: {TASK_UPDATE_INTERVAL} hours")
            logger.info(f"Debug mode: {app.debug}")
        db.create_all()
    app.run(debug=config.debug, use_reloader=True, host='localhost', port=5000)
