# api/upload.py
from flask import request, jsonify
from . import api_bp
from models import db, Upload, Question, Topic
from models import Flashcard
from tasks import process_upload
import uuid
from .utils import allowed_file, extract_text_from_file
import logging

logger = logging.getLogger(__name__)

@api_bp.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": {"code": "NO_FILE", "message": "No file part"}}), 400
    
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({"success": False, "error": {"code": "INVALID_FILE", "message": "Invalid or no file selected"}}), 400
    
    session_id = str(uuid.uuid4())
    file_content = file.read()
    file_name = file.filename
    user_id = getattr(request, 'user_id', None)  # Falls Authentifizierung aktiviert ist
    
    logger.info(f"Received upload request: session_id={session_id}, file_name={file_name}, user_id={user_id}")
    
    # Starte Celery-Task
    task = process_upload.delay(session_id, [(file_name, file_content)], user_id)
    
    return jsonify({
        "success": True,
        "message": "Upload processing started",
        "session_id": session_id,
        "task_id": task.id
    }), 202

@api_bp.route('/results/<session_id>', methods=['GET'])
def get_results(session_id):
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    flashcards = [{"id": fc.id, "question": fc.question, "answer": fc.answer} for fc in Flashcard.query.filter_by(upload_id=upload.id).all()]
    questions = [{"id": q.id, "text": q.text, "options": q.options, "correctAnswer": q.correct_answer, "explanation": q.explanation} for q in Question.query.filter_by(upload_id=upload.id).all()]
    
    # Get the main topic
    main_topic = "Unknown Topic"
    main_topic_obj = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    if main_topic_obj:
        main_topic = main_topic_obj.name
    
    # Get subtopics
    subtopics = [topic.name for topic in Topic.query.filter_by(upload_id=upload.id, is_main_topic=False).all()]
    
    return jsonify({
        "success": True,
        "data": {
            "flashcards": flashcards,
            "test_questions": questions,
            "analysis": {
                "main_topic": main_topic,
                "subtopics": subtopics,
                "content_type": "unknown",
                "language": "de"  # Default to German for this application
            },
            "session_id": session_id
        }
    }), 200
