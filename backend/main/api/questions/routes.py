"""
Routes-Modul für das Questions-Paket
------------------------------------

Dieses Modul definiert alle API-Endpunkte für die Fragenverwaltung:
- Generierung von Fragen
- Generierung weiterer Fragen
- Abfrage von Fragen
"""

from flask import request, jsonify, current_app, g
from api import api_bp
from .controllers import (
    process_generate_questions, 
    process_generate_more_questions
)
from .schemas import QuestionRequestSchema
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

@api_bp.route('/generate-more-questions', methods=['POST', 'OPTIONS'])
def generate_more_questions_route():
    """
    API-Endpunkt zum Generieren weiterer Fragen zu einer bestehenden Sitzung.
    Erfordert eine gültige Sitzungs-ID und optional die Anzahl der zu generierenden Fragen.
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
    count = data.get('count', 3)  # Standardmäßig 3 neue Fragen
    timestamp = data.get('timestamp', '')
    
    return process_generate_more_questions(session_id, count, timestamp)

@api_bp.route('/questions/generate/<session_id>', methods=['POST', 'OPTIONS'])
def generate_questions_route(session_id):
    """
    API-Endpunkt zum erstmaligen Generieren von Fragen zu einer Sitzung.
    Verwendet die Sitzungs-ID, um den zugehörigen Upload zu finden und Fragen zu generieren.
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
    count = data.get('count', 5)  # Standardwert: 5 Fragen
    topic_filter = data.get('topic_filter', None)  # Optional: Beschränkung auf bestimmte Themen
    
    return process_generate_questions(session_id, count, topic_filter) 