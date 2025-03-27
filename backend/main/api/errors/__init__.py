"""
Fehlerbehandlungsmodul für das Backend
--------------------------------------

Dieses Modul bietet eine modulare Struktur für die Fehlerbehandlung, 
aufgeteilt in verschiedene spezialisierte Komponenten:

- constants: Fehlerkonstanten und Statuscodes
- logging: Funktionen zum Protokollieren von Fehlern
- handlers: Globale Fehlerbehandlungsroutinen
- decorators: Dekoratoren für sichere Operationen
- exceptions: Benutzerdefinierte Ausnahmeklassen
- responses: Funktionen zum Erstellen von Fehlerantworten
"""

# Importiere alle öffentlichen Komponenten aus den Submodulen
from .constants import *
from .logging import log_error
from .handlers import setup_error_handlers
from .decorators import safe_transaction
from .exceptions import (
    APIError, InvalidInputError, AuthenticationError, PermissionError,
    ResourceNotFoundError, DatabaseError, InsufficientCreditsError,
    FileProcessingError
)
from .responses import create_error_response

# Ein praktischer Wrapper für setup_error_handlers
def init_app(app):
    """
    Initialisiert die Fehlerbehandlung für die Flask-App.
    
    Args:
        app: Die Flask-App
    """
    setup_error_handlers(app) 