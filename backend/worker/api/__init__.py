"""
API-Module für den Worker-Microservice.
Enthält die zentrale Implementierung der API-Endpunkte für asynchrone Verarbeitung.
"""

# Version des API-Moduls
__version__ = '1.0.0'

# Importiere wichtige Komponenten für einfachen Zugriff
from api.upload import process_upload_files, get_upload_status
from api.openai_client import call_openai_api, extract_text_from_openai_response

# Exportiere öffentliche Funktionen
__all__ = [
    'process_upload_files',
    'get_upload_status',
    'call_openai_api',
    'extract_text_from_openai_response'
] 