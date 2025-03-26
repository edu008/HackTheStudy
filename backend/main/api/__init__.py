from flask import Blueprint, redirect, current_app
import logging
from functools import wraps
import os
from flask_cors import CORS

# API Blueprints erstellen
api_bp = Blueprint('api', __name__)
api_v1_bp = Blueprint('api_v1', __name__)

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

# Konfiguriere CORS für die API-Blueprints
setup_cors_for_blueprint(api_bp)
setup_cors_for_blueprint(api_v1_bp)

# Exportiere die Fehlerbehandlungskomponenten für einfachen Import in anderen Modulen
from .error_handler import (
    log_error, create_error_response, safe_transaction, APIError,
    InvalidInputError, AuthenticationError, PermissionError, 
    ResourceNotFoundError, DatabaseError, InsufficientCreditsError,
    FileProcessingError
)

# Vorhandene Routen-Imports bleiben gleich
from .upload import upload_file, get_results, upload_chunk
from .flashcards import generate_more_flashcards
from .questions import generate_more_questions
from .topics import generate_related_topics, get_topics
from .user import get_user_uploads, get_user_history, update_activity_timestamp
from .auth import auth_bp, setup_oauth
from .payment import payment_bp
from .admin import admin_bp

# Registriere die Sub-Blueprints mit CORS für beide API-Versionen
for bp in [api_bp, api_v1_bp]:
    bp.register_blueprint(auth_bp, url_prefix='/auth')
    bp.register_blueprint(payment_bp, url_prefix='/payment')
    bp.register_blueprint(admin_bp, url_prefix='/admin')

# Registriere explizit die wichtigen Routen unter verschiedenen Pfaden
# Dies stellt sicher, dass alle wichtigen Routes registriert sind, auch wenn sie nicht importiert wurden
api_bp.add_url_rule('/upload/chunk', view_func=upload_chunk, methods=['POST', 'OPTIONS'])
api_v1_bp.add_url_rule('/upload/chunk', view_func=upload_chunk, methods=['POST', 'OPTIONS'])

# Registriere v1 Blueprint mit dem Hauptblueprint
api_bp.register_blueprint(api_v1_bp, url_prefix='/v1')

# Behalte die Umleitung für Abwärtskompatibilität bei
@api_bp.route('/v1/<path:path>')
def redirect_v1(path):
    logger.info(f"Umleitung von /api/v1/{path} zu /api/{path}")
    return redirect(f'/api/{path}', code=301)