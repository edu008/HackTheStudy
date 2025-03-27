import logging
import os
from functools import wraps

from flask import Blueprint, current_app, redirect
from flask_cors import CORS

from .admin import admin_bp
from .ai_utils import cached_query_chatgpt, format_json_response, query_chatgpt
from .auth import auth_bp, setup_oauth
from .auth.token_auth import token_required
from .content_analysis import (analyze_content,
                               generate_concept_map_suggestions,
                               unified_content_processing)
from .diagnostics import (debug_session_status, get_diagnostics,
                          get_session_info)
from .error_handler import (APIError, AuthenticationError, DatabaseError,
                            FileProcessingError, InsufficientCreditsError,
                            InvalidInputError, PermissionError,
                            ResourceNotFoundError, create_error_response,
                            log_error, safe_transaction)
from .file_utils import (allowed_file, extract_text_from_file,
                         extract_text_from_pdf, extract_text_from_pdf_safe)
from .flashcards import generate_more_flashcards
from .learning_materials import (generate_additional_flashcards,
                                 generate_additional_questions, generate_quiz)
from .payment import payment_bp
from .processing import process_upload, retry_processing
from .questions import generate_more_questions
from .session_management import session_mgmt_get_session_info
from .session_utils import (check_and_manage_user_sessions, delete_session,
                            update_session_timestamp)
from .text_processing import (clean_text_for_database, count_words,
                              detect_language, extract_sentences,
                              get_text_statistics)
from .topics import generate_related_topics, get_topics
from .upload_chunked import get_upload_progress, upload_chunk
from .upload_core import get_results, upload_file, upload_redirect
from .user import get_user_history, get_user_uploads, update_activity_timestamp
from .utils_common import (format_timestamp, generate_hash, generate_unique_id,
                           get_from_redis, parse_bool, sanitize_filename,
                           store_in_redis, truncate_text)

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
    logger.info("CORS für Blueprint %s konfiguriert", blueprint.name)
    return blueprint


# Konfiguriere CORS für die API-Blueprints
setup_cors_for_blueprint(api_bp)
setup_cors_for_blueprint(api_v1_bp)

# Exportiere die Fehlerbehandlungskomponenten für einfachen Import in anderen Modulen

# Neue Module für Utilities und Hilfsfunktionen (ersetzt utils.py)

# Neue Module für Upload-Funktionalität

# Andere bestehende Imports

# Modulare Authentifizierung importieren (ersetzt auth.py)


# Registriere die Sub-Blueprints mit CORS für beide API-Versionen
for bp in [api_bp, api_v1_bp]:
    bp.register_blueprint(auth_bp, url_prefix='/auth')
    bp.register_blueprint(payment_bp, url_prefix='/payment')
    bp.register_blueprint(admin_bp, url_prefix='/admin')

# Registriere explizit die wichtigen Routen unter verschiedenen Pfaden
# Dies stellt sicher, dass alle wichtigen Routes registriert sind, auch wenn sie nicht importiert wurden
api_bp.add_url_rule('/upload/chunk', view_func=upload_chunk, methods=['POST', 'OPTIONS'])
api_v1_bp.add_url_rule('/upload/chunk', view_func=upload_chunk, methods=['POST', 'OPTIONS'])

# Registriere neue Routen aus der aufgeteilten upload.py-Datei
api_bp.add_url_rule('/upload/progress/<session_id>', view_func=get_upload_progress, methods=['GET', 'OPTIONS'])
api_v1_bp.add_url_rule('/upload/progress/<session_id>', view_func=get_upload_progress, methods=['GET', 'OPTIONS'])

api_bp.add_url_rule('/process-upload/<session_id>', view_func=process_upload, methods=['POST', 'OPTIONS'])
api_v1_bp.add_url_rule('/process-upload/<session_id>', view_func=process_upload, methods=['POST', 'OPTIONS'])

api_bp.add_url_rule('/session-info/<session_id>', view_func=get_session_info, methods=['GET', 'OPTIONS'])
api_v1_bp.add_url_rule('/session-info/<session_id>', view_func=get_session_info, methods=['GET', 'OPTIONS'])

api_bp.add_url_rule('/diagnostics/<session_id>', view_func=get_diagnostics, methods=['GET'])
api_v1_bp.add_url_rule('/diagnostics/<session_id>', view_func=get_diagnostics, methods=['GET'])

api_bp.add_url_rule('/debug-status/<session_id>', view_func=debug_session_status, methods=['GET'])
api_v1_bp.add_url_rule('/debug-status/<session_id>', view_func=debug_session_status, methods=['GET'])

api_bp.add_url_rule('/retry-processing/<session_id>', view_func=retry_processing, methods=['POST', 'OPTIONS'])
api_v1_bp.add_url_rule('/retry-processing/<session_id>', view_func=retry_processing, methods=['POST', 'OPTIONS'])

# Registriere v1 Blueprint mit dem Hauptblueprint
api_bp.register_blueprint(api_v1_bp, url_prefix='/v1')

# Behalte die Umleitung für Abwärtskompatibilität bei


@api_bp.route('/v1/<path:path>')
def redirect_v1(path):
    logger.info("Umleitung von /api/v1/%s zu /api/%s", path, path)
    return redirect(f'/api/{path}', code=301)
