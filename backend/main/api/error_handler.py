"""
Zentrales Fehlerbehandlungsmodul für das Backend
-----------------------------------------------

WARNUNG: Diese Datei wird zur Abwärtskompatibilität beibehalten.
Für neue Implementierungen verwenden Sie bitte das Modul `api.errors`.

Dieses Modul exportiert die Funktionen und Klassen des modularen Fehlerbehandlungsystems
zur Abwärtskompatibilität mit bestehenden Code.
"""

# Importiere spezifische Konstanten statt Wildcard-Import
from .errors.constants import (
    ERROR_AUTHENTICATION, ERROR_DATABASE, ERROR_INVALID_INPUT, 
    ERROR_NOT_FOUND, ERROR_PERMISSION, ERROR_PROCESSING,
    ERROR_INSUFFICIENT_CREDITS, ERROR_API_ERROR, ERROR_TOKEN_LIMIT,
    ERROR_RATE_LIMIT, ERROR_MAX_RETRIES, ERROR_CACHE_ERROR,
    ERROR_CREDIT_DEDUCTION_FAILED, ERROR_FILE_PROCESSING,
    ERROR_SESSION_CONFLICT, ERROR_UNKNOWN, ERROR_STATUS_CODES
)

from .errors.decorators import safe_transaction
from .errors.exceptions import (APIError, AuthenticationError,
                                  DatabaseError, FileProcessingError,
                                  InsufficientCreditsError, InvalidInputError,
                                  ResourceNotFoundError)
# Import APIPermissionError statt PermissionError
from .errors.exceptions import APIPermissionError, PermissionError
from .errors.handlers import setup_error_handlers
from .errors.logging import log_error
from .errors.responses import create_error_response

# API-Erlaubnisfehler für Backward-Kompatibilität
API_PermissionError = APIPermissionError

# Der Rest dieser Datei bleibt leer, da alle Funktionalität jetzt aus dem
# neuen modularen Fehlerbehandlungssystem importiert wird
