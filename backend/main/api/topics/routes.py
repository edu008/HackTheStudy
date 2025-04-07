"""
API-Routen für Topics (Refaktoriert)
------------------

Enthält API-Endpunkte zum Abrufen von Topics und ggf. Concept Map Vorschlägen.
Generierungs-Routen entfernt.
"""

import logging
import uuid
from datetime import datetime

from api.error_handler import (InsufficientCreditsError, InvalidInputError,
                               ResourceNotFoundError)
from core.models import Topic, Upload, UserActivity, db, Flashcard, Question
from flask import current_app, g, jsonify, request

from ..auth import token_required
# Entferne check_and_manage_user_sessions, da /load-topics entfernt wird
# from ..utils import check_and_manage_user_sessions 
# Importiere topics_bp direkt aus dem __init__.py Modul
from . import topics_bp # Geändert zu relativem Import
from .concept_map import generate_concept_map_suggestions
# Entferne Imports für Generierungsfunktionen
# from .generation import generate_related_topics, generate_topics
from .models import get_topic_hierarchy # log_topic_activity importiert von core
from .utils import find_upload_by_session # Nicht mehr benötigt?
from core.user_tracking import log_topic_activity
from ..error_handler import (DatabaseError, InvalidInputError,
                             InsufficientCreditsError, ResourceNotFoundError)
# Entferne ungenutzte Imports
# from ..utils.ai_utils import query_chatgpt
# from ..utils.utils_common import generate_unique_id
# from .topic_manager import find_upload_by_session, get_topic_hierarchy, generate_topics

logger = logging.getLogger(__name__)


# --- Veraltete Generierungs-Routen entfernt --- #

# @topics_bp.route('/load-topics', methods=['POST', 'OPTIONS'])
# def load_topics():
#    ...

# @topics_bp.route('/generate-related-topics', methods=['POST', 'OPTIONS'])
# def generate_related_topics_route():
#    ...

# @topics_bp.route('/generate/<session_id>', methods=['POST', 'OPTIONS'])
# def generate_topics_route(session_id):
#    ...


# --- Routen zum Abrufen und für Concept Maps --- #

@topics_bp.route('/<session_id>', methods=['GET', 'OPTIONS'])
def get_topics_route(session_id):
    """
    Holt alle Topics für eine Sitzung.
    HINWEIS: Sollte idealerweise über /api/results/<session_id> erfolgen.
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        # Minimalistische Antwort, da CORS global gehandhabt wird
        return "", 204

    logger.info(f"Topics-Abruf-Endpunkt aufgerufen für Session: {session_id}")

    # Authentifizierung
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result

    try:
        # Finde Upload basierend auf Session ID
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            logger.warning(f"Keine Upload-Session gefunden für {session_id}")
            return jsonify({"success": False,
                           "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404

        logger.info(f"Upload gefunden: ID={upload.id}, Session={session_id}, Status={upload.overall_processing_status}")

        # Hole die Topics für diesen Upload
        topics_hierarchy = get_topic_hierarchy(upload.id)
        logger.info(f"Topics geladen für Upload {upload.id}: {len(topics_hierarchy.get('topics', []))} Topics")

        # Hole Counts für Kontext
        flashcards_count = db.session.query(Flashcard.id).filter_by(upload_id=upload.id).count()
        questions_count = db.session.query(Question.id).filter_by(upload_id=upload.id).count()

        # Protokolliere Aktivität
        user_id = g.get('user_id') # Hole user_id aus g nach @token_required
        if user_id:
            log_topic_activity(user_id, upload.id, "view_topics")

        # Gib nur die Topic-Hierarchie zurück
        return jsonify({
            "success": True,
            "data": topics_hierarchy,
            "metadata": {
                "flashcards_count": flashcards_count,
                "questions_count": questions_count,
                "upload_id": upload.id,
                "processing_status": upload.overall_processing_status
            }
        }), 200
    except Exception as e:
        logger.error(f"Error getting topics for session {session_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": {"code": "SERVER_ERROR", "message": "Fehler beim Laden der Themen."}}), 500


@topics_bp.route('/concept-map/suggestions', methods=['POST', 'OPTIONS'])
def generate_concept_map_suggestions_route():
    """
    Generiert Vorschläge für Verbindungen in einer Concept Map.
    (Diese Funktion könnte potenziell bleiben, wenn sie nur DB-Daten nutzt)
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        return "", 204

    # Authentifizierung
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result

    data = request.json
    session_id = data.get('session_id')
    max_suggestions = data.get('max_suggestions', 5)
    user_id = g.get('user_id')

    if not session_id:
        return jsonify({"success": False, "error": {"code": "NO_SESSION_ID", "message": "Session ID required"}}), 400

    try:
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            return jsonify({"success": False, 
                           "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404

        # Hole das Hauptthema
        main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
        if not main_topic:
            # Versuche irgendein Topic zu finden, falls kein Hauptthema markiert ist
            main_topic = Topic.query.filter_by(upload_id=upload.id).first()
        if not main_topic:
            return jsonify({"success": False, 
                                "error": {"code": "NO_TOPICS_FOUND", "message": "No topics found for this upload"}}), 404
            logger.warning(f"Kein Hauptthema gefunden für Upload {upload.id}, verwende Topic '{main_topic.name}'.")

        # Generiere Vorschläge
        # Annahme: generate_concept_map_suggestions nutzt nur DB-Daten
        suggestions = generate_concept_map_suggestions(upload.id, main_topic, max_suggestions)

        # Aktivität loggen
        if user_id:
             log_topic_activity(user_id, upload.id, "generate_concept_map_suggestions", {"count": len(suggestions)})

        return jsonify({
            "success": True,
            "data": {
                "suggestions": suggestions,
                "count": len(suggestions)
            }
        }), 200
    except Exception as e:
        logger.error(f"Error generating concept map suggestions for session {session_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": {"code": "SERVER_ERROR", "message": "Fehler beim Generieren der Vorschläge."}}), 500
