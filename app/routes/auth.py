from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from ..models import User, db
from ..models import Activity, ScheduleRecord, Entity

# Create two separate blueprints
auth_bp = Blueprint('auth', __name__)  # For auth routes
profile_bp = Blueprint('profile', __name__)  # For profile routes

# Auth routes
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, redirect to index
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user is None:
            flash('Invalid username or password', 'error')
            return redirect(url_for('auth.login'))
            
        if not user.check_password(password):
            flash('Invalid username or password', 'error')
            return redirect(url_for('auth.login'))
        
        # Log the user in and remember them
        login_user(user, remember=True)
        
        # Get the next page from the query string
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('main.index')
        return redirect(next_page)
    
    # GET request - show login form
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('auth.register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('auth.register'))
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful')
        return redirect(url_for('auth.login'))
    
    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

# Profile routes
@profile_bp.route('/')
@login_required
def profile():
    """User profile page"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
        
    # Get all places accessible to the user
    owned_places = Entity.query.filter_by(user_id=current_user.id).count()
    shared_places = Entity.query.filter(
        Entity.user_id != current_user.id,
        Entity.shared_with.contains([current_user.id])
    ).count()
    public_places = Entity.query.filter(
        Entity.user_id != current_user.id,
        Entity.is_public == True
    ).count()
    
    stats = {
        'total_activities': Activity.query.filter_by(user_id=current_user.id).count(),
        'active_schedules': ScheduleRecord.query.filter_by(user_id=current_user.id).count(),
        'places_tracked': owned_places + shared_places + public_places,
        'owned_places': owned_places,
        'shared_places': shared_places,
        'public_places': public_places
    }
    return render_template('profile.html', user=current_user, stats=stats)

@profile_bp.route('/update', methods=['POST'])
@login_required
def update_profile():
    """Handle profile updates"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
        
    username = request.form.get('username')
    email = request.form.get('email')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    # Validate username and email aren't taken by other users
    if username != current_user.username and User.query.filter_by(username=username).first():
        flash('Username already exists', 'error')
        return redirect(url_for('profile.profile'))
    if email != current_user.email and User.query.filter_by(email=email).first():
        flash('Email already registered', 'error')
        return redirect(url_for('profile.profile'))

    # Update user information
    current_user.username = username
    current_user.email = email

    # Update password if provided
    if new_password:
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('profile.profile'))
        current_user.set_password(new_password)

    db.session.commit()
    flash('Profile updated successfully', 'success')
    return redirect(url_for('profile.profile')) 