"""
Fehlerprotokollierung
------------------

Dieses Modul enthält Funktionen zur strukturierten Protokollierung von Fehlern
mit einheitlichem Format und kontextbezogenen Informationen.
"""

import json
import logging
import traceback
from datetime import datetime

from .constants import ERROR_INVALID_INPUT, ERROR_NOT_FOUND

logger = logging.getLogger(__name__)


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
