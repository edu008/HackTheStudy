"""
Authentifizierungs- und Berechtigungsfunktionen für das Admin-Modul.
Enthält Dekoratoren für die Zugriffskontrolle auf Admin-Endpunkte.
"""

import os
import logging
from functools import wraps
from flask import jsonify, g
from api.auth.token_auth import token_required

# Logger konfigurieren
logger = logging.getLogger(__name__)

def admin_required(f):
    """
    Dekorator, der überprüft, ob der aktuell authentifizierte Benutzer Admin ist.
    Verwendet token_required als Basis für die Authentifizierung.
    """
    @wraps(f)
    @token_required
    def decorated_function(*args, **kwargs):
        # Hier wurde bereits sichergestellt, dass ein Token gültig ist (durch token_required)
        # Prüfen, ob der Benutzer ein Admin ist
        admin_emails = os.getenv('ADMIN_EMAILS', '').strip().split(',')
        if g.user.email not in admin_emails:
            return jsonify({"success": False, "error": {"code": "NOT_AUTHORIZED", "message": "Admin access required"}}), 403
        
        return f(*args, **kwargs)
    return decorated_function

def is_admin(user):
    """
    Hilfsfunktion, die prüft ob ein Benutzer Admin-Rechte hat.
    
    Args:
        user: Der zu überprüfende Benutzer
        
    Returns:
        bool: True wenn der Benutzer Admin ist, sonst False
    """
    admin_emails = os.getenv('ADMIN_EMAILS', '').strip().split(',')
    return user.email in admin_emails 