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

from .diagnostics import *
from .processing import *
from .session_management import *
from .upload_chunked import *
# Importiere alle öffentlichen Komponenten aus den Submodulen
from .upload_core import *

# Setze die __all__ Variable, um sicherzustellen, dass nur die gewünschten Elemente exportiert werden
__all__ = [
    # upload_core exports
    'handle_upload', 'validate_upload', 'save_upload', 'get_upload_config',

    # upload_chunked exports
    'init_chunked_upload', 'process_chunk', 'finalize_chunked_upload',

    # session_management exports
    'create_upload_session', 'get_session_status', 'cleanup_old_sessions',

    # processing exports
    'process_uploaded_file', 'delegate_to_worker', 'track_processing_progress',

    # diagnostics exports
    'get_upload_diagnostics', 'debug_upload_issue', 'get_upload_metrics'
]
