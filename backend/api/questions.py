from flask import request, jsonify, current_app
from . import api_bp
from .utils import generate_test_questions, detect_language
from models import db, Upload, Question, UserActivity, Topic
from marshmallow import Schema, fields, ValidationError
import logging

logger = logging.getLogger(__name__)

class QuestionRequestSchema(Schema):
    session_id = fields.Str(required=True)
    count = fields.Int(required=True, validate=lambda n: n > 0)

@api_bp.route('/generate-more-questions', methods=['POST'])
def generate_more_questions():
    try:
        data = QuestionRequestSchema().load(request.json)
    except ValidationError as e:
        return jsonify({"success": False, "error": {"code": "VALIDATION_ERROR", "message": str(e.messages)}}), 400
    
    session_id = data['session_id']
    count = data['count']
    logger.info(f"Generating {count} more questions for session_id: {session_id}")
    
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    existing_questions = [{"text": q.text, "options": q.options, "correct": q.correct_answer, "explanation": q.explanation} for q in Question.query.filter_by(upload_id=upload.id).all()]
    # Initialize OpenAI client directly
    from openai import OpenAI
    client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
    language = detect_language(upload.content)
    analysis = {"main_topic": Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first().name}
    
    try:
        new_questions = generate_test_questions(upload.content, client, analysis=analysis, existing_questions_list=existing_questions, language=language)
        filtered_questions = [q for q in new_questions if not any(q['text'] == ex['text'] for ex in existing_questions)]
        for q in filtered_questions[:count]:
            if q.get('text') and q.get('options') and not q['text'].startswith('Could not generate'):
                question = Question(upload_id=upload.id, text=q['text'], options=q['options'], correct_answer=q.get('correct', 0), explanation=q.get('explanation', ''))
                db.session.add(question)
        
        if hasattr(request, 'user_id'):
            activity = UserActivity(
                user_id=request.user_id,
                activity_type='test',
                title=f"Generated {len(filtered_questions[:count])} more questions",
                details={"count": len(filtered_questions[:count]), "session_id": session_id}
            )
            db.session.add(activity)
        
        db.session.commit()
        return jsonify({"success": True, "questions": filtered_questions[:count], "message": "Additional questions generated successfully"}), 200
    except Exception as e:
        logger.error(f"Error generating questions: {str(e)}")
        return jsonify({"success": False, "error": {"code": "GENERATION_FAILED", "message": str(e)}}), 500
