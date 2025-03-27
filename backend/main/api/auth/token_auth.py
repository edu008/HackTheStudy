"""
Token-basierte Authentifizierung mit JWT.
Enthält Funktionen für JWT-Token-Validierung und Token-Dekoratoren.
"""

import logging
from functools import wraps
from flask import request, jsonify, g
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request
from core.models import User

# Logger konfigurieren
logger = logging.getLogger(__name__)

def token_required(f):
    """
    Dekorator, der überprüft, ob ein gültiges JWT-Token in den Anfrage-Headern übergeben wurde.
    Verwendet flask_jwt_extended für die Token-Validierung.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Bei OPTIONS-Anfragen sofort eine Antwort zurückgeben
        if request.method == 'OPTIONS':
            return jsonify({"success": True})
        
        # Prüfe, ob der Authorization-Header im Request vorhanden ist
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"success": False, "error": {"code": "MISSING_TOKEN", "message": "Missing authorization token"}}), 401
        
        # Extrahiere das Token aus dem Authorization-Header
        token = auth_header.replace('Bearer ', '')
        
        try:
            # Verwende flask_jwt_extended für Token-Validierung
            # Der JWT-Secret-Key wird aus der App-Konfiguration gelesen
            # Validiere Token und hole user_id
            verify_jwt_in_request()  # Token validieren
            user_id = get_jwt_identity()  # Dann erst Identität abrufen
            
            # Füge den Benutzer zur Flask-g hinzu, um ihn in anderen Funktionen zu verwenden
            user = User.query.get(user_id)
            if not user:
                return jsonify({"success": False, "error": {"code": "INVALID_TOKEN", "message": "Invalid or expired token"}}), 401
            
            # Speichere den Benutzer in Flask-g und in request für einfachen Zugriff
            g.user = user
            request.user = user
            request.user_id = user_id
            
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Fehler bei Token-Validierung: {str(e)}")
            return jsonify({"success": False, "error": {"code": "INVALID_TOKEN", "message": "Invalid or expired token"}}), 401
    
    return decorated

def get_current_user():
    """
    Hilfsfunktion, um den aktuellen authentifizierten Benutzer abzurufen.
    Gibt None zurück, wenn kein Benutzer authentifiziert ist.
    """
    try:
        # Versuche, das Token zu validieren
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        
        # Wenn keine Identität vorhanden ist, gib None zurück
        if not user_id:
            return None
        
        # Hole Benutzer aus der Datenbank
        return User.query.get(user_id)
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des aktuellen Benutzers: {str(e)}")
        return None 