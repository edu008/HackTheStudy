import logging
import os
from functools import wraps

from flask import Blueprint, current_app, redirect
from flask_cors import CORS

# API Blueprints erstellen
api_bp = Blueprint('api', __name__, url_prefix='/api')
api_v1_bp = Blueprint('api_v1', __name__, url_prefix='/v1')

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Importe nach Blueprint-Definition, um zirkuläre Importe zu vermeiden
from .admin import admin_bp
from .utils.ai_utils import cached_query_chatgpt, format_json_response, query_chatgpt
from .auth import auth_bp, setup_oauth, register_routes as register_auth_routes
from .auth.token_auth import token_required
from .token_tracking import register_routes as register_token_routes

# Importiere den uploads-Blueprint direkt, nicht die register Funktion
from .uploads import uploads_bp
from .topics.topic_routes import register_topic_routes

# Importe von Modulen aus dem utils-Unterverzeichnis
try:
    from .utils.content_analysis import (analyze_content,
                                   generate_concept_map_suggestions,
                                   unified_content_processing)
except ImportError:
    logger.warning("Module 'utils.content_analysis' konnte nicht importiert werden")

# Importe von Modulen aus dem uploads-Unterverzeichnis für Diagnostik
from .uploads.diagnostics import (debug_session_status, get_diagnostics,
                          get_session_info)

from .error_handler import (APIError, AuthenticationError, DatabaseError,
                            FileProcessingError, InsufficientCreditsError,
                            InvalidInputError, PermissionError,
                            ResourceNotFoundError, create_error_response,
                            log_error, safe_transaction)

# Importe existierender Module (auskommentiert, falls sie nicht existieren)
# from .flashcards import generate_more_flashcards
# from .questions import generate_more_questions
# from .topics import generate_related_topics, get_topics

# Importe aus dem utils-Unterverzeichnis für Lernmaterialien
# from .utils.learning_materials import (generate_additional_flashcards,
#                                  generate_additional_questions, generate_quiz)

from .payment import payment_bp
# from .uploads.processing import process_upload, retry_processing
# from .uploads.session_management import session_mgmt_get_session_info
# from .utils.session_utils import (check_and_manage_user_sessions, delete_session,
#                             update_session_timestamp)
# from .utils.text_processing import (clean_text_for_database, count_words,
#                               detect_language, extract_sentences,
#                               get_text_statistics)

# from .uploads.upload_chunked import get_upload_progress, upload_chunk
# from .uploads.upload_core import get_results, upload_file, upload_redirect
from .user import get_user_history, get_user_uploads, update_activity_timestamp
from .utils.utils_common import (format_timestamp, generate_hash, generate_unique_id,
                           get_from_redis, parse_bool, sanitize_filename,
                           store_in_redis, truncate_text)
from .flashcards import flashcards_bp

# Token-Tracking Routen registrieren
register_token_routes(api_bp)
register_token_routes(api_v1_bp)

# Registriere die Routen/Blueprints der Untermodule am Haupt-Blueprint
register_auth_routes(api_bp)
register_topic_routes(api_bp)
api_bp.register_blueprint(flashcards_bp, url_prefix='/flashcards')
api_bp.register_blueprint(payment_bp, url_prefix='/payment')
api_bp.register_blueprint(admin_bp, url_prefix='/admin')
# Registriere den uploads_bp direkt
api_bp.register_blueprint(uploads_bp, url_prefix='/uploads')

# Registriere hier die gleichen Routen/Blueprints oder spezifische V1-Routen für api_v1_bp
register_auth_routes(api_v1_bp)
register_topic_routes(api_v1_bp)
api_v1_bp.register_blueprint(flashcards_bp, url_prefix='/flashcards')
# Registriere den uploads_bp auch für V1
api_v1_bp.register_blueprint(uploads_bp, url_prefix='/uploads')

# Registriere den V1-Blueprint unter dem Haupt-API-Blueprint
api_bp.register_blueprint(api_v1_bp)

# Behalte die Umleitung für Abwärtskompatibilität bei
@api_bp.route('/v1/<path:path>')
def redirect_v1(path):
    # Bestimmte Pfade nicht umleiten, da sie in der v1-Version spezifisch sind
    excluded_paths = ['topics/', 'session-info/', 'results/']
    for excluded in excluded_paths:
        if path.startswith(excluded):
            logger.info("Keine Umleitung für /api/v1/%s - API-Version v1 wird verwendet", path)
            # Hier geben wir keine Response zurück, sondern lassen Flask weitermachen
            # zu den anderen Routen, die für diesen Pfad registriert sind
            return

    logger.info("Umleitung von /api/v1/%s zu /api/%s", path, path)
    return redirect(f'/api/{path}', code=301)

def create_api_blueprint():
    """
    Erstellt und registriert alle API-Blueprints.
    """
    # Wir verwenden die bereits definierten und oben konfigurierten Blueprints
    return api_bp

logger.info("API Blueprints (api_bp, api_v1_bp) und Routen initialisiert.")
