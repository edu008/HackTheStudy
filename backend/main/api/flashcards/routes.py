"""
Routes-Modul für das Flashcards-Paket
-----------------------------------

Dieses Modul definiert alle API-Endpunkte für die Flashcard-Verwaltung:
- Generierung von Flashcards
- Generierung weiterer Flashcards
- Abfrage von Flashcards
- Verwaltung von Lern-Sessions
"""

from flask import request, jsonify, current_app, g
from api import api_bp
from .controllers import (
    process_generate_flashcards, 
    process_generate_more_flashcards,
    process_get_flashcards,
    process_update_flashcard,
    process_delete_flashcard,
    process_get_study_session,
    process_save_flashcard_feedback
)
from .schemas import FlashcardRequestSchema, FlashcardFeedbackSchema
from api.auth import token_required
import os
import logging

logger = logging.getLogger(__name__)

# CORS-Konfiguration für alle Endpoints
CORS_CONFIG = {
    "supports_credentials": True,
    "origins": os.environ.get('CORS_ORIGINS', '*'),
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}

@api_bp.route('/generate-more-flashcards', methods=['POST', 'OPTIONS'])
def generate_more_flashcards_route():
    """
    API-Endpunkt zum Generieren weiterer Lernkarten zu einer bestehenden Sitzung.
    Erfordert eine gültige Sitzungs-ID und optional die Anzahl der zu generierenden Lernkarten.
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
    
    data = request.get_json()
    if not data or 'session_id' not in data:
        return jsonify({'error': 'Session-ID erforderlich', 'success': False}), 400
    
    session_id = data['session_id']
    count = data.get('count', 5)  # Standardmäßig 5 neue Lernkarten
    timestamp = data.get('timestamp', '')
    
    return process_generate_more_flashcards(session_id, count, timestamp)

@api_bp.route('/flashcards/generate/<session_id>', methods=['POST', 'OPTIONS'])
def generate_flashcards_route(session_id):
    """
    API-Endpunkt zum erstmaligen Generieren von Lernkarten zu einer Sitzung.
    Verwendet die Sitzungs-ID, um den zugehörigen Upload zu finden und Lernkarten zu generieren.
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
    
    # Parameter aus der Anfrage extrahieren
    data = request.get_json() or {}
    count = data.get('count', 10)  # Standardwert: 10 Lernkarten
    topic_filter = data.get('topic_filter', None)  # Optional: Beschränkung auf bestimmte Themen
    
    return process_generate_flashcards(session_id, count, topic_filter)

@api_bp.route('/flashcards/<session_id>', methods=['GET', 'OPTIONS'])
def get_flashcards_route(session_id):
    """
    API-Endpunkt zum Abrufen aller Lernkarten einer Sitzung.
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
    
    # Parameter aus der Anfrage extrahieren
    include_stats = request.args.get('include_stats', 'false').lower() == 'true'
    category = request.args.get('category', None)
    
    return process_get_flashcards(session_id, include_stats, category)

@api_bp.route('/flashcards/<int:flashcard_id>', methods=['PUT', 'OPTIONS'])
def update_flashcard_route(flashcard_id):
    """
    API-Endpunkt zum Aktualisieren einer Lernkarte.
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
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Keine Daten übermittelt', 'success': False}), 400
    
    return process_update_flashcard(flashcard_id, data)

@api_bp.route('/flashcards/<int:flashcard_id>', methods=['DELETE', 'OPTIONS'])
def delete_flashcard_route(flashcard_id):
    """
    API-Endpunkt zum Löschen einer Lernkarte.
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
    
    return process_delete_flashcard(flashcard_id)

@api_bp.route('/flashcards/study/<session_id>', methods=['POST', 'OPTIONS'])
def get_study_session_route(session_id):
    """
    API-Endpunkt zum Starten einer Lern-Session.
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
    
    data = request.get_json() or {}
    settings = data.get('settings', {})
    
    return process_get_study_session(session_id, settings)

@api_bp.route('/flashcards/feedback', methods=['POST', 'OPTIONS'])
def save_flashcard_feedback_route():
    """
    API-Endpunkt zum Speichern von Feedback zu einer Lernkarte.
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
    
    data = request.get_json()
    if not data or 'flashcard_id' not in data or 'difficulty' not in data:
        return jsonify({
            'error': 'Lernkarten-ID und Schwierigkeitsgrad erforderlich',
            'success': False
        }), 400
    
    flashcard_id = data.get('flashcard_id')
    difficulty = data.get('difficulty')
    is_correct = data.get('is_correct', None)
    feedback = data.get('feedback', None)
    time_spent = data.get('time_spent', None)
    
    return process_save_flashcard_feedback(flashcard_id, difficulty, is_correct, feedback, time_spent)
