from flask import request, jsonify, current_app
from . import api_bp
from .utils import generate_flashcards, detect_language
from models import db, Upload, Flashcard, UserActivity, Topic
from marshmallow import Schema, fields, ValidationError
import logging
from .auth import token_required

logger = logging.getLogger(__name__)

class FlashcardRequestSchema(Schema):
    session_id = fields.Str(required=True)
    count = fields.Int(required=True, validate=lambda n: n > 0)

@api_bp.route('/generate-more-flashcards', methods=['POST'])
@token_required
def generate_more_flashcards():
    try:
        data = FlashcardRequestSchema().load(request.json)
    except ValidationError as e:
        return jsonify({"success": False, "error": {"code": "VALIDATION_ERROR", "message": str(e.messages)}}), 400
    
    session_id = data['session_id']
    count = data['count']
    logger.info(f"Generating {count} more flashcards for session_id: {session_id}")
    
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    # Hole alle bestehenden Flashcards für diese Upload-ID
    existing_flashcards = [
        {"question": f.question, "answer": f.answer}
        for f in Flashcard.query.filter_by(upload_id=upload.id).all()
    ]
    logger.info(f"Found {len(existing_flashcards)} existing flashcards for session_id: {session_id}")
    
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
        # Generiere neue Flashcards mit bestehenden Flashcards als Referenz
        new_flashcards = generate_flashcards(
            upload.content,
            client,
            analysis=analysis,
            existing_flashcards=existing_flashcards,
            language=language
        )
        
        # Filtere Duplikate basierend auf der Frage
        filtered_flashcards = [
            f for f in new_flashcards
            if not any(f['question'] == ex['question'] for ex in existing_flashcards)
        ]
        logger.info(f"Generated {len(filtered_flashcards)} new flashcards before limiting to {count}")
        
        # Begrenze die Anzahl der zurückgegebenen Flashcards auf die angeforderte Anzahl
        filtered_flashcards = filtered_flashcards[:count]
        
        # Speichere nur gültige Flashcards in der Datenbank
        for f in filtered_flashcards:
            if f.get('question') and f.get('answer') and not f['question'].startswith('Could not generate'):
                flashcard = Flashcard(
                    upload_id=upload.id,
                    question=f['question'],
                    answer=f['answer']
                )
                db.session.add(flashcard)
                logger.info(f"Saved flashcard: {f['question']}")
        
        # Logge und speichere Benutzeraktivität, falls vorhanden
        if hasattr(request, 'user_id'):
            activity = UserActivity(
                user_id=request.user_id,
                activity_type='flashcard',
                title=f"Generated {len(filtered_flashcards)} more flashcards",
                details={"count": len(filtered_flashcards), "session_id": session_id}
            )
            db.session.add(activity)
            logger.info(f"Logged user activity for generating {len(filtered_flashcards)} flashcards")
        
        db.session.commit()
        return jsonify({
            "success": True,
            "data": {
                "flashcards": filtered_flashcards
            },
            "message": "Additional flashcards generated successfully"
        }), 200
    except Exception as e:
        logger.error(f"Error generating flashcards for session_id {session_id}: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": {"code": "GENERATION_FAILED", "message": str(e)}}), 500
