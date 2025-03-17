from flask import request, jsonify, current_app, g
from . import api_bp
from tasks import celery, process_upload  # Updated import
from .utils import allowed_file
import uuid
import logging

logger = logging.getLogger(__name__)

@api_bp.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": {"code": "NO_FILE", "message": "No file part"}}), 400
    
    files = request.files.getlist('file')
    if not files or len(files) > 5:
        return jsonify({"success": False, "error": {"code": "INVALID_COUNT", "message": "Max 5 files allowed"}}), 400
    
    session_id = str(uuid.uuid4())
    files_data = [(file.filename, file.read()) for file in files if allowed_file(file.filename)]
    if len(files_data) != len(files):
        return jsonify({"success": False, "error": {"code": "INVALID_TYPE", "message": "Some files have invalid types"}}), 400
    
    # Pass None for openai_client, it will be initialized in the task
    task = process_upload.delay(session_id, files_data, user_id=g.get('user_id'), openai_client=None)
    return jsonify({"success": True, "session_id": session_id, "task_id": task.id, "message": "Processing started"}), 202

@api_bp.route('/results/<session_id>', methods=['GET'])
def get_results(session_id):
    from models import Upload, Flashcard, Question, Topic
    from .utils import detect_language
    
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    flashcards = [{"question": fc.question, "answer": fc.answer} for fc in Flashcard.query.filter_by(upload_id=upload.id).all()]
    questions = [{"text": q.text, "options": q.options, "correct": q.correct_answer, "explanation": q.explanation} for q in Question.query.filter_by(upload_id=upload.id).all()]
    main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    subtopics = Topic.query.filter_by(upload_id=upload.id, parent_id=main_topic.id).all() if main_topic else []
    
    analysis = {
        "main_topic": main_topic.name if main_topic else "Unknown Topic",
        "subtopics": [subtopic.name for subtopic in subtopics],
        "estimated_flashcards": len(flashcards),
        "estimated_questions": len(questions),
        "existing_questions": [],
        "content_type": "unknown",
        "language": detect_language(upload.content) if upload.content else "en"
    }
    
    return jsonify({"success": True, "data": {"flashcards": flashcards, "test_questions": questions, "analysis": analysis}}), 200
