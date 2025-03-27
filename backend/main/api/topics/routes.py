"""
API-Routen für Topics
------------------

Dieses Modul enthält die API-Endpunkte für die Verwaltung von Topics.
"""

import logging
import uuid
from datetime import datetime
from flask import request, jsonify, current_app, g
from . import topics_bp
from ..auth import token_required
from ..utils import check_and_manage_user_sessions
from core.models import db, Upload, Topic, Connection, UserActivity
from api.error_handler import InvalidInputError, ResourceNotFoundError, InsufficientCreditsError
from .utils import find_upload_by_session
from .models import get_topic_hierarchy, log_topic_activity
from .generation import generate_topics, generate_related_topics
from .concept_map import generate_concept_map_suggestions

logger = logging.getLogger(__name__)

@topics_bp.route('/load-topics', methods=['POST', 'OPTIONS'])
def load_topics():
    """
    Erstellt eine neue Topic-Session.
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response
        
    # Authentifizierung für nicht-OPTIONS Anfragen
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    try:
        user_id = getattr(request, 'user_id', None)
        
        # Überprüfe und verwalte die Anzahl der Sessions des Benutzers
        if user_id:
            check_and_manage_user_sessions(user_id)
        
        # Generiere eine neue Session-ID
        session_id = str(uuid.uuid4())
        
        logger.info(f"Creating new session with ID: {session_id} for user: {user_id}")
        
        # Rückgabe der neuen Session-ID
        return jsonify({
            "success": True,
            "message": "Session zurückgesetzt und neue Session erstellt",
            "session_id": session_id
        }), 200
    except Exception as e:
        logger.error(f"Error resetting session: {str(e)}")
        return jsonify({"success": False, "message": f"Fehler beim Zurücksetzen der Session: {str(e)}"}), 500

@topics_bp.route('/generate-related-topics', methods=['POST', 'OPTIONS'])
def generate_related_topics_route():
    """
    Generiert verwandte Topics für eine Sitzung.
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response

    # Führe Authentifizierung durch
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    data = request.json
    session_id = data.get('session_id')
    user_id = getattr(request, 'user_id', None)
    
    if not session_id:
        return jsonify({"success": False, "error": {"code": "NO_SESSION_ID", "message": "Session ID required"}}), 400
    
    try:
        # Generiere verwandte Topics
        result = generate_related_topics(session_id, user_id)
        
        # Protokolliere Aktivität
        if result.get("success") and user_id:
            upload = find_upload_by_session(session_id)
            if upload:
                log_topic_activity(user_id, upload.id, "generate_related_topics", {
                    "new_topics_count": result.get("new_topics_count", 0),
                    "new_connections_count": result.get("new_connections_count", 0)
                })
        
        return jsonify(result), 200 if result.get("success") else 400
    except InvalidInputError as e:
        return jsonify({"success": False, "error": {"code": "INVALID_INPUT", "message": str(e)}}), 400
    except ResourceNotFoundError as e:
        return jsonify({"success": False, "error": {"code": "RESOURCE_NOT_FOUND", "message": str(e)}}), 404
    except InsufficientCreditsError as e:
        return jsonify({
            "success": False, 
            "error": {
                "code": "INSUFFICIENT_CREDITS", 
                "message": str(e),
                "credits_required": e.additional_data.get("credits_required")
            }
        }), 402
    except Exception as e:
        logger.error(f"Error generating related topics: {str(e)}")
        return jsonify({"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}), 500

@topics_bp.route('/topics/<session_id>', methods=['GET', 'OPTIONS'])
def get_topics_route(session_id):
    """
    Holt alle Topics für eine Sitzung.
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response
        
    # Authentifizierung
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    try:
        upload = find_upload_by_session(session_id)
        if not upload:
            return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
        
        # Hole die Topics für diesen Upload
        topics_hierarchy = get_topic_hierarchy(upload.id)
        
        # Protokolliere Aktivität
        user_id = getattr(request, 'user_id', None)
        if user_id:
            log_topic_activity(user_id, upload.id, "view_topics")
        
        return jsonify({
            "success": True,
            "data": topics_hierarchy
        }), 200
    except Exception as e:
        logger.error(f"Error getting topics: {str(e)}")
        return jsonify({"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}), 500

@topics_bp.route('/generate-concept-map-suggestions', methods=['POST', 'OPTIONS'])
def generate_concept_map_suggestions_route():
    """
    Generiert Vorschläge für Verbindungen in einer Concept Map.
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response

    # Führe Authentifizierung durch
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    data = request.json
    session_id = data.get('session_id')
    max_suggestions = data.get('max_suggestions', 5)
    
    if not session_id:
        return jsonify({"success": False, "error": {"code": "NO_SESSION_ID", "message": "Session ID required"}}), 400
    
    try:
        upload = find_upload_by_session(session_id)
        if not upload:
            return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
        
        # Hole das Hauptthema
        main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
        if not main_topic:
            return jsonify({"success": False, "error": {"code": "NO_MAIN_TOPIC", "message": "No main topic found"}}), 404
        
        # Generiere Vorschläge
        suggestions = generate_concept_map_suggestions(upload.id, main_topic, max_suggestions)
        
        return jsonify({
            "success": True,
            "data": {
                "suggestions": suggestions,
                "count": len(suggestions)
            }
        }), 200
    except Exception as e:
        logger.error(f"Error generating concept map suggestions: {str(e)}")
        return jsonify({"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}), 500

@topics_bp.route('/generate/<session_id>', methods=['POST', 'OPTIONS'])
def generate_topics_route(session_id):
    """
    Generiert Topics für eine Sitzung.
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response
        
    # Authentifizierung
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    user_id = getattr(request, 'user_id', None)
    
    try:
        # Generiere Topics
        result = generate_topics(session_id, user_id)
        
        # Protokolliere Aktivität
        if result.get("success") and user_id:
            upload = find_upload_by_session(session_id)
            if upload:
                log_topic_activity(user_id, upload.id, "generate_topics", {
                    "topics_count": result.get("topics_count", 0),
                    "main_topic": result.get("main_topic")
                })
        
        return jsonify(result), 200 if result.get("success") else 400
    except InvalidInputError as e:
        return jsonify({"success": False, "error": {"code": "INVALID_INPUT", "message": str(e)}}), 400
    except ResourceNotFoundError as e:
        return jsonify({"success": False, "error": {"code": "RESOURCE_NOT_FOUND", "message": str(e)}}), 404
    except InsufficientCreditsError as e:
        return jsonify({
            "success": False, 
            "error": {
                "code": "INSUFFICIENT_CREDITS", 
                "message": str(e),
                "credits_required": e.additional_data.get("credits_required")
            }
        }), 402
    except Exception as e:
        logger.error(f"Error generating topics: {str(e)}")
        return jsonify({"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}), 500 