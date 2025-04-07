"""
Routes-Modul für das Flashcards-Paket (Refaktoriert)
-----------------------------------

Enthält nur noch API-Endpunkte zum Abrufen und Verwalten
von bereits generierten Flashcards.
Die Generierungs-Routen wurden entfernt, da dies im Worker geschieht.
"""

import logging
import os

from api import api_bp
from api.auth import token_required
from flask import current_app, g, jsonify, request

from .controllers import (process_delete_flashcard,
                          process_get_flashcards, process_get_study_session,
                          process_save_flashcard_feedback,
                          process_update_flashcard)
from .schemas import FlashcardFeedbackSchema

logger = logging.getLogger(__name__)

# CORS-Konfiguration für alle Endpoints
CORS_CONFIG = {
    "supports_credentials": True,
    "origins": os.environ.get('CORS_ORIGINS', '*'),
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}


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
