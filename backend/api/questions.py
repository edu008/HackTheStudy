from flask import request, jsonify, current_app
from . import api_bp
from .utils import generate_test_questions, detect_language
from models import db, Upload, Question, UserActivity, Topic
from marshmallow import Schema, fields, ValidationError
import logging
from .auth import token_required

logger = logging.getLogger(__name__)

class QuestionRequestSchema(Schema):
    session_id = fields.Str(required=True)
    count = fields.Int(required=True, validate=lambda n: n > 0)

@api_bp.route('/generate-more-questions', methods=['POST'])
@token_required
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
    
    # Hole alle bestehenden Fragen für diese Upload-ID
    existing_questions = [
        {"text": q.text, "options": q.options, "correct": q.correct_answer, "explanation": q.explanation}
        for q in Question.query.filter_by(upload_id=upload.id).all()
    ]
    logger.info(f"Found {len(existing_questions)} existing questions for session_id: {session_id}")
    
    # Initialisiere den OpenAI-Client
    from openai import OpenAI
    client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
    
    # Ermittle die Sprache und analysiere den Inhalt
    language = detect_language(upload.content)
    main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    analysis = {
        "main_topic": main_topic.name if main_topic else "Unknown Topic",
        "subtopics": [topic.name for topic in Topic.query.filter_by(upload_id=upload.id, is_main_topic=False).all()]
    }
    logger.info(f"Analysis for session_id {session_id}: Main topic={analysis['main_topic']}, Subtopics={analysis['subtopics']}")
    
    try:
        # Generiere neue Fragen mit bestehenden Fragen als Referenz
        new_questions = generate_test_questions(
            upload.content,
            client,
            analysis=analysis,
            existing_questions_list=existing_questions,
            language=language
        )
        
        # Filtere Duplikate basierend auf dem Text
        filtered_questions = [
            q for q in new_questions
            if not any(q['text'] == ex['text'] for ex in existing_questions)
        ]
        logger.info(f"Generated {len(filtered_questions)} new questions before limiting to {count}")
        
        # Begrenze die Anzahl der zurückgegebenen Fragen auf die angeforderte Anzahl
        filtered_questions = filtered_questions[:count]
        
        # Speichere nur gültige Fragen in der Datenbank
        for q in filtered_questions:
            if q.get('text') and q.get('options') and not q['text'].startswith('Could not generate'):
                question = Question(
                    upload_id=upload.id,
                    text=q['text'],
                    options=q['options'],
                    correct_answer=q.get('correct', 0),
                    explanation=q.get('explanation', '')
                )
                db.session.add(question)
                logger.info(f"Saved question: {q['text']}")
        
        # Logge und speichere Benutzeraktivität, falls vorhanden
        if hasattr(request, 'user_id'):
            activity = UserActivity(
                user_id=request.user_id,
                activity_type='test',
                title=f"Generated {len(filtered_questions)} more questions",
                details={"count": len(filtered_questions), "session_id": session_id}
            )
            db.session.add(activity)
            logger.info(f"Logged user activity for generating {len(filtered_questions)} questions")
        
        db.session.commit()
        return jsonify({
            "success": True,
            "data": {
                "questions": filtered_questions
            },
            "message": "Additional questions generated successfully"
        }), 200
    except Exception as e:
        logger.error(f"Error generating questions for session_id {session_id}: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": {"code": "GENERATION_FAILED", "message": str(e)}}), 500
