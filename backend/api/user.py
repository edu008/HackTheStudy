from flask import jsonify, request
from . import api_bp
from .auth import token_required
from models import db, Upload, Flashcard, Question, UserActivity
import logging

logger = logging.getLogger(__name__)

@api_bp.route('/user/uploads', methods=['GET'])
@token_required
def get_user_uploads():
    logger.info(f"Fetching uploads for user_id: {request.user_id}")
    uploads = Upload.query.filter_by(user_id=request.user_id).order_by(Upload.upload_date.desc()).all()
    uploads_data = [
        {
            "id": u.id,
            "session_id": u.session_id,
            "file_name": u.file_name,
            "upload_date": u.upload_date.isoformat(),
            "flashcard_count": Flashcard.query.filter_by(upload_id=u.id).count(),
            "question_count": Question.query.filter_by(upload_id=u.id).count()
        } for u in uploads
    ]
    return jsonify({"success": True, "uploads": uploads_data}), 200

@api_bp.route('/user-history', methods=['GET'])
@token_required
def get_user_history():
    try:
        # Hole alle Aktivitäten des aktuellen Benutzers
        activities = UserActivity.query.filter_by(user_id=request.user_id).order_by(UserActivity.timestamp.desc()).all()
        
        activity_list = [{
            'id': activity.id,
            'user_id': activity.user_id,
            'activity_type': activity.activity_type,
            'title': activity.title,
            'main_topic': activity.main_topic,
            'subtopics': activity.subtopics or [],
            'session_id': activity.session_id,
            'details': activity.details,
            'timestamp': activity.timestamp.isoformat()
        } for activity in activities]

        return jsonify({'success': True, 'activities': activity_list})
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der User-History: {str(e)}")
        return jsonify({'success': False, 'message': 'Fehler beim Abrufen der Aktivitäten'}), 500

@api_bp.route('/user-history/<activity_id>', methods=['PUT'])
@token_required
def update_activity_timestamp(activity_id):
    try:
        activity = UserActivity.query.filter_by(id=activity_id, user_id=request.user_id).first()
        if not activity:
            return jsonify({'success': False, 'message': 'Aktivität nicht gefunden'}), 404
        
        # Aktualisiere den timestamp auf den aktuellen Zeitpunkt
        activity.timestamp = db.func.current_timestamp()
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Aktivität aktualisiert', 'timestamp': activity.timestamp.isoformat()})
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren der Aktivität: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Fehler beim Aktualisieren der Aktivität'}), 500
