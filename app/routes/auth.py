from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from ..models import User, db
from ..models import Activity, Schedule, Entity

# Create two separate blueprints
auth_bp = Blueprint('auth', __name__)  # For auth routes
profile_bp = Blueprint('profile', __name__)  # For profile routes

# Auth routes
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user is None or not user.check_password(password):
            flash('Invalid username or password')
            return redirect(url_for('auth.login'))
        
        login_user(user)
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('main.index')
        return redirect(next_page)
    
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
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
    stats = {
        'total_activities': Activity.query.filter_by(user_id=current_user.id).count(),
        'active_schedules': Schedule.query.filter_by(user_id=current_user.id).count(),
        'places_tracked': Entity.query.filter_by(user_id=current_user.id).count()
    }
    return render_template('profile.html', user=current_user, stats=stats)

@profile_bp.route('/update', methods=['POST'])
@login_required
def update_profile():
    """Handle profile updates"""
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