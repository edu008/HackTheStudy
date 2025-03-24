"""
Zentrales Fehlerbehandlungsmodul für das Backend
-----------------------------------------------

Dieses Modul stellt Funktionen und Klassen zur einheitlichen Fehlerbehandlung bereit.
Es definiert Fehlertypen, Hilfsfunktionen für Fehlerantworten und eine einheitliche Logging-Struktur.
"""

import json
import logging
import traceback
from datetime import datetime
from flask import jsonify, current_app, request
from functools import wraps
import sqlalchemy.exc
import werkzeug.exceptions

logger = logging.getLogger(__name__)

# Fehlertyp-Konstanten für einheitliche Fehlerbehandlung
ERROR_INVALID_INPUT = "invalid_input"
ERROR_AUTHENTICATION = "authentication_error"
ERROR_PERMISSION = "permission_denied"
ERROR_NOT_FOUND = "resource_not_found"
ERROR_DATABASE = "database_error"
ERROR_PROCESSING = "processing_error"
ERROR_INSUFFICIENT_CREDITS = "insufficient_credits"
ERROR_API_ERROR = "api_error"
ERROR_TOKEN_LIMIT = "token_limit"
ERROR_RATE_LIMIT = "rate_limit"
ERROR_MAX_RETRIES = "max_retries"
ERROR_CACHE_ERROR = "cache_error"
ERROR_CREDIT_DEDUCTION_FAILED = "credit_deduction_failed"
ERROR_FILE_PROCESSING = "file_processing_error"
ERROR_SESSION_CONFLICT = "session_conflict"
ERROR_UNKNOWN = "unknown_error"

# HTTP-Statuscodes für verschiedene Fehlertypen
ERROR_STATUS_CODES = {
    ERROR_INVALID_INPUT: 400,
    ERROR_AUTHENTICATION: 401,
    ERROR_PERMISSION: 403,
    ERROR_NOT_FOUND: 404,
    ERROR_DATABASE: 500,
    ERROR_PROCESSING: 500,
    ERROR_INSUFFICIENT_CREDITS: 402,
    ERROR_API_ERROR: 500,
    ERROR_TOKEN_LIMIT: 413,
    ERROR_RATE_LIMIT: 429,
    ERROR_MAX_RETRIES: 503,
    ERROR_CACHE_ERROR: 500,
    ERROR_CREDIT_DEDUCTION_FAILED: 402,
    ERROR_FILE_PROCESSING: 400,
    ERROR_SESSION_CONFLICT: 409,
    ERROR_UNKNOWN: 500
}

def create_error_response(error_message, error_type=ERROR_UNKNOWN, additional_data=None, http_status=None):
    """
    Erstellt eine standardisierte Fehlerantwort.
    
    Args:
        error_message: Die Fehlermeldung
        error_type: Der Typ des Fehlers (aus den ERROR_* Konstanten)
        additional_data: Zusätzliche Daten, die in die Antwort aufgenommen werden sollen
        http_status: Optionaler HTTP-Statuscode (überschreibt den Standardwert)
        
    Returns:
        Ein jsonify-Response-Objekt mit standardisierter Fehlerstruktur 
        und passendem HTTP-Statuscode
    """
    if http_status is None:
        http_status = ERROR_STATUS_CODES.get(error_type, 500)
    
    response = {
        "success": False,
        "error": {
            "code": error_type,
            "message": error_message
        }
    }
    
    if additional_data:
        response["error"].update(additional_data)
    
    # CORS-Header werden automatisch durch den globalen after_request Handler in app.py hinzugefügt
    return jsonify(response), http_status

