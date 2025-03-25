from flask import Blueprint, redirect, current_app
import logging
from functools import wraps
import os
from flask_cors import CORS

# API Blueprint erstellen
api_bp = Blueprint('api', __name__)

# Wir verwenden jetzt nur das OAuth-Objekt aus auth.py
logger = logging.getLogger(__name__)

# Zentrale CORS-Konfiguration, die für alle Blueprints verwendet werden kann
def setup_cors_for_blueprint(blueprint):
    """
    Zentrale Funktion zur Konfiguration von CORS für Blueprints.
    Diese sollte für alle Blueprints verwendet werden, um eine einheitliche CORS-Konfiguration zu gewährleisten.
    """
    cors_origin_string = os.environ.get('CORS_ORIGINS', '*')
    # Flask-CORS so konfigurieren, dass es nicht automatisch CORS-Header hinzufügt,
    # da dies bereits vom globalen after_request-Handler in app.py erledigt wird.
    # Stattdessen nur Routen registrieren und OPTIONS-Handling aktivieren.
    CORS(blueprint,
         automatic_options=True,  # Automatische OPTIONS-Antworten aktivieren
         send_wildcard=False,     # Kein '*' senden
         supports_credentials=True,  # Credentials werden unterstützt (wichtig für withCredentials)
         resources={r"/*": {"origins": cors_origin_string.split(",") if "," in cors_origin_string else cors_origin_string}})
    logger.info(f"CORS für Blueprint {blueprint.name} konfiguriert")
    return blueprint

# Konfiguriere CORS für den API-Blueprint
setup_cors_for_blueprint(api_bp)

# Exportiere die Fehlerbehandlungskomponenten für einfachen Import in anderen Modulen
from .error_handler import (
    log_error, create_error_response, safe_transaction, APIError,
    InvalidInputError, AuthenticationError, PermissionError, 
    ResourceNotFoundError, DatabaseError, InsufficientCreditsError,
    FileProcessingError
)

# Vorhandene Routen-Imports bleiben gleich
from .upload import upload_file, get_results
from .flashcards import generate_more_flashcards
from .questions import generate_more_questions
from .topics import generate_related_topics, get_topics
from .user import get_user_uploads, get_user_history, update_activity_timestamp
from .auth import auth_bp, setup_oauth

# Bedingt payment importieren
try:
    from .payment import payment_bp
    has_payment_bp = True
except ImportError:
    # Dummy Blueprint für payment erstellen, wenn stripe nicht verfügbar ist
    from flask import Blueprint
    payment_bp = Blueprint('payment', __name__)
    has_payment_bp = False
    print("WARNUNG: Payment-Module konnte nicht importiert werden. Stripe-Funktionalität deaktiviert.")

from .admin import admin_bp

# Registriere den auth Blueprint mit CORS
api_bp.register_blueprint(auth_bp, url_prefix='/auth')

# Registriere den payment Blueprint mit CORS
api_bp.register_blueprint(payment_bp, url_prefix='/payment')

# Registriere die Admin-Blueprint mit CORS
api_bp.register_blueprint(admin_bp, url_prefix='/admin')

# Füge eine Umleitung für /api/v1/ hinzu
@api_bp.route('/v1/<path:path>')
def redirect_v1(path):
    return redirect(f'/api/{path}', code=301)