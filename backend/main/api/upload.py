"""
Upload-Funktionalität für das Backend - WRAPPER
---------------------------------------------

WARNUNG: Diese Datei wird aus Gründen der Abwärtskompatibilität beibehalten.
Für neue Implementierungen verwenden Sie bitte das Modul `api.uploads`.

Diese Datei importiert alle nötigen Funktionen aus dem neuen modularen Upload-Modul,
um Abwärtskompatibilität mit bestehendem Code zu gewährleisten.
"""

# Logger, der Verwendung der alten API dokumentiert
import logging

# Importiere Module statt einzelner Funktionen
from .uploads import (
    upload_core,
    upload_chunked, 
    session_management,
    processing,
    diagnostics
)

# Importiere Blueprint
try:
    from .uploads.routes import uploads_bp
except ImportError:
    uploads_bp = None
    logging.getLogger(__name__).error("Konnte uploads_bp nicht importieren")

logger = logging.getLogger(__name__)
logger.warning(
    "Die Datei upload.py wird verwendet, die aus Gründen der Abwärtskompatibilität beibehalten wird. "
    "Bitte verwenden Sie für neue Implementierungen das api.uploads-Modul."
)

# Exportiere Module für Abwärtskompatibilität
__all__ = [
    'uploads_bp',
    'upload_core',
    'upload_chunked',
    'session_management',
    'processing',
    'diagnostics'
]