def log_error(error, user_id=None, session_id=None, endpoint=None, additional_info=None):
    """
    Protokolliert einen Fehler in einem standardisierten Format.
    
    Args:
        error: Die Ausnahme oder Fehlermeldung
        user_id: Optional, die ID des betroffenen Benutzers
        session_id: Optional, die ID der betroffenen Sitzung
        endpoint: Optional, der betroffene API-Endpunkt
        additional_info: Optional, zusätzliche Informationen zum Fehler
    """
    error_message = str(error)
    error_type = type(error).__name__ if isinstance(error, Exception) else "Error"
    
    error_data = {
        "error": error_message,
        "error_type": error_type,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if user_id:
        error_data["user_id"] = user_id
    
    if session_id:
        error_data["session_id"] = session_id
        
    if endpoint:
        error_data["endpoint"] = endpoint
    
    if additional_info:
        error_data.update(additional_info)
    
    # Stacktrace hinzufügen, wenn verfügbar
    if isinstance(error, Exception):
        error_data["traceback"] = traceback.format_exc()
    
    # Je nach Schweregrad des Fehlers entsprechendes Log-Level verwenden
    if isinstance(error, (ValueError, TypeError)) or \
       error_type in [ERROR_INVALID_INPUT, ERROR_NOT_FOUND]:
        logger.warning(json.dumps(error_data))
    else:
        logger.error(json.dumps(error_data))

def safe_transaction(func):
    """
    Dekorator für sichere Datenbanktransaktionen.
    Stellt sicher, dass bei Ausnahmen ein Rollback durchgeführt wird.
    
    Usage:
        @safe_transaction
        def my_db_function(db_session, ...):
            # Datenbank-Operationen
            
    Returns:
        Eine dekorierte Funktion mit automatischem Rollback bei Ausnahmen
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        from core.models import db
        
        try:
            return func(*args, **kwargs)
        except Exception as e:
            db.session.rollback()
            log_error(e, endpoint=func.__name__)
            raise
    
    return wrapper

class APIError(Exception):
    """
    Basisklasse für benutzerdefinierte API-Fehler.
    Ermöglicht eine einfache Erzeugung von standardisierten Fehlerantworten.
    """
    def __init__(self, message, error_type=ERROR_UNKNOWN, additional_data=None, http_status=None):
        self.message = message
        self.error_type = error_type
        self.additional_data = additional_data or {}
        self.http_status = http_status
        super().__init__(self.message)
    
    def to_response(self):
        """Konvertiert den Fehler in eine standardisierte API-Antwort."""
        return create_error_response(
            self.message,
            self.error_type,
            self.additional_data,
            self.http_status
        )

# Spezialisierte Fehlerklassen für häufige Fehlertypen
class InvalidInputError(APIError):
    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_INVALID_INPUT, additional_data)

class AuthenticationError(APIError):
    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_AUTHENTICATION, additional_data)

class PermissionError(APIError):
    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_PERMISSION, additional_data)

class ResourceNotFoundError(APIError):
    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_NOT_FOUND, additional_data)

class DatabaseError(APIError):
    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_DATABASE, additional_data)

class InsufficientCreditsError(APIError):
    def __init__(self, message, required_credits=None, available_credits=None):
        additional_data = {}
        if required_credits is not None:
            additional_data["credits_required"] = required_credits
        if available_credits is not None:
            additional_data["credits_available"] = available_credits
        super().__init__(message, ERROR_INSUFFICIENT_CREDITS, additional_data)

class FileProcessingError(APIError):
    def __init__(self, message, additional_data=None):
        super().__init__(message, ERROR_FILE_PROCESSING, additional_data)

def setup_error_handlers(app):
    """
    Richtet globale Fehlerbehandler für die Flask-App ein.
    
    Args:
        app: Die Flask-App
    """
    @app.errorhandler(APIError)
    def handle_api_error(error):
        # Fehlerantwort erstellen - CORS-Header werden durch after_request hinzugefügt
        return error.to_response()
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        log_error(e)
        
        if current_app.config.get('DEBUG', False):
            # Im Debug-Modus mehr Informationen zurückgeben
            return create_error_response(
                f"{type(e).__name__}: {str(e)}",
                ERROR_UNKNOWN,
                {"traceback": traceback.format_exc().split("\n")}
            )
        else:
            # Im Produktionsmodus nur allgemeine Meldung zurückgeben
            return create_error_response(
                "Ein interner Serverfehler ist aufgetreten.",
                ERROR_UNKNOWN
            )
    
    @app.errorhandler(werkzeug.exceptions.MethodNotAllowed)
    def handle_method_not_allowed(error):
        """
        Behandelt 405 Method Not Allowed Fehler
        """
        log_error(error)
        
        # Erstelle eine strukturierte Antwort für MethodNotAllowed
        response = create_error_response(
            f"Die Methode {request.method} ist für diesen Endpunkt nicht erlaubt.",
            ERROR_INVALID_INPUT,
            {"allowed_methods": error.valid_methods if hasattr(error, 'valid_methods') else []},
            http_status=405
        )
        
        # Setze Allow-Header, wenn valid_methods verfügbar
        if hasattr(error, 'valid_methods') and error.valid_methods:
            response[0].headers['Allow'] = ', '.join(error.valid_methods)
            
        return response

    @app.errorhandler(sqlalchemy.exc.OperationalError)
    def handle_db_error(error):
        """
        Behandelt Datenbankverbindungsprobleme
        """
        try:
            from core.models import db
            db.session.rollback()  # Versuche, ausstehende Transaktionen rückgängig zu machen
        except Exception as e:
            app.logger.error(f"Fehler beim Rollback: {str(e)}")
            
        # Fehlerantwort erstellen - CORS-Header werden durch after_request hinzugefügt
        return create_error_response(
            "Datenbankfehler: Die Verbindung zur Datenbank wurde unterbrochen. Bitte versuchen Sie es später erneut.",
            ERROR_DATABASE
        ) 