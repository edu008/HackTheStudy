"""
Upload-Modul für Dateiverarbeitung und -verwaltung
-------------------------------------------------

Dieses Modul bietet eine modulare Struktur für die Dateiupload-Funktionalität,
aufgeteilt in verschiedene spezialisierte Komponenten:

- upload_core: Kernfunktionalität für Datei-Uploads
- upload_chunked: Chunked-Upload-Funktionalität für große Dateien
- session_management: Verwaltung von Upload-Sessions
- processing: Verarbeitung hochgeladener Dateien und Worker-Delegation
- diagnostics: Diagnose- und Debug-Funktionen
"""

# Erstelle einen eigenen Blueprint, der später in der app.py registriert wird
from flask import Blueprint, request, make_response, Response, current_app, jsonify
import logging
import os
import uuid

# Logger für dieses Modul
logger = logging.getLogger(__name__)

# Statt api_bp zu importieren, haben wir einen eigenen Blueprint
uploads_bp = Blueprint('uploads', __name__)

# CORS-Hilfsfunktion
# def add_cors_headers(response):
#     """Fügt CORS-Header zu einer Response hinzu, basierend auf der Origin der Anfrage"""
#     origin = request.headers.get('Origin')
#     
#     # Erlaubte Origins - aus Konfiguration oder Standard-Werte
#     allowed_origins = current_app.config.get('ALLOWED_ORIGINS', [
#         'http://localhost:3000',  # Entwicklungsumgebung
#         'http://localhost:8080',  # Falls Backend direkt aufgerufen wird
#         'https://www.hackthestudy.ch'  # Produktionsumgebung
#     ])
#     
#     # Wenn die Origin in der Liste erlaubter Origins ist, setze sie
#     if origin and (origin in allowed_origins or '*' in allowed_origins):
#         response.headers.add('Access-Control-Allow-Origin', origin)
#         response.headers.add('Access-Control-Allow-Credentials', 'true')
#     else:
#         # Fallback für unbekannte Origins
#         logger.warning(f"Unbekannte Origin: {origin} nicht in {allowed_origins}")
#         response.headers.add('Access-Control-Allow-Origin', 'http://localhost:3000')
#         response.headers.add('Access-Control-Allow-Credentials', 'true')
#     
#     response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Cache-Control,Pragma,Expires')
#     response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
#     response.headers.add('Access-Control-Max-Age', '86400')
#     response.headers.add('Cache-Control', 'no-cache, no-store, must-revalidate')
#     
#     return response

# CORS-Middleware für den Blueprint
# @uploads_bp.after_request
# def after_request(response):
#     """Fügt CORS-Header zu allen Antworten des Blueprints hinzu"""
#     return add_cors_headers(response)

# Importieren der Module in der richtigen Reihenfolge, nach Blueprint-Definition
from .diagnostics import debug_session_status, get_diagnostics, get_session_info
from .session_management import session_mgmt_get_session_info
from .upload_chunked import get_upload_progress, upload_chunk, complete_chunked_upload
from .upload_core import get_results, upload_file, upload_redirect
from .debug import get_upload_debug_info

# Setze die __all__ Variable, um sicherzustellen, dass nur die gewünschten Elemente exportiert werden
__all__ = [
    # Eigener Blueprint
    'uploads_bp',
    
    # upload_core exports
    'upload_file',
    'upload_redirect',
    'get_results',

    # upload_chunked exports
    'upload_chunk',
    'get_upload_progress',
    'complete_chunked_upload',

    # session_management exports
    'session_mgmt_get_session_info',

    # diagnostics exports
    'get_diagnostics',
    'debug_session_status',
    'get_session_info',
    
    # debug exports
    'get_upload_debug_info'
]

# Funktion zum Registrieren der Routen an einem Blueprint
def register_routes(blueprint):
    """
    Registriert alle REST-Endpunkte für den Uploads-Blueprint.
    
    Args:
        blueprint: Der Flask-Blueprint, an dem die Routen registriert werden sollen
    """
    # === Kern-Upload-Routen ===
    # blueprint.add_url_rule('/upload/file', view_func=upload_file, methods=['POST', 'OPTIONS']) 
    # blueprint.add_url_rule('/upload', view_func=upload_redirect, methods=['GET', 'POST', 'OPTIONS']) 
    
    # === Chunked Upload Routen ===
    # blueprint.add_url_rule('/upload/chunk', view_func=upload_chunk, methods=['POST', 'OPTIONS']) 
    # blueprint.add_url_rule('/upload/complete_chunk', view_func=complete_chunked_upload, methods=['POST', 'OPTIONS'])
    # blueprint.add_url_rule('/upload/progress/<session_id>', view_func=get_upload_progress, methods=['GET', 'OPTIONS']) 
    
    # === Ergebnis- und Status-Routen ===
    # Wrapper für get_results (ohne add_cors_headers Aufruf hier)
    def results_endpoint(session_id):
        if request.method == 'OPTIONS':
            # Einfache OK-Antwort, globale CORS-Handler fügen Header hinzu
            return make_response(), 200 
        try:
            result, status_code = get_results(session_id)
            # Globale Handler fügen CORS hinzu
            return make_response(result, status_code) 
        except Exception as e:
            logger.error(f"Fehler im Results-Endpoint-Wrapper: {e}", exc_info=True)
            # Globale Handler fügen CORS hinzu
            return make_response(jsonify({"success": False, "error": {"message": f"Interner Serverfehler: {e}"}}), 500)

    results_endpoint_name = f"{blueprint.name}_results"
    blueprint.add_url_rule('/results/<session_id>',
                           endpoint=results_endpoint_name,
                           view_func=results_endpoint,
                           methods=['GET', 'OPTIONS'])

    options_endpoint_name = f"{blueprint.name}_results_options"
    # Passe Lambda an, um keine Header zu setzen
    blueprint.add_url_rule('/results/<path:path>',
                           endpoint=options_endpoint_name,
                           view_func=lambda path: make_response(), 
                           methods=['OPTIONS'])

    # === Diagnose- und Debug-Routen ===
    # blueprint.add_url_rule('/session-info/<session_id>', view_func=get_session_info, methods=['GET', 'OPTIONS'])
    # blueprint.add_url_rule('/diagnostics/<session_id>', view_func=get_diagnostics, methods=['GET'])
    # blueprint.add_url_rule('/debug-status/<session_id>', view_func=debug_session_status, methods=['GET'])
    # blueprint.add_url_rule('/debug-upload/<session_id>', view_func=get_upload_debug_info, methods=['GET'])
    
    # === Session Management Route ===
    # blueprint.add_url_rule('/new-session', view_func=create_new_session_endpoint, methods=['GET', 'OPTIONS'])
    # Die new-session Route wird über @uploads_bp.route definiert, add_url_rule ist hier nicht nötig
    pass # Funktion bleibt bestehen, aber leer, da Routen über @ Decorator definiert werden

# Füge eine neue Funktion hinzu, um eine neue Session-ID zu generieren
def create_new_session():
    """Erstellt eine neue Session-ID und gibt sie als JSON-Antwort zurück."""
    session_id = str(uuid.uuid4())
    logger.info(f"Neue Session-ID generiert: {session_id}")
    return jsonify({
        "success": True,
        "session_id": session_id
    })

# Route für die neue Session-Generierung registrieren
@uploads_bp.route('/new-session', methods=['GET'])
def new_session():
    """Generiert eine neue Session-ID bei jedem Aufruf."""
    return create_new_session()
