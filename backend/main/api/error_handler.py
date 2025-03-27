"""
Zentrales Fehlerbehandlungsmodul für das Backend
-----------------------------------------------

WARNUNG: Diese Datei wird zur Abwärtskompatibilität beibehalten.
Für neue Implementierungen verwenden Sie bitte das Modul `api.errors`.

Dieses Modul exportiert die Funktionen und Klassen des modularen Fehlerbehandlungsystems
zur Abwärtskompatibilität mit bestehenden Code.
"""

# Importiere alle notwendigen Komponenten aus dem neuen modularen System
from api.errors.constants import *
from api.errors.logging import log_error
from api.errors.handlers import setup_error_handlers
from api.errors.decorators import safe_transaction
from api.errors.exceptions import (
    APIError, InvalidInputError, AuthenticationError, PermissionError,
    ResourceNotFoundError, DatabaseError, InsufficientCreditsError,
    FileProcessingError
)
from api.errors.responses import create_error_response

# Der Rest dieser Datei bleibt leer, da alle Funktionalität jetzt aus dem
# neuen modularen Fehlerbehandlungssystem importiert wird 