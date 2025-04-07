"""
Token-basierte Authentifizierung mit JWT.
Enthält Funktionen für JWT-Token-Validierung und Token-Dekoratoren.
"""

import logging
from functools import wraps

from core.models import User
from flask import g, jsonify, request
from flask_jwt_extended import (get_jwt_identity, jwt_required,
                                verify_jwt_in_request, create_access_token)

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
            return jsonify({"success": False, "error": {"code": "MISSING_TOKEN",
                           "message": "Missing authorization token"}}), 401

        try:
            # Verwende flask_jwt_extended für Token-Validierung
            # Der JWT-Secret-Key wird aus der App-Konfiguration gelesen
            # Validiere Token und hole user_id
            verify_jwt_in_request()  # Token validieren
            user_id = get_jwt_identity()  # Dann erst Identität abrufen

            # Füge den Benutzer zur Flask-g hinzu, um ihn in anderen Funktionen zu verwenden
            user = User.query.get(user_id)
            if not user:
                return jsonify({"success": False, "error": {"code": "INVALID_TOKEN",
                               "message": "Invalid or expired token"}}), 401

            # Speichere den Benutzer in Flask-g und in request für einfachen Zugriff
            g.user = user
            request.user = user
            request.user_id = user_id

            return f(*args, **kwargs)
        except Exception as e:
            logger.error("Fehler bei Token-Validierung: %s", str(e))
            return jsonify({"success": False, "error": {"code": "INVALID_TOKEN",
                           "message": "Invalid or expired token"}}), 401

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
        logger.error("Fehler beim Abrufen des aktuellen Benutzers: %s", str(e))
        return None

# --- Neue Funktion für Token Refresh --- #
@jwt_required(refresh=True)
def handle_token_refresh():
    """
    Verarbeitet eine Anfrage zum Aktualisieren eines Access Tokens.
    Erfordert ein gültiges Refresh Token im Request (normalerweise als Cookie).
    Gibt ein neues Access Token zurück.
    """
    try:
        # Die Identität wird durch @jwt_required(refresh=True) validiert
        current_user_id = get_jwt_identity()
        if not current_user_id:
            # Sollte eigentlich nicht passieren wegen Dekorator, aber zur Sicherheit
            return jsonify({"success": False, "error": {"code": "INVALID_REFRESH_TOKEN", "message": "Ungültiges Refresh-Token"}}), 401

        # Optional: Zusätzliche Prüfungen (z.B. ob User noch existiert/aktiv ist)
        user = User.query.get(current_user_id)
        if not user:
             return jsonify({"success": False, "error": {"code": "USER_NOT_FOUND", "message": "Benutzer nicht gefunden"}}), 401

        # Erstelle ein neues Access Token
        new_access_token = create_access_token(identity=current_user_id)
        logger.info(f"Neues Access Token für Benutzer {current_user_id} erstellt.")

        return jsonify({
            "success": True,
            "access_token": new_access_token
        }), 200

    except Exception as e:
        logger.error(f"Fehler beim Token-Refresh für User {get_jwt_identity()}: {e}", exc_info=True)
        return jsonify({"success": False, "error": {"code": "REFRESH_FAILED", "message": "Token-Aktualisierung fehlgeschlagen."}}), 500
