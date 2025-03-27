"""
Globale Fehlerbehandlungsroutinen
-----------------------------

Dieses Modul definiert globale Fehlerbehandlungsroutinen für Flask-Anwendungen
und stellt deren korrekte Registrierung sicher.
"""

import traceback
import sqlalchemy.exc
import werkzeug.exceptions
from flask import current_app, request

from .constants import ERROR_UNKNOWN, ERROR_INVALID_INPUT, ERROR_DATABASE
from .exceptions import APIError
from .logging import log_error
from .responses import create_error_response

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