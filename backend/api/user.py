from flask import jsonify, request
from . import api_bp
from .auth import token_required
from models import db, Upload, Flashcard, Question
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
