from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, abort
from flask_login import login_required, current_user

from ..models import Activity, SuggestionQueueItem, db
from ..utils.translations import _

suggestions_api_bp = Blueprint('suggestions_api', __name__, url_prefix='/api/suggestions')

MAX_QUEUE_ITEMS_RETURNED = 10
DEFAULT_SNOOZE_HOURS = 24


@suggestions_api_bp.route('/queue', methods=['GET'])
@login_required
def get_queue():
    """The current user's pending suggestions, highest score first."""
    items = SuggestionQueueItem.query.filter_by(
        user_id=current_user.id, status='pending'
    ).order_by(SuggestionQueueItem.score.desc()).limit(MAX_QUEUE_ITEMS_RETURNED).all()

    return jsonify({'items': [item.to_dict() for item in items]})


def _get_owned_item_or_404(item_id):
    item = SuggestionQueueItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        # 404, not 403 -- a queue item is always private to the user it was
        # generated for, so its existence shouldn't be revealed to anyone else.
        abort(404)
    return item


@suggestions_api_bp.route('/queue/<int:item_id>/dismiss', methods=['POST'])
@login_required
def dismiss_item(item_id):
    item = _get_owned_item_or_404(item_id)
    item.status = 'dismissed'
    db.session.commit()
    return jsonify({'item': item.to_dict()})


@suggestions_api_bp.route('/queue/<int:item_id>/snooze', methods=['POST'])
@login_required
def snooze_item(item_id):
    item = _get_owned_item_or_404(item_id)

    data = request.get_json(silent=True) or {}
    snoozed_until = None
    raw_until = data.get('until')
    if raw_until:
        try:
            snoozed_until = datetime.fromisoformat(raw_until)
        except ValueError:
            return jsonify({'error': _("'until' must be an ISO datetime.")}), 400
    if snoozed_until is None:
        snoozed_until = datetime.utcnow() + timedelta(hours=DEFAULT_SNOOZE_HOURS)

    item.status = 'snoozed'
    item.snoozed_until = snoozed_until
    db.session.commit()
    return jsonify({'item': item.to_dict()})


@suggestions_api_bp.route('/queue/<int:item_id>/complete', methods=['POST'])
@login_required
def complete_item(item_id):
    item = _get_owned_item_or_404(item_id)
    item.status = 'done'

    if item.item_type == 'activity':
        activity = Activity.query.filter_by(id=item.source_id, user_id=current_user.id).first()
        if activity:
            activity.status = 'completed'

    db.session.commit()
    return jsonify({'item': item.to_dict()})
