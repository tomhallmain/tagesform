import json
from datetime import datetime, timedelta
from ..models import User, Activity
from .ollama_service import ollama_service

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
        response = ollama_service.query(prompt)
        
        if response:
            try:
                importance = float(response.strip())
                return max(0.0, min(1.0, importance))
            except ValueError:
                return 0.5
        return 0.5
    except Exception as e:
        return 0.5

def get_upcoming_activities(user_id, timeframe='day'):
    """Get upcoming activities for a user within a specified timeframe"""
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
    
    return Activity.query.filter(
        Activity.user_id == user_id,
        Activity.status == 'upcoming',
        Activity.scheduled_time >= now,
        Activity.scheduled_time <= end_time
    ).order_by(Activity.scheduled_time, Activity.importance.desc()).all() 