from flask import request, jsonify, current_app
from . import api_bp
from .utils import generate_flashcards, detect_language
from models import db, Upload, Flashcard, UserActivity, Topic
from marshmallow import Schema, fields, ValidationError
import logging

logger = logging.getLogger(__name__)

class FlashcardRequestSchema(Schema):
    session_id = fields.Str(required=True)
    count = fields.Int(required=True, validate=lambda n: n > 0)

@api_bp.route('/generate-more-flashcards', methods=['POST'])
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
    
    existing_flashcards = [{"question": fc.question, "answer": fc.answer} for fc in Flashcard.query.filter_by(upload_id=upload.id).all()]
    # Initialize OpenAI client directly
    from openai import OpenAI
    client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
    language = detect_language(upload.content)
    analysis = {"main_topic": Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first().name}
    
    try:
        new_flashcards = generate_flashcards(upload.content, client, analysis=analysis, existing_flashcards=existing_flashcards, language=language)
        filtered_flashcards = [fc for fc in new_flashcards if not any(fc['question'] == ex['question'] for ex in existing_flashcards)]
        for fc in filtered_flashcards[:count]:
            if fc.get('question') and fc.get('answer') and not fc['question'].startswith('Could not generate'):
                flashcard = Flashcard(upload_id=upload.id, question=fc['question'], answer=fc['answer'])
                db.session.add(flashcard)
        
        if hasattr(request, 'user_id'):
            activity = UserActivity(
                user_id=request.user_id,
                activity_type='flashcard',
                title=f"Generated {len(filtered_flashcards[:count])} more flashcards",
                details={"count": len(filtered_flashcards[:count]), "session_id": session_id}
            )
            db.session.add(activity)
        
        db.session.commit()
        return jsonify({"success": True, "flashcards": filtered_flashcards[:count], "message": "Additional flashcards generated successfully"}), 200
    except Exception as e:
        logger.error(f"Error generating flashcards: {str(e)}")
        return jsonify({"success": False, "error": {"code": "GENERATION_FAILED", "message": str(e)}}), 500
