from flask import Flask, jsonify, request, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_required, current_user, login_user, logout_user
from flask_migrate import Migrate
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import json
import pytz
import os
from apscheduler.schedulers.background import BackgroundScheduler
from services.integration_service import integration_service
from utils.config import config

app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = config.DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS
app.config['DEBUG'] = config.debug

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

if __name__ == '__main__':
    with app.app_context():
        if app.config['DEBUG']:
            app.logger.info(f"Using Ollama at: {OLLAMA_BASE_URL}")
            app.logger.info(f"Using model: {OLLAMA_MODEL}")
            app.logger.info(f"Activity update interval: {TASK_UPDATE_INTERVAL} hours")
        db.create_all()
    app.run(debug=app.config['DEBUG'])
